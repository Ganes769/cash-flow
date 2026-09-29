from fastapi import FastAPI

from src.api.get_invoice import (
    get_all_contacts,
    get_all_invoices,
    get_xero_client,
)

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Xero API is running"}


@app.get("/contacts")
def contacts():
    api_client = get_xero_client()

    contacts = get_all_contacts(api_client)

    return {
        "count": len(contacts),
        "contacts": [
            {
                "contact_id": contact.contact_id,
                "name": contact.name,
                "email": contact.email_address,
            }
            for contact in contacts
        ],
    }


@app.get("/invoices")
def invoices():
    api_client = get_xero_client()

    invoices = get_all_invoices(api_client)

    return {
        "count": len(invoices),
        "invoices": [
            {
                "invoice_id": invoice.invoice_id,
                "invoice_number": invoice.invoice_number,
                "type": invoice.type,
                "status": invoice.status,
            }
            for invoice in invoices
        ],
    }