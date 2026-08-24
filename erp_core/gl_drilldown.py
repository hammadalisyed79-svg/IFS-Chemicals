"""V14 RC1 — bidirectional GL ↔ source document navigation."""

from __future__ import annotations


def gl_entries_for_document(ref_type: str, ref_id: int) -> list[dict]:
    from database import get_connection, rows_to_list

    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='general_ledger'"
        ).fetchone():
            return []
        return rows_to_list(conn.execute(
            """SELECT gl.*, a.code AS account_code, a.name AS account_name
               FROM general_ledger gl
               JOIN chart_of_accounts a ON a.id=gl.account_id
               WHERE gl.reference_type=? AND gl.reference_id=?
               ORDER BY gl.id""",
            (ref_type, ref_id),
        ).fetchall())


def source_document_for_gl(gl_id: int) -> dict | None:
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        row = conn.execute(
            "SELECT reference_type, reference_id, reference_no, voucher_id FROM general_ledger WHERE id=?",
            (gl_id,),
        ).fetchone()
        if not row:
            return None
        info = dict(row)
        ref_type = info.get("reference_type") or ""
        ref_id = info.get("reference_id")
        nav = _REF_NAV.get(ref_type)
        if nav and ref_id:
            info["nav_group"] = nav[0]
            info["nav_screen"] = nav[1]
            info["doc_type"] = nav[2]
        if info.get("voucher_id"):
            info["journal_voucher_id"] = info["voucher_id"]
            info["nav_group"] = "Finance"
            info["nav_screen"] = "Journal Voucher"
            info["doc_type"] = "journal_voucher"
        return info


_REF_NAV = {
    "sales_invoice": ("Sales", "Sales Invoices", "sales_invoice"),
    "sales": ("Sales", "Sales Invoices", "sales_invoice"),
    "purchase_invoice": ("Purchases", "Purchase Invoices", "purchase_invoice"),
    "purchase": ("Purchases", "Purchase Invoices", "purchase_invoice"),
    "grn": ("Purchases", "GRN", "grn"),
    "journal": ("Finance", "Journal Voucher", "journal_voucher"),
    "cash_receipt": ("Finance", "Customer Receipt", "cash_receipt"),
    "cash_payment": ("Finance", "Supplier Payment", "cash_payment"),
    "production": ("Production", "Production Orders", "production_order"),
}


def render_gl_drilldown_panel(ref_type: str, ref_id: int, key_prefix: str = "gl_drill") -> None:
    """Streamlit panel: show GL lines with link to source."""
    import streamlit as st
    from erp_ui.helpers import fmt_money

    rows = gl_entries_for_document(ref_type, ref_id)
    if not rows:
        st.caption("No GL entries linked to this document yet.")
        return
    st.markdown("**Accounting entries**")
    for r in rows:
        st.text(
            f"{r.get('account_code')} {r.get('account_name', '')[:30]} · "
            f"Dr {fmt_money(r.get('debit'))} · Cr {fmt_money(r.get('credit'))}"
        )
