from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.xero import router as xero_router

app = FastAPI(title="Cashflow Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(xero_router)


@app.get("/")
def root():
    return {
        "xero_login": "/xero/login",
        "xero_login_url": "/xero/login/url",
        "xero_status": "/xero/status",
        "xero_contacts": "/xero/contacts",
    }
