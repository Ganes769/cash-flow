from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.db.database import get_db
from src.api.routes.xero import router as xero_router

app = FastAPI(title="Cashflow Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://localhost:5190",
        "http://localhost:5191",
        "http://127.0.0.1:5190",
        "http://127.0.0.1:5191",
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
    }
@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "Supabase PostgreSQL",
        "result": result.scalar(),
    }