
import os

from dotenv import load_dotenv
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
def agent(state: MessagesState):
    response = llm_with_tools.invoke(state["messages"])

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

