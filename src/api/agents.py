
from fastapi import APIRouter
from pydantic import BaseModel

from src.api.agent.graph import graph

router = APIRouter(
    prefix="/agent",
    tags=["Agent"],
)



class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": request.message,
                }
            ]
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