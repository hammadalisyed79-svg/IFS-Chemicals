"""V13.14 — unified transaction document framework."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DocumentSpec:
    """One transactional document type — shared lifecycle hooks."""

    key: str
    label: str
    table: str
    nav_group: str
    nav_screen: str
    no_field: str = "document_no"
    party_field: str | None = None
    search_fn: Callable[..., list] | None = None
    get_fn: Callable[[int], dict | None] | None = None
    save_fn: Callable | None = None
    delete_fn: Callable | None = None
    submit_fn: Callable | None = None
    approve_fn: Callable | None = None
    post_fn: Callable | None = None
    require_rate: bool = True
    party_kind: str = "sales"  # sales | purchase | stock | none
    editable_statuses: tuple[str, ...] = ("draft", "rejected", "open")


def _row_get(table: str, record_id: int) -> dict | None:
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
        return row_to_dict(row) if row else None


def _lazy_registry() -> dict[str, DocumentSpec]:
    import database as db
    import db_v3

    return {
        "sales_invoice": DocumentSpec(
            key="sales_invoice",
            label="Sales Invoice",
            table="sales_invoices",
            nav_group="Sales",
            nav_screen="Sales Invoices",
            no_field="document_no",
            party_field="customer_id",
            party_kind="sales",
            search_fn=db.search_sales_invoices,
            get_fn=db.get_sale,
            save_fn=db.save_sale,
            delete_fn=db.delete_sale,
            submit_fn=db.submit_sale_invoice,
            approve_fn=db.approve_sale_invoice,
        ),
        "purchase_invoice": DocumentSpec(
            key="purchase_invoice",
            label="Purchase Invoice",
            table="purchase_invoices",
            nav_group="Purchases",
            nav_screen="Purchase Invoices",
            party_field="supplier_id",
            party_kind="purchase",
            search_fn=db.search_purchases,
            get_fn=db.get_purchase,
            save_fn=db.save_purchase,
            delete_fn=db.delete_purchase,
            submit_fn=db.submit_purchase_invoice,
            approve_fn=db.approve_purchase_invoice,
        ),
        "sales_return": DocumentSpec(
            key="sales_return",
            label="Sales Return",
            table="sales_returns",
            nav_group="Sales",
            nav_screen="Sales Returns",
            no_field="document_no",
            party_field="customer_id",
            party_kind="sales",
            search_fn=db.search_sale_returns,
            get_fn=db.get_sale_return,
            save_fn=db.save_sale_return,
            delete_fn=db.delete_sale_return,
        ),
        "purchase_return": DocumentSpec(
            key="purchase_return",
            label="Purchase Return",
            table="purchase_returns",
            nav_group="Purchases",
            nav_screen="Purchase Returns",
            party_field="supplier_id",
            party_kind="purchase",
            search_fn=db.search_purchase_returns,
            get_fn=db.get_purchase_return,
            save_fn=db.save_purchase_return,
            delete_fn=db.delete_purchase_return,
        ),
        "sales_order": DocumentSpec(
            key="sales_order",
            label="Sales Order",
            table="sales_orders",
            nav_group="Sales",
            nav_screen="Sales Orders",
            party_field="customer_id",
            party_kind="sales",
            search_fn=db_v3.search_sales_orders,
            get_fn=db_v3.get_sales_order,
            save_fn=db_v3.save_sales_order,
            editable_statuses=("draft", "open", "rejected"),
        ),
        "purchase_order": DocumentSpec(
            key="purchase_order",
            label="Purchase Order",
            table="purchase_orders",
            nav_group="Purchases",
            nav_screen="Purchase Orders",
            party_field="supplier_id",
            party_kind="purchase",
            search_fn=db_v3.search_purchase_orders,
            get_fn=db_v3.get_purchase_order,
            save_fn=db_v3.save_purchase_order,
        ),
        "quotation": DocumentSpec(
            key="quotation",
            label="Quotation",
            table="quotations",
            nav_group="Sales",
            nav_screen="Quotations",
            party_field="customer_id",
            party_kind="sales",
            search_fn=db_v3.search_quotations,
            get_fn=db_v3.get_quotation,
            save_fn=db_v3.save_quotation,
        ),
        "delivery_note": DocumentSpec(
            key="delivery_note",
            label="Delivery Note",
            table="delivery_notes",
            nav_group="Sales",
            nav_screen="Delivery Notes",
            party_field="customer_id",
            party_kind="sales",
            search_fn=db_v3.search_delivery_notes,
            get_fn=lambda rid: _row_get("delivery_notes", rid),
            save_fn=db_v3.save_delivery_note,
            post_fn=db_v3.post_delivery_note,
        ),
        "purchase_requisition": DocumentSpec(
            key="purchase_requisition",
            label="Purchase Requisition",
            table="purchase_requisitions",
            nav_group="Purchases",
            nav_screen="Purchase Requisition",
            party_kind="none",
            search_fn=db_v3.search_purchase_requisitions,
            get_fn=db_v3.get_purchase_requisition,
            save_fn=db_v3.save_purchase_requisition,
        ),
        "grn": DocumentSpec(
            key="grn",
            label="GRN",
            table="goods_receipt_notes",
            nav_group="Purchases",
            nav_screen="GRN",
            party_field="supplier_id",
            party_kind="purchase",
            search_fn=db_v3.search_grns,
            get_fn=lambda rid: _row_get("goods_receipt_notes", rid),
            save_fn=db_v3.save_grn,
            post_fn=db_v3.post_grn,
        ),
        "journal_voucher": DocumentSpec(
            key="journal_voucher",
            label="Journal Voucher",
            table="journal_vouchers",
            nav_group="Finance",
            nav_screen="Journal Voucher",
            party_kind="none",
            search_fn=db_v3.search_journal_vouchers,
            get_fn=db_v3.get_journal_voucher,
            save_fn=db_v3.save_journal_voucher,
            post_fn=db_v3.post_journal_voucher,
            require_rate=False,
        ),
        "production_order": DocumentSpec(
            key="production_order",
            label="Production Order",
            table="production_orders",
            nav_group="Production",
            nav_screen="Production Orders",
            party_kind="none",
            search_fn=_search_production_orders,
            get_fn=db_v3.get_production_order,
            save_fn=db_v3.save_production_order,
            post_fn=db_v3.issue_production_materials if hasattr(db_v3, "issue_production_materials") else None,
            require_rate=False,
        ),
    }


def _search_production_orders(q=None, page=1, page_size=50, export_all=False):
    import db_v3
    from database import get_connection, rows_to_list

    like = f"%{(q or '').strip()}%"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(
            """SELECT po.*, p.name AS product_name FROM production_orders po
               LEFT JOIN products p ON p.id=po.finished_product_id
               WHERE po.document_no LIKE ? OR po.batch_no LIKE ? OR p.name LIKE ?
               ORDER BY po.order_date DESC LIMIT ?""",
            (like, like, like, page_size),
        ).fetchall())
    return rows if export_all else {"items": rows, "total": len(rows)}


_REGISTRY: dict[str, DocumentSpec] | None = None


def get_document_spec(key: str) -> DocumentSpec | None:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _lazy_registry()
    return _REGISTRY.get(key)


def all_document_specs() -> list[DocumentSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _lazy_registry()
    return list(_REGISTRY.values())


def search_documents(spec: DocumentSpec, query: str, *, limit: int = 10) -> list[dict]:
    if not spec.search_fn or not query or not query.strip():
        return []
    try:
        rows = spec.search_fn(q=query.strip(), page=1, page_size=limit, export_all=False)
        if isinstance(rows, dict) and "items" in rows:
            rows = rows["items"]
        return list(rows or [])[:limit]
    except TypeError:
        try:
            return list(spec.search_fn(query.strip()) or [])[:limit]
        except Exception:
            return []
    except Exception:
        return []


def document_label(row: dict, spec: DocumentSpec) -> str:
    no = row.get(spec.no_field) or row.get("invoice_no") or row.get("return_no") or row.get("id")
    party = (
        row.get("customer_name")
        or row.get("supplier_name")
        or row.get("party_name")
        or ""
    )
    status = (row.get("status") or "draft").replace("_", " ")
    return f"{spec.label} {no} — {party or '—'} [{status}]"


def is_editable(row: dict, spec: DocumentSpec) -> bool:
    st = (row.get("status") or "draft").lower()
    return st in spec.editable_statuses


def log_document_open(spec: DocumentSpec, record_id: int, document_no: str, user_id: int | None) -> None:
    try:
        from database import get_connection
        with get_connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='erp_document_open_log'"
            ).fetchone():
                return
            conn.execute(
                """INSERT INTO erp_document_open_log
                   (doc_type, record_id, document_no, user_id) VALUES (?,?,?,?)""",
                (spec.key, record_id, document_no, user_id),
            )
    except Exception:
        pass
