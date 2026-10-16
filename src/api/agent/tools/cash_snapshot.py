from collections import defaultdict
from datetime import date

from langchain_core.tools import tool
from sqlalchemy import select

from src.db.database import SessionLocal
from src.db.schema.xero_sync import XeroInvoiceRecord

_TOP_CUSTOMERS = 5


def _payload_value(payload: dict, *keys):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def collection_status(
    xero_status: str | None, amount_due: float, due_date_string: str | None
) -> str:
    status = (xero_status or "").upper()
    if status in {"DRAFT", "VOIDED", "DELETED"}:
        return status
    if amount_due <= 0:
        return "PAID"
    if not due_date_string:
        return "OPEN"
    try:
        due_date = date.fromisoformat(str(due_date_string)[:10])
    except ValueError:
        return "OPEN"
    days_until_due = (due_date - date.today()).days
    if days_until_due < 0:
        return "OVERDUE"
    if days_until_due == 0:
        return "DUE_TODAY"
    if days_until_due <= 7:
        return "DUE_SOON"
    return "OPEN"


def build_cash_snapshot(top_n: int = _TOP_CUSTOMERS) -> dict:
    overdue_total = 0.0
    due_this_week_total = 0.0
    currency = "GBP"
    counts = {
        "overdue": 0,
        "due_today": 0,
        "due_soon": 0,
        "paid": 0,
        "open": 0,
    }
    by_customer: dict[str, dict] = defaultdict(
        lambda: {"amount_due": 0.0, "overdue_count": 0}
    )

    with SessionLocal() as db:
        rows = db.execute(
            select(XeroInvoiceRecord).where(XeroInvoiceRecord.deleted.is_(False))
        ).scalars()
        for row in rows:
            payload = row.payload or {}
            amount_due = float(
                _payload_value(payload, "amount_due", "AmountDue") or 0
            )
            due_date = str(_payload_value(payload, "due_date", "DueDate") or "")
            status = collection_status(row.status, amount_due, due_date)
            code = _payload_value(payload, "currency_code", "CurrencyCode")
            if code:
                currency = str(code)
            contact = payload.get("contact") or payload.get("Contact") or {}
            customer = str(
                _payload_value(contact, "name", "Name") or "Unknown"
            ).strip() or "Unknown"

            if status == "OVERDUE":
                overdue_total += amount_due
                counts["overdue"] += 1
                by_customer[customer]["amount_due"] += amount_due
                by_customer[customer]["overdue_count"] += 1
            elif status == "DUE_TODAY":
                due_this_week_total += amount_due
                counts["due_today"] += 1
                by_customer[customer]["amount_due"] += amount_due
            elif status == "DUE_SOON":
                due_this_week_total += amount_due
                counts["due_soon"] += 1
                by_customer[customer]["amount_due"] += amount_due
            elif status == "PAID":
                counts["paid"] += 1
            elif status == "OPEN":
                counts["open"] += 1
                if amount_due > 0:
                    by_customer[customer]["amount_due"] += amount_due

    top_customers = [
        {
            "customer": name,
            "amount_due": round(values["amount_due"], 2),
            "overdue_count": values["overdue_count"],
        }
        for name, values in sorted(
            by_customer.items(),
            key=lambda item: item[1]["amount_due"],
            reverse=True,
        )
        if values["amount_due"] > 0
    ][:top_n]

    return {
        "overdue_total": round(overdue_total, 2),
        "due_this_week_total": round(due_this_week_total, 2),
        "currency": currency,
        "invoice_count": counts,
        "top_customers": top_customers,
    }


@tool
def get_cash_snapshot() -> dict:
    """Cash snapshot: overdue total, amount due this week, and who owes the most.

    Use this for portfolio questions, not for a single invoice.
    """

    return build_cash_snapshot()
