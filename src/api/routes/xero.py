from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from src.api.xero.auth import (
    begin_oauth,
    complete_oauth_callback,
    get_connection_status,
    get_oauth_setup,
)
from src.api.xero.config import LOGIN_PATH, LOGIN_URL_PATH
from src.api.xero.contacts import fetch_contacts
from src.api.xero.exceptions import XeroNotConnectedError
from src.api.xero import token_store

router = APIRouter(prefix="/xero", tags=["Xero"])


def _not_connected_response(exc: XeroNotConnectedError) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "message": str(exc),
            "login_url": LOGIN_PATH,
            "login_url_api": LOGIN_URL_PATH,
        },
    )


@router.get("/login")
def login():
    """Browser: redirects to Xero. Do not call from Swagger (use GET /xero/login/url)."""
    try:
        authorize_url = begin_oauth()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(authorize_url)


@router.get("/login/url")
def login_url():
    """Swagger-safe: returns authorize_url to open in a browser tab."""
    try:
        authorize_url = begin_oauth()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "authorize_url": authorize_url,
        "instruction": "Paste authorize_url into a new browser tab.",
    }


@router.get("/callback")
def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(status_code=400, detail=f"Xero login failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")
    if not token_store.verify_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    try:
        complete_oauth_callback(code)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/xero/status")


@router.get("/status")
def status():
    return get_connection_status()


@router.get("/setup")
def oauth_setup():
    return get_oauth_setup()


@router.get("/contacts")
def get_contacts(page: int = 1, page_size: int = 100):
    try:
        return fetch_contacts(page=page, page_size=page_size)
    except XeroNotConnectedError as exc:
        raise _not_connected_response(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
