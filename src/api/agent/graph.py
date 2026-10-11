
import os

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import SecretStr

from src.api.agent.tools.customer_tool import get_customer
from src.api.agent.tools.invoice_tools import get_invoice

load_dotenv()


tools = [
    get_invoice,
    get_customer,
]


llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=(
        SecretStr(api_key) if (api_key := os.getenv("GROQ_API_KEY")) is not None else None
    ),
)

llm_with_tools = llm.bind_tools(tools)

SYSTEM = """You are a collections assistant.
After the tools return, reply in exactly two parts and nothing else:
1. One short paragraph (3–5 sentences): why this invoice is unpaid, and the single next action.
2. A ready-to-send email with a Subject line and a short body.
Use only facts from the tools. Use £ for GBP. Do not invent an email address, phone number, or dispute.
Do not use tables, checklists, or multi-step escalation plans."""


def agent(state: MessagesState):
    response = llm_with_tools.invoke(
        [SystemMessage(content=SYSTEM), *state["messages"]]
    )

    return {
        "messages": [response]
    }


builder = StateGraph(MessagesState)

builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "agent")

builder.add_conditional_edges(
    "agent",
    tools_condition,
)

builder.add_edge("tools", "agent")


# Compile
graph = builder.compile()

