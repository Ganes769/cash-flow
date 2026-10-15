
import json
import logging
from collections.abc import AsyncIterator
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from src.api.agent.graph import graph
from src.api.agent.mail import (
    MailDeliveryError,
    MailNotConfiguredError,
    send_collection_email,
)
from src.db.database import SessionLocal
from src.db.schema.collection import CollectionEmail
from src.db.schema.xero_sync import XeroContactRecord, XeroInvoiceRecord

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Agent"],
)



class ChatRequest(BaseModel):
    message: str
    invoice_number: str | None = None


class ChatResponse(BaseModel):
    response: str
    email: str | None = None
    customer: str | None = None
    invoice_number: str | None = None
    collection_status: str | None = None
    can_send: bool = False


class SendEmailRequest(BaseModel):
    invoice_number: str = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    to: EmailStr | None = None


class SendEmailResponse(BaseModel):
    status: str
    id: str
    to: EmailStr
    invoice_number: str | None = None


def _payload_value(payload: dict, *keys):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


_SENDABLE = {"OVERDUE", "DUE_TODAY", "DUE_SOON"}


def _collection_status(xero_status: str | None, amount_due: float, due_date_string: str | None) -> str:
    status = (xero_status or "").upper()
    if status in {"DRAFT", "VOIDED", "DELETED"}:
        return status
    if amount_due <= 0:
        return "PAID"
    if not due_date_string:
        return "OPEN"
    try:
        due_date = date.fromisoformat(str(due_date_string)[:10])
    except ValueError:
        return "OPEN"
    days_until_due = (due_date - date.today()).days
    if days_until_due < 0:
        return "OVERDUE"
    if days_until_due == 0:
        return "DUE_TODAY"
    if days_until_due <= 7:
        return "DUE_SOON"
    return "OPEN"


def _invoice_mail_context(invoice_number: str | None) -> dict:
    empty = {
        "email": None,
        "customer": None,
        "collection_status": None,
        "can_send": False,
        "found": False,
    }
    if not invoice_number or not str(invoice_number).strip():
        return empty
    number = str(invoice_number).strip()
    with SessionLocal() as db:
        invoice = db.execute(
            select(XeroInvoiceRecord).where(
                XeroInvoiceRecord.deleted.is_(False),
                func.lower(XeroInvoiceRecord.invoice_number) == number.lower(),
            )
        ).scalars().first()
        if invoice is None:
            return empty
        payload = invoice.payload or {}
        contact = payload.get("contact") or payload.get("Contact") or {}
        name = str(_payload_value(contact, "name", "Name") or "").strip()
        email = _payload_value(contact, "email_address", "EmailAddress")
        if not email and name:
            row = db.execute(
                select(XeroContactRecord).where(
                    XeroContactRecord.deleted.is_(False),
                    func.lower(XeroContactRecord.name) == name.lower(),
                )
            ).scalars().first()
            email = row.email if row else None
        amount_due = float(_payload_value(payload, "amount_due", "AmountDue") or 0)
        due_date = str(_payload_value(payload, "due_date", "DueDate") or "")
        collection_status = _collection_status(invoice.status, amount_due, due_date)
        email_text = str(email).strip() if email else None
        return {
            "email": email_text,
            "customer": name or None,
            "collection_status": collection_status,
            "can_send": bool(email_text) and collection_status in _SENDABLE,
            "found": True,
        }


def _record_sent_email(request: SendEmailRequest, recipient: str, provider_id: str) -> None:
    with SessionLocal() as db:
        db.add(
            CollectionEmail(
                invoice_number=request.invoice_number.strip(),
                to_email=recipient,
                subject=request.subject.strip(),
                body=request.body,
                provider_id=provider_id,
            )
        )
        db.commit()


def _message_content(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


def _tool_payload(message) -> dict:
    content = message.content
    if isinstance(content, dict):
        return content
    if not isinstance(content, str) or not content.strip():
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _apply_tool_fields(item, fields: dict) -> dict:
    payload = _tool_payload(item)
    if item.name == "get_invoice":
        fields["invoice_number"] = payload.get("invoice_number") or fields.get("invoice_number")
        fields["customer"] = payload.get("customer") or fields.get("customer")
        fields["email"] = payload.get("email") or fields.get("email")
    elif item.name == "get_customer":
        fields["customer"] = payload.get("customer") or fields.get("customer")
        fields["email"] = payload.get("email") or fields.get("email")
    return fields


def _investigation_prompt(request: ChatRequest) -> str:
    if not request.invoice_number:
        return request.message

    invoice_number = request.invoice_number.strip()
    if not invoice_number:
        return request.message

    return (
        f"{request.message}\n\n"
        f"The currently open invoice is {invoice_number}. "
        "Use the get_invoice tool to retrieve this invoice before analyzing it. "
        "Then call get_customer with the customer name from that invoice to get their email. "
        "Base the investigation on the retrieved invoice and customer data."
    )


async def _investigation_events(message: str) -> AsyncIterator[str]:
    step = 0
    answer = ""
    tool_steps: dict[str, int] = {}
    fields: dict = {
        "email": None,
        "customer": None,
        "invoice_number": None,
    }

    def event(name: str, payload: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    try:
        async for update in graph.astream(
            {"messages": [HumanMessage(content=message)]},
            stream_mode="updates",
        ):
            for node, state_update in update.items():
                messages = state_update.get("messages", [])
                for item in messages:
                    if node == "agent" and item.type == "ai":
                        tool_calls = getattr(item, "tool_calls", [])
                        if tool_calls:
                            for call in tool_calls:
                                step += 1
                                yield event(
                                    "step",
                                    {
                                        "step": step,
                                        "status": "started",
                                        "tool": call.get("name", "tool"),
                                    },
                                )
                                call_id = call.get("id")
                                if call_id:
                                    tool_steps[call_id] = step
                        elif item.content:
                            answer = _message_content(item)
                    elif node == "tools" and item.type == "tool":
                        fields = _apply_tool_fields(item, fields)
                        completed = {
                            "step": tool_steps.get(item.tool_call_id, step),
                            "status": "completed",
                            "tool": item.name,
                        }
                        if item.name == "get_customer":
                            completed["email"] = fields.get("email")
                            completed["customer"] = fields.get("customer")
                        yield event("step", completed)

        context = _invoice_mail_context(fields.get("invoice_number"))
        yield event(
            "result",
            {
                "response": answer,
                "email": context.get("email") or fields.get("email"),
                "customer": context.get("customer") or fields.get("customer"),
                "invoice_number": fields.get("invoice_number"),
                "collection_status": context.get("collection_status"),
                "can_send": context.get("can_send", False),
            },
        )
    except Exception:
        logger.exception("Investigation graph failed")
        yield event("error", {"message": "Investigation failed. Check server logs."})


@router.post("/investigate/stream")
async def investigate_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _investigation_events(_investigation_prompt(request)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/investigate", response_model=ChatResponse)
@router.post("/agent/chat", response_model=ChatResponse, include_in_schema=False)
def investigate(request: ChatRequest):

    result = graph.invoke(
        {
            "messages": [HumanMessage(content=_investigation_prompt(request))]
        }
    )

    fields: dict = {
        "email": None,
        "customer": None,
        "invoice_number": None,
    }
    answer = "No response generated."
    for message in result["messages"]:
        if message.type == "tool":
            fields = _apply_tool_fields(message, fields)
        elif message.type == "ai" and message.content:
            answer = _message_content(message)

    context = _invoice_mail_context(fields.get("invoice_number"))
    return ChatResponse(
        response=answer,
        email=context.get("email") or fields.get("email"),
        customer=context.get("customer") or fields.get("customer"),
        invoice_number=fields.get("invoice_number"),
        collection_status=context.get("collection_status"),
        can_send=bool(context.get("can_send")),
    )


@router.post("/investigate/send", response_model=SendEmailResponse)
def investigate_send(request: SendEmailRequest):
    """Send a confirmed reminder for a due or overdue invoice."""
    context = _invoice_mail_context(request.invoice_number)
    if not context["found"]:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if context["collection_status"] not in _SENDABLE:
        raise HTTPException(
            status_code=400,
            detail="Email can only be sent for overdue or due invoices.",
        )
    recipient = context["email"]
    if not recipient:
        raise HTTPException(status_code=400, detail="This customer has no email in Xero.")
    if request.to and str(request.to).lower() != recipient.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Send only to the contact email on file ({recipient}).",
        )
    try:
        message_id = send_collection_email(
            to=recipient,
            subject=request.subject.strip(),
            body=request.body,
        )
    except MailNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MailDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _record_sent_email(request, recipient, message_id)
    return SendEmailResponse(
        status="sent",
        id=message_id,
        to=recipient,
        invoice_number=request.invoice_number.strip(),
    )