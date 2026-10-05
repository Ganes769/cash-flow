import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

client = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0,
)


def generate_invoice_answer(question: str, results) -> str:

    invoices = []

    for match in results.matches:

        metadata = match.metadata

        invoices.append({
            "invoice_number": metadata.get("invoice_number"),
            "customer": metadata.get("customer"),
            "total": metadata.get("total"),
            "amount_paid": metadata.get("amount_paid"),
            "amount_due": metadata.get("amount_due"),
            "currency": metadata.get("currency"),
            "invoice_date": metadata.get("invoice_date"),
            "due_date": metadata.get("due_date"),
            "collection_status": metadata.get("collection_status"),
            "payment_status": metadata.get("payment_status"),
            "days_overdue": metadata.get("days_overdue"),
            "risk_level": metadata.get("risk_level"),
        })

    prompt = f"""
You are a business cashflow assistant.

Answer the user's question using ONLY the invoice data provided below.

User question:
{question}

Invoice data:
{invoices}

Instructions:

1. Give a direct answer first.
2. State how many invoices were found.
3. For each invoice provide:
   - Invoice number
   - Customer
   - Total amount
   - Amount paid
   - Amount due
   - Invoice date
   - Due date
   - Payment status
   - Risk level
4. Format the answer clearly.
5. Use £ when currency is GBP.
6. Do not invent information.
7. If information is missing, say "Not available".
8. At the end, provide a short summary of the total invoice value,
   total paid and total outstanding.
"""

    response = client.invoke(prompt)

    return response.content.strip()