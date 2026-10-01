from xero_python.accounting import AccountingApi
from xero_python.exceptions import HTTPStatusException

from src.api.xero.auth import get_authenticated_client
from src.api.xero import sync as xero_sync


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

    contacts = [contact.to_dict() for contact in (response.contacts or [])]
    stored = xero_sync.upsert_contacts(tenant_id, contacts)
    return {
        "count": len(contacts),
        "stored": stored,
        "contacts": contacts,
    }


def as_synced_contact(contact: dict) -> dict:
    return {
        "id": str(contact.get("ContactID") or contact.get("contact_id") or ""),
        "name": contact.get("Name") or contact.get("name"),
        "email": contact.get("EmailAddress") or contact.get("email_address"),
        "deleted": False,
        "updated_at": contact.get("UpdatedDateUTC") or contact.get("updated_date_utc"),
        "payload": contact,
    }


def refresh_synced_contacts() -> list[dict]:
    _, tenant_id = get_authenticated_client()
    items = []
    keep_ids: set[str] = set()
    completed = False
    for page in range(1, 21):
        batch = fetch_contacts(page=page, page_size=100)
        contacts = batch.get("contacts") or []
        for contact in contacts:
            row = as_synced_contact(contact)
            if row["id"]:
                items.append(row)
                keep_ids.add(row["id"])
        if len(contacts) < 100:
            completed = True
            break
    if completed:
        xero_sync.prune_contacts(tenant_id, keep_ids)
    return items
