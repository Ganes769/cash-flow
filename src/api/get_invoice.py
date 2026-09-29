import json
import os

from dotenv import load_dotenv
from xero_python.accounting import AccountingApi
from xero_python.api_client import ApiClient, Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from xero_python.exceptions import AccountingBadRequestException

load_dotenv()
# ======================
# PUT YOUR CREDENTIALS HERE
# ======================
CLIENT_ID = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")

def get_xero_client():
    """Create and authenticate the Xero client"""
    api_client = ApiClient(
        Configuration(
            debug=False,
            oauth2_token=OAuth2Token(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET
            ),
        )
    )
    
    # Get access token (valid for ~30 minutes)
    token = api_client.get_client_credentials_token()
    print("✅ Access token obtained successfully")
    return api_client

def get_all_contacts(api_client):
    """Get all contacts (handles pagination)"""
    accounting_api = AccountingApi(api_client)
    all_contacts = []
    page = 1

    while True:
        try:
            response = accounting_api.get_contacts(
                xero_tenant_id='',          # empty for Custom Connection
                page=page,
                page_size=100
            )
            
            contacts = response.contacts
            if not contacts:
                break
                
            all_contacts.extend(contacts)
            print(f"📄 Fetched page {page} → {len(contacts)} contacts")
            
            if len(contacts) < 100:
                break
            page += 1
            
        except AccountingBadRequestException as e:
            print("❌ Error getting contacts:", e)
            break

    return all_contacts

def get_all_invoices(api_client):
    """Get all invoices (handles pagination)"""
    accounting_api = AccountingApi(api_client)
    all_invoices = []
    page = 1

    while True:
        try:
            response = accounting_api.get_invoices(
                xero_tenant_id='',          # empty for Custom Connection
                page=page,
                page_size=100
            )
            
            invoices = response.invoices
            if not invoices:
                break
                
            all_invoices.extend(invoices)
            print(f"📄 Fetched page {page} → {len(invoices)} invoices")
            
            if len(invoices) < 100:
                break
            page += 1
            
        except AccountingBadRequestException as e:
            print("❌ Error getting invoices:", e)
            break

    return all_invoices


