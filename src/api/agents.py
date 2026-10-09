
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


def _message_content(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


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
        "Base the investigation on the retrieved invoice data."
    )


async def _investigation_events(message: str) -> AsyncIterator[str]:
    step = 0
    answer = ""
    tool_steps: dict[str, int] = {}

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
                        yield event(
                            "step",
                            {
                                "step": tool_steps.get(item.tool_call_id, step),
                                "status": "completed",
                                "tool": item.name,
                            },
                        )

        yield event("result", {"response": answer})
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

    for message in reversed(result["messages"]):

        if message.type == "ai" and message.content:
            return ChatResponse(
                response=message.content
            )

    return ChatResponse(
        response="No response generated."
    )