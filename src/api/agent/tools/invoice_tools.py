from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.tools import tool
from src.api.agent.search_invoice import search_invoices

load_dotenv()
import os

from langchain_groq import ChatGroq


@tool
def get_invoice(invoice_number: str) -> dict:
    """Retrieve an exact invoice by invoice number."""

    results = search_invoices(
        question=invoice_number,
        top_k=10,
    )

    normalized_invoice_number = str(invoice_number).strip().lower()

    matching_invoice = None
    for match in results.matches:
        metadata = match.metadata or {}
        if str(metadata.get("invoice_number", "")).strip().lower() == normalized_invoice_number:
            matching_invoice = metadata
            break

    if matching_invoice is None:
        return {
            "error": f"Invoice {invoice_number} not found"
        }

    return {
        "invoice_number": matching_invoice.get("invoice_number"),
        "customer": matching_invoice.get("customer"),
        "total": matching_invoice.get("total"),
        "amount_paid": matching_invoice.get("amount_paid"),
        "amount_due": matching_invoice.get("amount_due"),
        "currency": matching_invoice.get("currency"),
        "invoice_date": matching_invoice.get("invoice_date"),
        "due_date": matching_invoice.get("due_date"),
        "payment_status": matching_invoice.get("payment_status"),
        "collection_status": matching_invoice.get("collection_status"),
        "risk_level": matching_invoice.get("risk_level"),
        "xero_status": matching_invoice.get("xero_status"),
    }

