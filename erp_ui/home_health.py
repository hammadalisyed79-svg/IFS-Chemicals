"""Lightweight Books Health strip for CEO home (Phase next)."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from erp_ui.nav import can_view_screen, go_screen


def _safe_int(fn, default=0):
    try:
        return int(fn() or 0)
    except Exception:
        return default


def _orphan_weight_slips() -> int:
    try:
        return len(db.get_completed_unlinked_slips() or [])
    except Exception:
        return 0


def _gl_imbalance_flag() -> bool:
    """Prefer last Health Check flag; otherwise skip heavy full-GL scan on home."""
    if "hc_gl_ok" in st.session_state:
        return st.session_state.get("hc_gl_ok") is False
    try:
        with db.get_connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='general_ledger'"
            ).fetchone():
                return False
            n = conn.execute("SELECT COUNT(*) FROM general_ledger").fetchone()[0]
            if int(n or 0) > 200_000:
                return False  # too large for home strip — use Health Check page
            row = conn.execute(
                """SELECT COALESCE(SUM(debit),0) AS d, COALESCE(SUM(credit),0) AS c
                   FROM general_ledger"""
            ).fetchone()
            if not row:
                return False
            d, c = float(row[0] or 0), float(row[1] or 0)
            bad = abs(d - c) > 0.05
            st.session_state["hc_gl_ok"] = not bad
            return bad
    except Exception:
        return False


def _pending_fmye_hint() -> int:
    """Count recent pending FMYE-related drafts if registry exists; else 0."""
    try:
        with db.get_connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='erp_draft_registry'"
            ).fetchone():
                return 0
            return int(conn.execute(
                """SELECT COUNT(*) FROM erp_draft_registry
                   WHERE COALESCE(status,'draft') IN ('draft','pending')
                     AND (LOWER(COALESCE(doc_type,'')) LIKE '%fmye%'
                          OR LOWER(COALESCE(source,'')) LIKE '%fmye%'
                          OR LOWER(COALESCE(notes,'')) LIKE '%fmye%')"""
            ).fetchone()[0] or 0)
    except Exception:
        return 0


def render_books_health_strip(nav: dict, user: dict) -> None:
    """Compact trust strip under Business Pulse."""
    if not can_view_screen(user, "ERP Health Check") and not can_view_screen(user, "Dashboard"):
        return

    try:
        stats = db.get_dashboard_stats()
    except Exception:
        stats = {}
    pending = stats.get("pending_breakdown") or {}

    slips = _orphan_weight_slips()
    payroll = int(pending.get("payroll_draft") or 0)
    sales_appr = int(pending.get("sales_approval") or 0)
    purch_appr = int(pending.get("purchase_approval") or 0)
    gl_bad = _gl_imbalance_flag()
    fmye = _pending_fmye_hint()
    score = st.session_state.get("hc_score")

    issues = []
    if slips:
        issues.append(f"{slips} slip(s) awaiting invoice")
    if gl_bad:
        issues.append("GL debit≠credit")
    if payroll:
        issues.append(f"{payroll} payroll draft(s)")
    if sales_appr or purch_appr:
        issues.append(f"{sales_appr + purch_appr} invoice approval(s)")
    if fmye:
        issues.append(f"{fmye} FMYE draft(s)")

    head, btn = st.columns([5, 1])
    with head:
        st.markdown('<p class="erp-desk-section">Books Health</p>', unsafe_allow_html=True)
    with btn:
        if can_view_screen(user, "ERP Health Check") and st.button(
            "Health Check", key="desk_hc_full", use_container_width=True
        ):
            if "Administration" in nav and "ERP Health Check" in nav.get("Administration", []):
                go_screen("Administration", "ERP Health Check")

    cols = st.columns(5)
    cells = [
        ("Unlinked slips", str(slips), slips > 0),
        ("Approvals", str(sales_appr + purch_appr), (sales_appr + purch_appr) > 0),
        ("Payroll drafts", str(payroll), payroll > 0),
        ("GL balance", "Off" if gl_bad else "OK", gl_bad),
        ("Health score", f"{score}%" if score is not None else "—", False),
    ]
    for col, (title, value, warn) in zip(cols, cells):
        accent = "#DC2626" if warn else "#1D4ED8"
        with col:
            st.markdown(
                f"""
                <div class="dash-kpi dash-kpi-compact" style="border-left-color:{accent};">
                    <div class="dash-kpi-title">{title}</div>
                    <div class="dash-kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if issues:
        st.caption("Attention: " + " · ".join(issues))
    elif fmye:
        st.caption(f"FMYE drafts pending: **{fmye}**")
    else:
        st.caption("No open trust flags from quick checks.")
