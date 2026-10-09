import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.api.agent.tools.customer_tool import get_customer
from src.api.agent.tools.invoice_tools import get_invoice

load_dotenv()


# ============================================================
# TOOLS
# ============================================================

tools = [
    get_invoice,
    get_customer,
]


# ============================================================
# LLM
# ============================================================

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)


# ============================================================
# BIND TOOLS TO LLM
# ============================================================

llm_with_tools = llm.bind_tools(tools)


# ============================================================
# AGENT NODE
# ============================================================

def agent(state: MessagesState):
    response = llm_with_tools.invoke(state["messages"])

    return {
        "messages": [response]
    }


# ============================================================
# BUILD LANGGRAPH
# ============================================================

builder = StateGraph(MessagesState)

# Nodes
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(tools))

# START -> Agent
builder.add_edge(START, "agent")

# Agent -> Tools OR END
builder.add_conditional_edges(
    "agent",
    tools_condition,
)

# Tools -> Agent
builder.add_edge("tools", "agent")


# Compile graph
graph = builder.compile()


# ============================================================
# QUESTION
# ============================================================

question = """
Give me the current cashflow situation for Ganesh Gnawali.

Tell me:
- total invoiced
- total paid
- total outstanding
- overdue invoices
- risk level
- recommended action
"""


# ============================================================
# INVOKE GRAPH
# ============================================================

result = graph.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": question,
            }
        ]
    }
)


# ============================================================
# PRINT FINAL AI RESPONSE
# ============================================================

print("\n================ FINAL ANSWER ================\n")

for message in reversed(result["messages"]):

    if message.type == "ai" and message.content:
        print(message.content)
        break

