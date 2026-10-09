
from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.api.agent.graph import graph

router = APIRouter(
    tags=["Agent"],
)



class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/investigate", response_model=ChatResponse)
@router.post("/agent/chat", response_model=ChatResponse, include_in_schema=False)
def investigate(request: ChatRequest):

    result = graph.invoke(
        {
            "messages": [HumanMessage(content=request.message)]
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