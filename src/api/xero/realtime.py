import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.api.xero.config import SYNC_INTERVAL_SECONDS
from src.api.xero.contacts import fetch_contacts, refresh_synced_contacts
from src.api.xero.exceptions import XeroNotConnectedError
from src.api.xero.invoices import fetch_invoices, refresh_synced_invoices
from src.db.database import SessionLocal
from src.db.schema.xero_sync import XeroContactRecord, XeroInvoiceRecord

logger = logging.getLogger(__name__)

_poll_lock = threading.Lock()
_last_sync: dict = {
    "status": "idle",
    "mode": None,
    "contacts_stored": 0,
    "invoices_stored": 0,
    "finished_at": None,
    "error": None,
}


def last_sync_status() -> dict:
    return dict(_last_sync)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _latest(model) -> datetime | None:
    with SessionLocal() as db:
        value = db.execute(select(func.max(model.updated_at))).scalar()
    return _aware(value)


def _since_for(model) -> datetime | None:
    latest = _latest(model)
    if latest is None:
        return None
    return latest - timedelta(minutes=2)


def _pull_changed(fetch_fn, since: datetime | None) -> int:
    stored = 0
    for page in range(1, 21):
        batch = fetch_fn(page=page, page_size=100, if_modified_since=since)
        stored += int(batch.get("stored") or 0)
        if int(batch.get("count") or 0) < 100:
            break
    return stored


def run_sync(full: bool = False) -> dict:
    result = {
        "status": "ok",
        "mode": "full" if full else "changed",
        "contacts_stored": 0,
        "invoices_stored": 0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }
    try:
        contact_since = None if full else _since_for(XeroContactRecord)
        invoice_since = None if full else _since_for(XeroInvoiceRecord)
        if contact_since is None:
            result["contacts_stored"] = len(refresh_synced_contacts())
        else:
            result["contacts_stored"] = _pull_changed(fetch_contacts, contact_since)
        if invoice_since is None:
            result["invoices_stored"] = len(refresh_synced_invoices())
        else:
            result["invoices_stored"] = _pull_changed(fetch_invoices, invoice_since)
    except XeroNotConnectedError as exc:
        result["status"] = "skipped"
        result["error"] = str(exc)
        raise
    except Exception as exc:
        logger.exception("Xero sync failed")
        result["status"] = "error"
        result["error"] = str(exc)
        raise
    finally:
        _last_sync.update(result)
    return result


def start_sync(full: bool = False) -> None:
    threading.Thread(target=_run_sync_safe, kwargs={"full": full}, daemon=True).start()


def _run_sync_safe(full: bool = False) -> None:
    if not _poll_lock.acquire(blocking=full):
        return
    try:
        run_sync(full=full)
    except XeroNotConnectedError:
        return
    except Exception:
        logger.exception("Background Xero sync failed")
    finally:
        _poll_lock.release()


async def realtime_loop(stop: asyncio.Event) -> None:
    await asyncio.sleep(3)
    while not stop.is_set():
        await asyncio.to_thread(_run_sync_safe, False)
        try:
            await asyncio.wait_for(stop.wait(), timeout=SYNC_INTERVAL_SECONDS)
        except TimeoutError:
            continue
