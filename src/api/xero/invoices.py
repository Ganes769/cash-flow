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

    invoices = [invoice.to_dict() for invoice in (response.invoices or [])]
    stored = xero_sync.upsert_invoices(tenant_id, invoices)
    return {
        "count": len(invoices),
        "stored": stored,
        "invoices": invoices,
    }
