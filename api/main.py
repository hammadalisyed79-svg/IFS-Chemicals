"""IFS Industrial ERP — REST API v1 (V17 mature)."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from erp_version import APP_NAME, APP_VERSION_FULL
from security.jwt_auth import authenticate_user, create_access_token
from api.middleware import RateLimitMiddleware, RequestContextMiddleware
from api.deps import CustomerCreate, PaginatedResponse, get_current_user, pagination, oauth2_scheme
from pydantic import BaseModel

import database as db

db.init_db()

# Discover plugins at startup
try:
    from plugins.loader import discover_plugins
    discover_plugins()
except Exception:
    pass

app = FastAPI(
    title=f"{APP_NAME} API",
    description="V17 REST API — CRUD, pagination, webhooks, tenant isolation",
    version="1.1.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict
    trace_id: str | None = None


@app.post("/api/v1/auth/token", response_model=TokenResponse, tags=["Auth"])
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token({
        "sub": str(user["id"]), "username": user["username"], "role": user.get("role"),
    }))


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
def health():
    from infrastructure.observability.metrics import health_status
    from infrastructure.observability.tracing import get_trace_id
    h = health_status()
    return HealthResponse(status=h["status"], version=APP_VERSION_FULL, checks=h.get("checks", {}), trace_id=get_trace_id())


@app.get("/metrics", tags=["Observability"])
def prometheus_metrics():
    from fastapi.responses import PlainTextResponse
    from infrastructure.observability.prometheus import export_prometheus
    return PlainTextResponse(export_prometheus(), media_type="text/plain; version=0.0.4")


# --- Customers CRUD ---
@app.get("/api/v1/customers", tags=["Customers"])
def list_customers(user: dict = Depends(get_current_user), pg: dict = Depends(pagination)):
    from application.services import CustomerService
    rows = CustomerService().list_active()
    total = len(rows)
    start, end = pg["offset"], pg["offset"] + pg["page_size"]
    return PaginatedResponse(
        items=rows[start:end], total=total, page=pg["page"], page_size=pg["page_size"],
        pages=max(1, (total + pg["page_size"] - 1) // pg["page_size"]),
    )


@app.get("/api/v1/customers/{customer_id}", tags=["Customers"])
def get_customer(customer_id: int, user: dict = Depends(get_current_user)):
    from application.services import CustomerService
    from application.tenant import validate_row
    row = validate_row(CustomerService().get(customer_id), table="customers")
    if not row:
        raise HTTPException(404, "Not found")
    return row


@app.post("/api/v1/customers", tags=["Customers"], status_code=201)
def create_customer(body: CustomerCreate, user: dict = Depends(get_current_user)):
    from application.services import CustomerService
    from application.rules.engine import assert_rules
    data = body.model_dump()
    assert_rules("credit_limit", {"total": 0, "customer": data}, company_id=int(user.get("default_company_id") or 1))
    rid = CustomerService().create(data, user_id=user["id"])
    return {"id": rid}


@app.put("/api/v1/customers/{customer_id}", tags=["Customers"])
def update_customer(customer_id: int, body: CustomerCreate, user: dict = Depends(get_current_user)):
    from application.tenant import validate_row
    from application.services import CustomerService
    row = validate_row(CustomerService().get(customer_id), table="customers")
    if not row:
        raise HTTPException(404, "Not found")
    db.update_customer(customer_id, body.model_dump(), modified_by=user["id"])
    from infrastructure.cache.platform_cache import invalidate_masters
    invalidate_masters()
    return {"ok": True}


@app.delete("/api/v1/customers/{customer_id}", tags=["Customers"])
def delete_customer(customer_id: int, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    from application.services import CustomerService
    from application.tenant import validate_row
    if not validate_row(CustomerService().get(customer_id), table="customers"):
        raise HTTPException(404, "Not found")
    with db.get_connection() as conn:
        conn.execute("UPDATE customers SET is_active=0 WHERE id=?", (customer_id,))
    return {"ok": True}


# --- Read endpoints (existing) ---
@app.get("/api/v1/suppliers", tags=["Suppliers"])
def api_suppliers(user: dict = Depends(get_current_user)):
    from application.services import SupplierService
    return SupplierService().list_active()


@app.get("/api/v1/products", tags=["Products"])
def api_products(user: dict = Depends(get_current_user)):
    from application.services import ProductService
    return ProductService().list_active()


@app.get("/api/v1/inventory", tags=["Inventory"])
def api_inventory(user: dict = Depends(get_current_user)):
    from application.services import InventoryService
    return InventoryService().stock_report()


@app.get("/api/v1/sales/invoices", tags=["Sales"])
def api_sales_invoices(user: dict = Depends(get_current_user), pg: dict = Depends(pagination)):
    from application.services import SalesService
    return SalesService().list_invoices(page=pg["page"], page_size=pg["page_size"])


@app.get("/api/v1/purchase/invoices", tags=["Purchase"])
def api_purchase_invoices(user: dict = Depends(get_current_user), pg: dict = Depends(pagination)):
    from application.services import PurchaseService
    return PurchaseService().list_invoices(page=pg["page"], page_size=pg["page_size"])


@app.get("/api/v1/finance/trial-balance", tags=["Finance"])
def api_trial_balance(user: dict = Depends(get_current_user)):
    from application.services import FinanceService
    return FinanceService().trial_balance()


@app.get("/api/v1/production/orders", tags=["Production"])
def api_production(user: dict = Depends(get_current_user)):
    from application.services import ProductionService
    return ProductionService().list_orders()


@app.get("/api/v1/hr/employees", tags=["HR"])
def api_hr(user: dict = Depends(get_current_user)):
    from application.services import HRService
    return HRService().list_employees()


@app.get("/api/v1/notifications", tags=["Notifications"])
def api_notifications(user: dict = Depends(get_current_user), unread_only: bool = False):
    from application.services import NotificationService
    return NotificationService().for_user(user["id"], unread_only=unread_only)


@app.get("/api/v1/companies", tags=["Multi-Company"])
def api_companies(user: dict = Depends(get_current_user)):
    from application.services import CompanyService
    return CompanyService().list_companies()


@app.get("/api/v1/rules", tags=["Rules"])
def api_rules(user: dict = Depends(get_current_user), category: str | None = None):
    from application.rules.engine import list_rules
    return list_rules(category, company_id=int(user.get("default_company_id") or 1))


@app.get("/api/v1/workflows", tags=["Workflows"])
def api_workflows(user: dict = Depends(get_current_user)):
    from application.workflows.designer import list_workflows
    return list_workflows(company_id=int(user.get("default_company_id") or 1))


@app.get("/api/v1/plugins", tags=["Plugins"])
def api_plugins(user: dict = Depends(get_current_user)):
    from plugins.loader import discover_plugins
    from plugins.sdk import REGISTRY
    discover_plugins()
    return [{"id": p.manifest.plugin_id, "name": p.manifest.name} for p in REGISTRY.plugins.values()]


@app.get("/api/v1/tenant/coverage", tags=["Multi-Company"])
def api_tenant_coverage(user: dict = Depends(get_current_user)):
    from application.tenant import coverage_report
    return coverage_report()


@app.post("/api/v1/webhooks", tags=["Webhooks"])
def register_webhook(url: str, event_types: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    with db.get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO erp_webhooks(name,url,event_types,company_id) VALUES(?,?,?,?)",
            (url[:50], url, event_types, int(user.get("default_company_id") or 1)),
        )
        return {"id": cur.lastrowid}


@app.post("/api/v1/jobs/process", tags=["Jobs"])
def api_process_jobs(user: dict = Depends(get_current_user), limit: int = 10):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    from infrastructure.jobs.worker import process_jobs
    return {"processed": process_jobs(limit)}
