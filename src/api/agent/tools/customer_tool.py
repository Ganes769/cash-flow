import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from src.api.agent.search_invoice import search_invoices

load_dotenv()

@tool
def get_customer(customer_name: str) -> dict:
    """
    Retrieve customer information and invoice history.

    Use this when you need to understand a customer's
    invoices, payment behaviour, outstanding balance,
    and collection risk.
    """

    customer_name = customer_name.strip()

    results = search_invoices(
        question=f"Customer {customer_name} invoice history",
        customer_name=customer_name,
        top_k=50,
    )

    matches = results.get("matches", [])

    if not matches:
        return {
            "error": f"Customer '{customer_name}' not found"
        }

    invoices = []

    total_invoiced: float = 0.0
    total_paid: float = 0.0
    total_due: float = 0.0

    for match in matches:
        metadata = match.get("metadata", {})

        total = float(metadata.get("total") or 0)
        amount_paid = float(metadata.get("amount_paid") or 0)
        amount_due = float(metadata.get("amount_due") or 0)

        total_invoiced += total
        total_paid += amount_paid
        total_due += amount_due

        invoices.append({
            "invoice_number": metadata.get("invoice_number"),
            "total": total,
            "amount_paid": amount_paid,
            "amount_due": amount_due,
            "currency": metadata.get("currency"),
            "invoice_date": metadata.get("invoice_date"),
            "due_date": metadata.get("due_date"),
            "payment_status": metadata.get("payment_status"),
            "collection_status": metadata.get("collection_status"),
            "risk_level": metadata.get("risk_level"),
            "days_overdue": metadata.get("days_overdue"),
        })

    return {
        "customer": customer_name,
        "invoice_count": len(invoices),
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "total_due": total_due,
        "invoices": invoices,
    }

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0,
)

agent = create_agent(
    model=llm,
    tools=[get_customer],
)


result = agent.invoke({
    "messages": [
        {
            "role": "user",
            "content": "Can you find ganesh gnawali customer?"
        }
    ]
})


print(result["messages"][-1].content)