# src/ai/search_invoices.py

import os

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone

load_dotenv()


# ============================================================
# ENV
# ============================================================

PINECONE_API_KEY = os.getenv(
    "PINECONE_API_KEY"
)

PINECONE_INDEX_NAME = os.getenv(
    "PINECONE_INDEX_NAME"
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
# SEARCH FUNCTION
# ============================================================

def search_invoices(
    question: str,
    collection_status: str | None = None,
    payment_status: str | None = None,
    risk_level: str | None = None,
    top_k: int = 10,
):

    # -----------------------------------------
    # Create embedding
    # -----------------------------------------

    query_vector = embeddings.embed_query(
        question
    )

    # -----------------------------------------
    # Build metadata filter
    # -----------------------------------------

    filters = {}

    if collection_status:

        filters[
            "collection_status"
        ] = collection_status

    if payment_status:

        filters[
            "payment_status"
        ] = payment_status

    if risk_level:

        filters[
            "risk_level"
        ] = risk_level

    # -----------------------------------------
    # Query
    # -----------------------------------------

    query_args = {
        "vector": query_vector,

        "top_k": top_k,

        "include_metadata": True,
    }

    if filters:

        query_args["filter"] = filters

    results = index.query(
        **query_args
    )

    return results


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    results = search_invoices(

        question=(
            "Which invoices are paid?"
        ),

        collection_status="PAID",

        top_k=10,
    )

    print(
        "\n===================================="
    )

    print(
        "OVERDUE INVOICES"
    )

    print(
        "====================================\n"
    )

    matches = results.get(
        "matches",
        []
    )

    if not matches:

        print(
            "No overdue invoices found."
        )

    for match in matches:

        metadata = match["metadata"]

        print("------------------------------------")

        print(
            f"Score: "
            f"{match['score']:.4f}"
        )

        print(
            f"Invoice: "
            f"{metadata.get('invoice_number')}"
        )

        print(
            f"Customer: "
            f"{metadata.get('customer')}"
        )

        print(
            f"Total: "
            f"£{metadata.get('total')}"
        )

        print(
            f"Paid: "
            f"£{metadata.get('amount_paid')}"
        )

        print(
            f"Due: "
            f"£{metadata.get('amount_due')}"
        )

        print(
            f"Payment Status: "
            f"{metadata.get('payment_status')}"
        )

        print(
            f"Collection Status: "
            f"{metadata.get('collection_status')}"
        )

        print(
            f"Risk: "
            f"{metadata.get('risk_level')}"
        )

        print(
            f"Days Overdue: "
            f"{metadata.get('days_overdue')}"
        )