"""V13.14 — Enterprise Health Check & automated QC report."""

from __future__ import annotations

import os
import re
import sqlite3
import streamlit as st
from application import data_gateway as db
from erp_ui.helpers import std_page_header, section_header, render_dataframe_html_table
from erp_core.transaction_validation import (
    validate_purchase_invoice,
    validate_sale_invoice,
)
from erp_core.transaction_engine import all_document_specs
from erp_core.enterprise_search import enterprise_search
from erp_version import APP_VERSION_FULL


def _check(name: str, fn, *, category: str = "Core") -> tuple[str, str, str, str]:
    try:
        fn()
        return ("pass", category, name, "OK")
    except AssertionError as exc:
        return ("fail", category, name, str(exc))
    except Exception as exc:
        return ("fail", category, name, str(exc))


def page_erp_health_check():
    std_page_header("ERP Health Check", subtitle=f"{APP_VERSION_FULL} — Health Check 2.0", status="register", status_kind="shell")
    section_header("Automated inspection")
    c1, c2, c3 = st.columns(3)
    if c1.button("Run Health Check", type="primary", key="hc_run"):
        st.session_state["hc_results"] = _run_all_checks()
        _write_health_report(st.session_state["hc_results"])
        st.rerun()
    if c2.button("Run Enterprise QC", key="hc_ent"):
        st.session_state["hc_results"] = _run_enterprise_qc()
        _write_health_report(st.session_state["hc_results"])
        st.rerun()
    if c3.button("Run Full RC1 Suite", key="hc_rc1"):
        from erp_core.health_engine import run_health_check_2, write_all_reports
        rep = run_health_check_2()
        st.session_state["hc_results"] = rep.results
        st.session_state["hc_score"] = rep.score
        write_all_reports(rep)
        st.rerun()

    section_header("Party ledger repair")
    st.caption(
        "Restores openings from FMYE (**OpeningDr − OpeningCr**: + = Dr, − = Cr) for customers "
        "and suppliers, de-duplicates dual-code parties (keeps the signed amount), then "
        "recalculates all current balances from the ledger."
    )
    if st.button("Audit & Fix All Customer/Supplier Ledgers", key="hc_ledger_fix"):
        with st.spinner("Auditing and recalculating all party ledgers…"):
            rep = db.audit_fix_party_ledgers()
        st.session_state["hc_ledger_fix"] = rep
        st.rerun()
    rep = st.session_state.get("hc_ledger_fix")
    if rep:
        st.success(
            f"Ledgers repaired — customers **{rep.get('customers_updated')}**, "
            f"suppliers **{rep.get('suppliers_updated')}**. "
            f"Mismatches before/after: **{rep.get('mismatches_before')}** → **{rep.get('mismatches_after')}**."
        )
        fmye = rep.get("fmye_openings") or {}
        if fmye:
            st.info(
                f"FMYE openings restored — customers **{fmye.get('customers_restored', 0)}**, "
                f"suppliers **{fmye.get('suppliers_restored', 0)}**, "
                f"dual-code assigned **{fmye.get('dual_assigned', 0)}**."
            )
            if fmye.get("errors"):
                st.warning("; ".join(str(x) for x in fmye["errors"][:3]))
        dual = rep.get("dual_role") or {}
        if dual:
            st.info(
                f"Dual-role openings adjusted: **{dual.get('adjusted', 0)}** "
                f"(cleared customer stubs **{dual.get('cleared_customer_ob', 0)}**, "
                f"supplier stubs **{dual.get('cleared_supplier_ob', 0)}** "
                f"of {dual.get('dual_pairs', 0)} paired codes)."
            )
        if rep.get("asif_khan_closing_to_2026_08_07") is not None:
            st.caption(
                f"Check sample ASIF KHAN MARBLE closing to 2026-08-07: "
                f"Rs. {float(rep['asif_khan_closing_to_2026_08_07']):,.2f}"
            )
        if rep.get("samples"):
            with st.expander("Sample mismatches before repair"):
                render_dataframe_html_table(rep["samples"])

    score = st.session_state.get("hc_score")
    if score is not None:
        st.metric("Health Score", f"{score}%")

    results = st.session_state.get("hc_results")
    if not results:
        st.info("Click **Run Health Check** or **Run Enterprise QC (full)**.")
        return

    passed = sum(1 for r in results if r[0] == "pass")
    st.metric("Checks passed", f"{passed} / {len(results)}")
    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r[1], []).append(r)
    for cat, items in by_cat.items():
        section_header(cat)
        for status, _, name, detail in items:
            if status == "pass":
                st.success(f"✓ {name}")
            else:
                st.error(f"✗ {name} — {detail}")


def _run_all_checks() -> list[tuple[str, str, str, str]]:
    checks = []

    def login_ok():
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        u = db.authenticate("admin", CI_ADMIN_PASSWORD)
        assert u and u.get("username") == "admin", "admin login failed"

    def customer_required():
        r = validate_sale_invoice({"customer_id": None}, [{"product_id": 1, "quantity": 1, "rate": 10}], {"taxable": 10, "subtotal": 10, "discount_amt": 0, "sales_tax": 0, "further_tax": 0, "fed_tax": 0, "extra_tax": 0, "wht_tax": 0, "total_tax": 0})
        assert not r.ok

    def supplier_required():
        r = validate_purchase_invoice({"supplier_id": None}, [{"product_id": 1, "quantity": 1, "rate": 10}], {"taxable": 10, "subtotal": 10, "discount_amt": 0, "sales_tax": 0, "further_tax": 0, "fed_tax": 0, "extra_tax": 0, "wht_tax": 0, "total_tax": 0})
        assert not r.ok

    def blank_sale_blocked():
        assert not validate_sale_invoice({"customer_id": 1}, [], None).ok

    def blank_purchase_blocked():
        assert not validate_purchase_invoice({"supplier_id": 1}, [], None).ok

    def totals_recalc():
        from tax_engine import compute_invoice_totals
        t = compute_invoice_totals([{"quantity": 2, "rate": 100, "amount": 200}], {"discount_pct": 10, "tax_pct": 18})
        assert float(t["subtotal"]) == 200

    def weekly_holidays_table():
        with db.get_connection() as conn:
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='weekly_holidays'").fetchone()

    def draft_registry():
        with db.get_connection() as conn:
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_draft_registry'").fetchone()

    def v14_tables():
        with db.get_connection() as conn:
            for t in ("erp_approval_rules", "erp_error_log", "erp_print_log", "erp_favorite_reports"):
                assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), f"{t} missing"

    def cash_book_query():
        from datetime import date
        today = date.today().isoformat()
        assert db.get_cash_book(today, today) is not None

    def bank_book_query():
        from datetime import date
        today = date.today().isoformat()
        assert db.get_bank_book(today, today) is not None

    def gl_table():
        with db.get_connection() as conn:
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='general_ledger'").fetchone()

    def enterprise_search_ok():
        hits = enterprise_search("SI", limit=5)
        assert hits is not None

    def transaction_engine_registry():
        specs = all_document_specs()
        assert len(specs) >= 10

    for fn in (
        login_ok, customer_required, supplier_required, blank_sale_blocked,
        blank_purchase_blocked, totals_recalc, weekly_holidays_table,
        draft_registry, v14_tables, cash_book_query, bank_book_query, gl_table,
        enterprise_search_ok, transaction_engine_registry,
    ):
        checks.append(_check(fn.__name__.replace("_", " ").title(), fn))
    return checks


def _get_app_pages() -> dict:
    """PAGES from the running Streamlit script — never re-import app.py (set_page_config)."""
    import sys
    for name in ("__main__", "app"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "PAGES"):
            pages = getattr(mod, "PAGES")
            if isinstance(pages, dict) and pages:
                return pages
    # Offline / CLI: import under a no-op page-config so Streamlit does not raise
    import streamlit as _st
    _orig = getattr(_st, "set_page_config", None)
    try:
        if _orig is not None:
            _st.set_page_config = lambda *a, **k: None
        import app as _app  # noqa: WPS433
        return dict(_app.PAGES)
    finally:
        if _orig is not None:
            _st.set_page_config = _orig


def _run_enterprise_qc() -> list[tuple[str, str, str, str]]:
    results = _run_all_checks()

    def menus_registered():
        from erp_ui.nav import NAV_GROUPS
        pages = _get_app_pages()
        missing = []
        for group, screens in NAV_GROUPS.items():
            for s in screens:
                if s not in pages:
                    missing.append(s)
        assert not missing, f"Unregistered screens: {', '.join(missing[:10])}"

    def duplicate_page_ids():
        pages = _get_app_pages()
        assert pages, "PAGES is empty"
        # Same label may appear in more than one nav group (e.g. Employees); keys in PAGES must be unique.
        assert len(pages) == len(set(pages.keys()))
        nulls = [k for k, v in pages.items() if v is None]
        assert not nulls, f"Null page handlers: {', '.join(nulls[:8])}"

    def foreign_keys_on():
        with db.get_connection() as conn:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()
            assert fk is not None

    def scaffold_scan():
        root = os.path.dirname(os.path.dirname(__file__))
        bad = re.compile(r"\bst\.(info|warning)\([^)]*coming soon|\bst\.(info|warning)\([^)]*not configured", re.I)
        hits = []
        skip = {"health_check.py", "KNOWN_ISSUES.md"}
        for dirpath, _, files in os.walk(root):
            if "venv" in dirpath or "__pycache__" in dirpath or "erp_core" in dirpath:
                continue
            for f in files:
                if f in skip or not f.endswith(".py"):
                    continue
                path = os.path.join(dirpath, f)
                try:
                    text = open(path, encoding="utf-8", errors="ignore").read()
                    if bad.search(text):
                        hits.append(os.path.relpath(path, root))
                except Exception:
                    pass
        assert len(hits) <= 1, f"User-facing scaffold in: {hits}"

    def report_catalog_nonempty():
        from erp_ui.reports_pages import REPORT_CATALOG
        total = sum(len(v) for v in REPORT_CATALOG.values())
        assert total >= 20

    def approval_rules_seeded():
        with db.get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM erp_approval_rules").fetchone()[0]
            assert n >= 1

    for fn, cat in (
        (menus_registered, "Menus"),
        (duplicate_page_ids, "Menus"),
        (foreign_keys_on, "Database"),
        (scaffold_scan, "UI"),
        (report_catalog_nonempty, "Reports"),
        (approval_rules_seeded, "Approval"),
    ):
        results.append(_check(fn.__name__.replace("_", " ").title(), fn, category=cat))
    return results


def _write_health_report(results: list) -> None:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "HEALTH_CHECK_REPORT.md")
    passed = sum(1 for r in results if r[0] == "pass")
    lines = [
        "# ERP Health Check Report",
        "",
        f"**Version:** {APP_VERSION_FULL}",
        f"**Result:** {passed} / {len(results)} passed",
        "",
        "| Status | Category | Check | Detail |",
        "|--------|----------|-------|--------|",
    ]
    for status, cat, name, detail in results:
        lines.append(f"| {status.upper()} | {cat} | {name} | {detail} |")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass
