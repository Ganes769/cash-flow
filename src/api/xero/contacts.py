from xero_python.accounting import AccountingApi
from xero_python.exceptions import HTTPStatusException

from src.api.xero.auth import get_authenticated_client


def fetch_contacts(page: int = 1, page_size: int = 100) -> dict:
    api_client, tenant_id = get_authenticated_client()
    accounting_api = AccountingApi(api_client)

    try:
        response = accounting_api.get_contacts(
            xero_tenant_id=tenant_id,
            page=page,
            page_size=page_size,
        )
    except HTTPStatusException as exc:
        if exc.status == 403:
            raise RuntimeError(
                "Xero returned 403. Reconnect at /xero/login and ensure the Web app "
                "has accounting.contacts.read scope."
            ) from exc
        raise

    contacts = response.contacts or []
    return {
        "count": len(contacts),
        "contacts": [contact.to_dict() for contact in contacts],
    }
