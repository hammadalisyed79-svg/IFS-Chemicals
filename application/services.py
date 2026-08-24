"""Application services — UI and API call these, not database directly."""

from __future__ import annotations

from domain.tenant import TenantContext, get_tenant
from infrastructure.cache.platform_cache import cached, invalidate_masters
from infrastructure.events.bus import publish_simple
from domain import events as E


class BaseService:
    def __init__(self, tenant: TenantContext | None = None):
        self.tenant = tenant or get_tenant()


class CustomerService(BaseService):
    def list_active(self):
        def _load():
            import database as db
            from application.tenant import get_scope, tenant_filter
            rows = db.get_customers(active_only=True)
            scope = get_scope()
            if scope.enforce:
                return [r for r in rows if int(r.get("company_id") or 1) == scope.company_id]
            return rows
        return cached("master:customers", _load)

    def get(self, customer_id: int):
        from application.tenant import validate_row
        return validate_row(__import__("database").get_customer(customer_id), table="customers")

    def create(self, data: dict, user_id: int | None = None) -> int:
        db = __import__("database")
        rid = db.add_customer(data, created_by=user_id)
        invalidate_masters()
        publish_simple(E.CUSTOMER_CREATED, aggregate_type="customer", aggregate_id=rid, user_id=user_id,
                       company_id=self.tenant.company_id, payload={"code": data.get("code")})
        return rid


class SupplierService(BaseService):
    def list_active(self):
        return cached("master:suppliers", lambda: __import__("database").get_suppliers(active_only=True))

    def get(self, supplier_id: int):
        return __import__("database").get_supplier(supplier_id)

    def create(self, data: dict, user_id: int | None = None) -> int:
        db = __import__("database")
        rid = db.add_supplier(data, created_by=user_id)
        invalidate_masters()
        publish_simple(E.SUPPLIER_CREATED, aggregate_type="supplier", aggregate_id=rid, user_id=user_id)
        return rid


class ProductService(BaseService):
    def list_active(self):
        return cached("master:products", lambda: __import__("database").get_items(active_only=True))

    def get(self, product_id: int):
        return __import__("database").get_item(product_id)


class InventoryService(BaseService):
    def stock_report(self):
        return cached("master:inventory", lambda: __import__("database").get_inventory())


class SalesService(BaseService):
    def list_invoices(self, **kwargs):
        from db_v3 import search_sales_invoices
        return search_sales_invoices(**kwargs)

    def get_invoice(self, invoice_id: int):
        return __import__("database").get_sale(invoice_id)


class PurchaseService(BaseService):
    def list_invoices(self, **kwargs):
        from db_v3 import search_purchase_invoices
        return search_purchase_invoices(**kwargs)


class FinanceService(BaseService):
    def trial_balance(self, from_date=None, to_date=None):
        from db_v3 import get_trial_balance
        return get_trial_balance(from_date, to_date)


class ProductionService(BaseService):
    def list_orders(self):
        from db_v3 import get_production_orders
        return get_production_orders()


class HRService(BaseService):
    def list_employees(self):
        import db_hr
        return db_hr.get_employees()


class PortalService(BaseService):
    def catalog(self, user: dict):
        from erp_core import portal_service as ps
        return ps.get_catalog(user)

    def submit_order(self, user: dict, cart: list, notes: str = ""):
        from erp_core import portal_service as ps
        oid = ps.create_portal_order(user, cart, notes=notes, submit=True)
        publish_simple(E.PORTAL_ORDER_SUBMITTED, aggregate_type="portal_order", aggregate_id=oid, user_id=user.get("id"))
        return oid


class NotificationService(BaseService):
    def for_user(self, user_id: int, unread_only: bool = False):
        from erp_core import notifications as ntf
        return ntf.get_notifications_for_user(user_id, unread_only=unread_only)


class CompanyService(BaseService):
    def list_companies(self):
        from database import get_connection, rows_to_list
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                "SELECT * FROM erp_companies WHERE is_active=1 ORDER BY name"
            ).fetchall())

    def list_branches(self, company_id: int | None = None):
        from database import get_connection, rows_to_list
        cid = company_id or self.tenant.company_id
        with get_connection() as conn:
            return rows_to_list(conn.execute(
                "SELECT * FROM erp_branches WHERE company_id=? AND is_active=1 ORDER BY name", (cid,)
            ).fetchall())
