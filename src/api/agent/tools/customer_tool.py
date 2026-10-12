from langchain_core.tools import tool
from sqlalchemy import func, select

from src.db.database import SessionLocal
from src.db.schema.xero_sync import XeroContactRecord, XeroInvoiceRecord


def _payload_value(payload: dict, *keys):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _contact_name(payload: dict) -> str:
    contact = payload.get("contact") or payload.get("Contact") or {}
    return str(_payload_value(contact, "name", "Name") or "").strip()


@tool
def get_customer(customer_name: str) -> dict:
    """Retrieve a customer's email, contact details, and invoice history.

    Call this after get_invoice, using the customer name from that invoice.
    """

    name = (customer_name or "").strip()
    if not name:
        return {"error": "Customer name is required"}

    with SessionLocal() as db:
        contact = db.execute(
            select(XeroContactRecord).where(
                XeroContactRecord.deleted.is_(False),
                func.lower(XeroContactRecord.name) == name.lower(),
            )
        ).scalars().first()
        if contact is None:
            contact = db.execute(
                select(XeroContactRecord).where(
                    XeroContactRecord.deleted.is_(False),
                    XeroContactRecord.name.ilike(f"%{name}%"),
                )
            ).scalars().first()
        if contact is None:
            return {"error": f"Customer '{name}' not found"}

        payload = contact.payload or {}
        invoices = []
        total_invoiced = 0.0
        total_paid = 0.0
        total_due = 0.0
        for row in db.execute(
            select(XeroInvoiceRecord).where(XeroInvoiceRecord.deleted.is_(False))
        ).scalars():
            invoice_payload = row.payload or {}
            if _contact_name(invoice_payload).lower() != (contact.name or "").lower():
                continue
            total = float(_payload_value(invoice_payload, "total", "Total") or 0)
            amount_paid = float(
                _payload_value(invoice_payload, "amount_paid", "AmountPaid") or 0
            )
            amount_due = float(
                _payload_value(invoice_payload, "amount_due", "AmountDue") or 0
            )
            total_invoiced += total
            total_paid += amount_paid
            total_due += amount_due
            invoices.append(
                {
                    "invoice_number": row.invoice_number,
                    "total": total,
                    "amount_paid": amount_paid,
                    "amount_due": amount_due,
                    "currency": _payload_value(
                        invoice_payload, "currency_code", "CurrencyCode"
                    )
                    or "GBP",
                    "invoice_date": str(
                        _payload_value(invoice_payload, "date", "Date") or ""
                    ),
                    "due_date": str(
                        _payload_value(invoice_payload, "due_date", "DueDate") or ""
                    ),
                    "xero_status": row.status,
                }
            )

        return {
            "customer": contact.name,
            "email": contact.email
            or _payload_value(payload, "email_address", "EmailAddress"),
            "invoice_count": len(invoices),
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_due": total_due,
            "invoices": invoices,
        }
