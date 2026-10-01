import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.routes.xero import router as xero_router
from src.api.xero.realtime import realtime_loop
from src.db.database import get_db, init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    stop = asyncio.Event()
    task = asyncio.create_task(realtime_loop(stop))
    yield
    stop.set()
    await task


app = FastAPI(title="Cashflow Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://cash-flow-5gdu.onrender.com",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://localhost:5190",
        "http://127.0.0.1:5190",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(xero_router)


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Cashflow Agent API",
        "database": "Supabase PostgreSQL",
        "xero_login": "/xero/login",
        "xero_login_url": "/xero/login/url",
        "xero_status": "/xero/status",
        "xero_contacts": "/xero/contacts",
        "xero_invoices": "/xero/invoices",
        "xero_webhooks": "/xero/webhooks",
        "xero_sync": "/xero/sync",
        "xero_synced_contacts": "/xero/synced/contacts",
        "xero_synced_invoices": "/xero/synced/invoices",
    }


@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "Supabase PostgreSQL",
        "result": result.scalar(),
    }
