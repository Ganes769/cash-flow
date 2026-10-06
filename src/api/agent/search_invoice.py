# src/ai/search_invoices.py

import os

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from pinecone import Pinecone

load_dotenv()



PINECONE_API_KEY = os.getenv(
    "PINECONE_API_KEY"
)

PINECONE_INDEX_NAME = os.getenv(
    "PINECONE_INDEX_NAME"
)


embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)




pc = Pinecone(
    api_key=PINECONE_API_KEY
)

index = pc.Index(
    PINECONE_INDEX_NAME
)


def search_invoices(
    question: str,
    collection_status: str | None = None,
    payment_status: str | None = None,
    risk_level: str | None = None,
    top_k: int = 10,
    customer_name: str | None = None,
    email: str | None = None,
):
    """Search indexed invoices using a question and optional status or risk filters."""


    query_vector = embeddings.embed_query(
        question
    )


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


    query_args = {
        "vector": query_vector,

        "top_k": top_k,

        "include_metadata": True,
    }


    if email:
       filters["email"] = email

    if filters:

        query_args["filter"] = filters

    results = index.query(
        **query_args
    )

    return results



