# src/ai/embed_xero_invoices.py

import json
import os
from datetime import date

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone
from sqlalchemy import create_engine, text

# ============================================================
# ENV
# ============================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing")

if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY is missing")

if not PINECONE_INDEX_NAME:
    raise ValueError("PINECONE_INDEX_NAME is missing")


# ============================================================
# DATABASE
# ============================================================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# EMBEDDINGS
# ============================================================

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


# ============================================================
# PINECONE
# ============================================================

pc = Pinecone(
    api_key=PINECONE_API_KEY
)

index = pc.Index(
    PINECONE_INDEX_NAME
)


# ============================================================
# PAYMENT STATUS
# ============================================================

def calculate_payment_status(
    total: float,
    amount_paid: float,
    amount_due: float,
) -> str:

    if amount_due <= 0:
        return "PAID"

    if amount_paid > 0:
        return "PARTIALLY_PAID"

    return "UNPAID"


# ============================================================
# COLLECTION STATUS
# ============================================================

def calculate_collection_status(
    xero_status: str,
    amount_due: float,
    due_date_string: str | None,
) -> str:

    xero_status = (
        xero_status or ""
    ).upper()

    # -----------------------------------------
    # Xero lifecycle statuses
    # -----------------------------------------

    if xero_status == "DRAFT":
        return "DRAFT"

    if xero_status == "VOIDED":
        return "VOIDED"

    if xero_status == "DELETED":
        return "DELETED"

    # -----------------------------------------
    # Paid
    # -----------------------------------------

    if amount_due <= 0:
        return "PAID"

    # -----------------------------------------
    # No due date
    # -----------------------------------------

    if not due_date_string:
        return "OPEN"

    # -----------------------------------------
    # Parse due date
    # -----------------------------------------

    try:

        due_date = date.fromisoformat(
            due_date_string[:10]
        )

    except ValueError:

        return "OPEN"

    today = date.today()

    days_until_due = (
        due_date - today
    ).days

    # -----------------------------------------
    # Already overdue
    # -----------------------------------------

    if days_until_due < 0:
        return "OVERDUE"

    # -----------------------------------------
    # Due today
    # -----------------------------------------

    if days_until_due == 0:
        return "DUE_TODAY"

    # -----------------------------------------
    # Due within 7 days
    # -----------------------------------------

    if days_until_due <= 7:
        return "DUE_SOON"

    # -----------------------------------------
    # Future invoice
    # -----------------------------------------

    return "OPEN"


# ============================================================
# RISK LEVEL
# ============================================================

def calculate_risk_level(
    amount_due: float,
    collection_status: str,
    days_overdue: int,
) -> str:

    # Nothing outstanding
    if amount_due <= 0:
        return "LOW"

    # -----------------------------------------
    # High risk
    # -----------------------------------------

    if collection_status == "OVERDUE":

        if days_overdue > 30:
            return "HIGH"

        if amount_due >= 5000:
            return "HIGH"

        return "MEDIUM"

    # -----------------------------------------
    # Due soon
    # -----------------------------------------

    if collection_status == "DUE_TODAY":
        return "MEDIUM"

    if collection_status == "DUE_SOON":
        return "LOW"

    # -----------------------------------------
    # Normal open invoice
    # -----------------------------------------

    return "LOW"


# ============================================================
# CALCULATE ALL STATUS INFORMATION
# ============================================================

def calculate_statuses(payload: dict, database_status: str):

    xero_status = (
        payload.get("status")
        or database_status
        or ""
    ).upper()

    total = float(
        payload.get("total") or 0
    )

    amount_paid = float(
        payload.get("amount_paid") or 0
    )

    amount_due = float(
        payload.get("amount_due") or 0
    )

    due_date_string = (
        payload.get("due_date")
    )

    # -----------------------------------------
    # Payment status
    # -----------------------------------------

    payment_status = calculate_payment_status(
        total=total,
        amount_paid=amount_paid,
        amount_due=amount_due,
    )

    # -----------------------------------------
    # Collection status
    # -----------------------------------------

    collection_status = calculate_collection_status(
        xero_status=xero_status,
        amount_due=amount_due,
        due_date_string=due_date_string,
    )

    # -----------------------------------------
    # Days overdue
    # -----------------------------------------

    days_overdue = 0

    if (
        amount_due > 0
        and due_date_string
        and collection_status == "OVERDUE"
    ):

        try:

            due_date = date.fromisoformat(
                due_date_string[:10]
            )

            days_overdue = max(
                0,
                (date.today() - due_date).days
            )

        except ValueError:

            days_overdue = 0

    # -----------------------------------------
    # Risk
    # -----------------------------------------

    risk_level = calculate_risk_level(
        amount_due=amount_due,
        collection_status=collection_status,
        days_overdue=days_overdue,
    )

    return {
        "xero_status": xero_status,
        "payment_status": payment_status,
        "collection_status": collection_status,
        "risk_level": risk_level,
        "days_overdue": days_overdue,
    }


# ============================================================
# GET INVOICES
# ============================================================

def get_invoices():

    with engine.connect() as db:

        result = db.execute(
            text("""
                SELECT
                    id,
                    company_id,
                    tenant_id,
                    xero_invoice_id,
                    invoice_number,
                    status,
                    payload,
                    deleted,
                    updated_at
                FROM xero_invoices
            """)
        )

        return result.mappings().all()


# ============================================================
# CREATE INVOICE TEXT
# ============================================================

def invoice_to_text(
    invoice,
    statuses,
):

    payload = invoice["payload"] or {}

    contact = (
        payload.get("contact")
        or {}
    )

    customer_name = (
        contact.get("name")
        or "Unknown Customer"
    )

    invoice_number = (
        payload.get("invoice_number")
        or invoice["invoice_number"]
        or ""
    )

    invoice_date = (
        payload.get("date")
        or ""
    )

    due_date = (
        payload.get("due_date")
        or ""
    )

    total = float(
        payload.get("total") or 0
    )

    amount_paid = float(
        payload.get("amount_paid") or 0
    )

    amount_due = float(
        payload.get("amount_due") or 0
    )

    currency = (
        payload.get("currency_code")
        or "GBP"
    )

    # -----------------------------------------
    # Business-friendly text
    # -----------------------------------------

    business_text = f"""
Invoice Number: {invoice_number}

Customer: {customer_name}

Invoice Date: {invoice_date}

Due Date: {due_date}

Currency: {currency}

Total: {total}

Amount Paid: {amount_paid}

Amount Due: {amount_due}

Xero Status: {statuses["xero_status"]}

Payment Status: {statuses["payment_status"]}

Collection Status: {statuses["collection_status"]}

Risk Level: {statuses["risk_level"]}

Days Overdue: {statuses["days_overdue"]}

Complete Xero Invoice Data:

{json.dumps(
    payload,
    indent=2,
    ensure_ascii=False,
    default=str
)}
"""

    return business_text


# ============================================================
# CREATE VECTOR
# ============================================================

def create_vector(invoice):

    payload = invoice["payload"] or {}

    # -----------------------------------------
    # Calculate statuses
    # -----------------------------------------

    statuses = calculate_statuses(
        payload=payload,
        database_status=invoice["status"],
    )

    # -----------------------------------------
    # Customer
    # -----------------------------------------

    contact = (
        payload.get("contact")
        or {}
    )

    customer_name = (
        contact.get("name")
        or "Unknown Customer"
    )

    # -----------------------------------------
    # Financial values
    # -----------------------------------------

    total = float(
        payload.get("total") or 0
    )

    amount_paid = float(
        payload.get("amount_paid") or 0
    )

    amount_due = float(
        payload.get("amount_due") or 0
    )

    # -----------------------------------------
    # Text
    # -----------------------------------------

    invoice_text = invoice_to_text(
        invoice=invoice,
        statuses=statuses,
    )

    # -----------------------------------------
    # Embedding
    # -----------------------------------------

    vector = embeddings.embed_query(
        invoice_text
    )

    if len(vector) != 384:

        raise ValueError(
            f"Expected 384 dimensions, "
            f"got {len(vector)}"
        )

    # -----------------------------------------
    # Metadata
    # -----------------------------------------

    metadata = {

        "company_id": str(
            invoice["company_id"]
        ),

        "tenant_id": invoice["tenant_id"],

        "xero_invoice_id": (
            invoice["xero_invoice_id"]
        ),

        "invoice_number": (
            invoice["invoice_number"]
            or ""
        ),

        "customer": customer_name,

        # Xero
        "xero_status": statuses[
            "xero_status"
        ],

        # Payment
        "payment_status": statuses[
            "payment_status"
        ],

        # Collection
        "collection_status": statuses[
            "collection_status"
        ],

        # Risk
        "risk_level": statuses[
            "risk_level"
        ],

        # Dates
        "invoice_date": str(
            payload.get("date") or ""
        ),

        "due_date": str(
            payload.get("due_date") or ""
        ),

        # Financial
        "total": total,

        "amount_paid": amount_paid,

        "amount_due": amount_due,

        "days_overdue": statuses[
            "days_overdue"
        ],

        "currency": (
            payload.get("currency_code")
            or "GBP"
        ),
    }

    return {
        "id": str(invoice["id"]),

        "values": vector,

        "metadata": metadata,
    }


# ============================================================
# EMBED ALL
# ============================================================

def embed_all_invoices():

    invoices = get_invoices()

    print(
        f"\nFound {len(invoices)} invoices\n"
    )

    vectors = []

    for invoice in invoices:

        vector = create_vector(
            invoice
        )

        vectors.append(vector)

        metadata = vector["metadata"]

        print("------------------------------------")

        print(
            f"Invoice: "
            f"{metadata['invoice_number']}"
        )

        print(
            f"Customer: "
            f"{metadata['customer']}"
        )

        print(
            f"Total: "
            f"{metadata['currency']} "
            f"{metadata['total']}"
        )

        print(
            f"Paid: "
            f"{metadata['amount_paid']}"
        )

        print(
            f"Due: "
            f"{metadata['amount_due']}"
        )

        print(
            f"Xero status: "
            f"{metadata['xero_status']}"
        )

        print(
            f"Payment status: "
            f"{metadata['payment_status']}"
        )

        print(
            f"Collection status: "
            f"{metadata['collection_status']}"
        )

        print(
            f"Risk: "
            f"{metadata['risk_level']}"
        )

        print(
            f"Days overdue: "
            f"{metadata['days_overdue']}"
        )

    # -----------------------------------------
    # Upsert
    # -----------------------------------------

    if vectors:

        index.upsert(
            vectors=vectors
        )

    print("\n====================================")
    print(
        f"Uploaded {len(vectors)} invoices"
    )
    print("====================================")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    embed_all_invoices()