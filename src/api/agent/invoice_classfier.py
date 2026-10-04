import os
from typing import Optional

from dotenv import load_dotenv
from invoice_answer import generate_invoice_answer
from langchain_groq import ChatGroq
from search_invoice import search_invoices

load_dotenv()

apikey = os.getenv("GROQ_API_KEY")

client = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=apikey,
    temperature=0,
)


def get_collection_status(question: str) -> Optional[str]:

    prompt = f"""
You are an invoice query classifier.

Determine the invoice status requested by the user.

Allowed statuses:
PAID
UNPAID
OVERDUE
OUTSTANDING
AUTHORISED
DRAFT
VOIDED
None

User question:
{question}

Rules:
- Return ONLY one status.
- If no status is requested, return None.
- paid invoices -> PAID
- unpaid invoices -> UNPAID
- late invoices -> OVERDUE
- past due invoices -> OVERDUE
- customers still owing money -> OUTSTANDING

Answer:
"""

    response = client.invoke(prompt)

    result = response.content.strip().upper()

    if result == "NONE":
        return None

    allowed_statuses = {
        "PAID",
        "UNPAID",
        "OVERDUE",
        "OUTSTANDING",
        "AUTHORISED",
        "DRAFT",
        "VOIDED",
    }

    if result in allowed_statuses:
        return result

    return None


question = "Which invoices are overdue?"

collection_status = get_collection_status(question)

print("Question:", question)
print("Detected status:", collection_status)

results = search_invoices(
    question=question,
    collection_status=collection_status,
    top_k=10,
)

answer = generate_invoice_answer(
    question=question,
    results=results,
)

print("\nANSWER:")
print(answer)