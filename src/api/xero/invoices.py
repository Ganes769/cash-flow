from xero_python.accounting import AccountingApi
from xero_python.exceptions import HTTPStatusException

from src.api.xero.auth import get_authenticated_client
from src.api.xero import sync as xero_sync


def fetch_invoices(page: int = 1, page_size: int = 100) -> dict:
    api_client, tenant_id = get_authenticated_client()
    accounting_api = AccountingApi(api_client)

    try:
        response = accounting_api.get_invoices(
            xero_tenant_id=tenant_id,
            page=page,
            page_size=page_size,
        )
    except HTTPStatusException as exc:
        if exc.status == 403:
            raise RuntimeError(
                "Xero returned 403. Reconnect at /xero/login and ensure the Web app "
                "has accounting.transactions.read scope."
            ) from exc
        raise

    invoices = [
        xero_sync._json_safe(invoice.to_dict())
        for invoice in (response.invoices or [])
    ]
    try:
        stored = xero_sync.upsert_invoices(tenant_id, invoices)
    except Exception:
        stored = 0
    return {
        "count": len(invoices),
        "stored": stored,
        "invoices": invoices,
    }


def as_synced_invoice(invoice: dict) -> dict:
    return {
        "id": str(invoice.get("InvoiceID") or invoice.get("invoice_id") or ""),
        "invoice_number": invoice.get("InvoiceNumber") or invoice.get("invoice_number"),
        "status": invoice.get("Status") or invoice.get("status"),
        "deleted": False,
        "updated_at": invoice.get("UpdatedDateUTC") or invoice.get("updated_date_utc"),
        "payload": invoice,
    }


def refresh_synced_invoices() -> list[dict]:
    _, tenant_id = get_authenticated_client()
    items = []
    keep_ids: set[str] = set()
    completed = False
    for page in range(1, 21):
        batch = fetch_invoices(page=page, page_size=100)
        invoices = batch.get("invoices") or []
        for invoice in invoices:
            row = as_synced_invoice(invoice)
            if row["id"]:
                items.append(row)
                keep_ids.add(row["id"])
        if len(invoices) < 100:
            completed = True
            break
    if completed:
        xero_sync.prune_invoices(tenant_id, keep_ids)
    return items
