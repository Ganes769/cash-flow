
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.api.agent.graph import graph

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

        yield event(
            "result",
            {
                "response": answer,
                "email": fields.get("email"),
                "customer": fields.get("customer"),
                "invoice_number": fields.get("invoice_number"),
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

    return ChatResponse(
        response=answer,
        email=fields.get("email"),
        customer=fields.get("customer"),
        invoice_number=fields.get("invoice_number"),
    )