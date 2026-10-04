import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_groq import ChatGroq

from src.api.agent.search_invoice import search_invoices

load_dotenv()


# ============================================================
# MODEL
# ============================================================

model = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)


# ============================================================
# TOOLS
# ============================================================

@tool
def get_invoice(invoice_number: str) -> dict:
    """Retrieve an exact invoice by invoice number."""

    # Replace this with your existing database/API implementation
    # if you already have one.

    return search_invoices(invoice_number)


tools = [
    get_invoice,
    search_invoices,
]


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a business cashflow assistant.

You help users understand customer invoices, payments,
outstanding balances, collection status, and risk.

Use the available tools to retrieve invoice information.

Rules:

1. If the user asks about a specific invoice number,
   use get_invoice.

2. If the user asks about a customer, outstanding invoices,
   overdue invoices, payment status, collection status,
   or risk, use search_invoices.

3. Never invent invoice data.

4. Clearly explain the result to the user.

5. If there are no matching invoices, say so clearly.

6. For financial totals, use the values returned by the tools.

7. Keep the final answer concise and business-friendly.
"""


# ============================================================
# CREATE AGENT
# ============================================================

agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    question = """
    Give me the current cashflow situation for customer
    ABC Property Management.

    Tell me:
    - total invoiced
    - total paid
    - total outstanding
    - overdue invoices
    - risk level
    - what action should be taken
    """

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        }
    )

    # ========================================================
    # GET FINAL AI MESSAGE
    # ========================================================

    messages = result["messages"]

    for message in reversed(messages):
        if getattr(message, "type", None) == "ai":
            print("\n" + message.content)
            break