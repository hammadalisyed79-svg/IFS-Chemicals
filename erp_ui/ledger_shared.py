"""Shared party ledger UI — customer and supplier."""

from __future__ import annotations

import streamlit as st

from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui.helpers import sticky_page_tabs, render_ledger_summary_table, render_ledger_detailed_table


def render_party_ledger(
    party_kind: str,
    *,
    page_title: str,
    party_select_key: str,
    from_key: str,
    to_key: str,
    tab_state_key: str,
    split_books_key: str,
    export_summary_name: str,
    export_detailed_name: str,
    export_summary_title: str,
    export_detailed_title: str,
    attach_ledger_party_fn,
    export_df_fn,
) -> None:
    hlp.std_page_header(page_title, status="posted", status_kind="shell")
    st.caption(
        "**Summary** = one line per voucher. **Detailed** = invoice lines (Qty / Rate / Amount). "
        "Toggle tabs below; use **Export** for print/PDF."
    )

    if party_kind == "customer":
        if not db.get_customers(active_only=False):
            st.info("Add customers under **Master Data → Customer** first.")
            return
        get_summary = db.get_customer_ledger
        get_detailed = db.get_customer_ledger_detailed
        find_linked = lambda pid: db.find_linked_counterparty("customer", pid)
        linked_label = "Supplier"
        party_label = "Customer"
        balance_kind = "customer"
        party_select = lambda: hlp.customer_select(party_select_key)
    else:
        if not db.get_suppliers(active_only=False):
            st.info("Add suppliers under **Master Data → Supplier** first.")
            return
        get_summary = db.get_supplier_ledger
        get_detailed = db.get_supplier_ledger_detailed
        find_linked = lambda pid: db.find_linked_counterparty("supplier", pid)
        linked_label = "Customer"
        party_label = "Supplier"
        balance_kind = "supplier"
        party_select = lambda: hlp.supplier_select(party_select_key)

    c1, c2, c3 = st.columns(3)
    with c1:
        party_id = party_select()
    with c2:
        fd = c2.date_input("From", value=None, key=from_key)
    with c3:
        td = c3.date_input("To", value=None, key=to_key)

    if not party_id:
        st.info(f"Select a {party_label.lower()} to view the ledger.")
        return

    fd_s = str(fd) if fd else None
    td_s = str(td) if td else None
    period = f"{fd_s or 'Start'} to {td_s or 'Today'}"
    linked = find_linked(party_id)
    include_linked = True
    if linked:
        st.success(
            f"Dual-role party **{linked.get('primary_code') or linked.get('code')}** — "
            f"{party_label} and {linked_label} **{linked['code']} — {linked['name']}** "
            f"share one **combined ledger**. Master balances stay **per book**; "
            f"Outstanding nets both."
        )
        split_books = st.checkbox(
            f"Show {party_label.lower()} book only (not combined)",
            value=False,
            key=split_books_key,
            help=f"Off = combined statement (recommended). On = {party_label.lower()} book only.",
        )
        include_linked = not split_books

    def _ledger_kpis(party, entries, detailed=False):
        summary = (party or {}).get("ledger_summary") or {}
        opening = float(summary.get("opening") or 0)
        pdeb = float(summary.get("period_debit") or 0)
        pcred = float(summary.get("period_credit") or 0)
        if detailed:
            closing = db.last_detailed_ledger_balance(entries, kind=balance_kind) if entries else float(
                party.get("balance") or 0
            )
        else:
            closing = float(summary.get("closing") if summary else (
                entries[-1]["balance"] if entries else party.get("balance") or 0
            ))
        code = party.get("code") or ""
        st.subheader(f"{code} — {party['name']}" if code else party["name"])
        note = summary.get("note")
        if note:
            st.caption(note)
        hlp.render_ledger_kpi_strip(opening, pdeb, pcred, closing)
        st.caption("Balances: **Dr** = Debit, **Cr** = Credit (+Dr / −Cr).")

    ledger_tab = sticky_page_tabs(
        ["Summary", "Detailed (with invoice lines)"],
        tab_state_key,
    )

    # Match Reports Center: show up to 1000 on-screen lines (same data, not a 100-row page).
    # Closing KPIs already use the full entry list; paging at 100 made mid-history look "missing".
    _SCREEN_CAP = 1000

    if ledger_tab == "Summary":
        party, entries = get_summary(party_id, fd_s, td_s, include_linked=include_linked)
        _ledger_kpis(party, entries, detailed=False)
        if entries:
            import pandas as pd
            show = entries[:_SCREEN_CAP]
            df = pd.DataFrame(entries)[["date", "ref", "description", "debit", "credit", "balance"]]
            df = attach_ledger_party_fn(df, party, party_kind)
            st.caption(f"**{len(entries):,}** voucher lines" + (
                f" — showing first **{len(show):,}** on screen; Export / Print has all."
                if len(entries) > _SCREEN_CAP else ""
            ))
            render_ledger_summary_table(show)
            filters = {party_label: f"{party.get('code')} - {party.get('name')}"}
            if include_linked and party.get("linked_party"):
                lp = party["linked_party"]
                filters["Combined with"] = f"{linked_label} {lp.get('code')} — {lp.get('name')}"
            export_df_fn(
                df, export_summary_name, export_summary_title,
                period=period,
                filters=filters,
            )
        else:
            st.markdown(
                '<div class="erp-empty-state"><p>No ledger movements in this period.</p></div>',
                unsafe_allow_html=True,
            )
    elif ledger_tab == "Detailed (with invoice lines)":
        party, entries = get_detailed(party_id, fd_s, td_s, include_linked=include_linked)
        _ledger_kpis(party, entries, detailed=True)
        if entries:
            from erp_ui.reports_pages import _detailed_ledger_dataframe
            show = entries[:_SCREEN_CAP]
            df = _detailed_ledger_dataframe(entries)
            df = attach_ledger_party_fn(df, party, party_kind)
            try:
                ls = dict(df.attrs.get("ledger_summary") or party.get("ledger_summary") or {})
                ls["closing"] = db.last_detailed_ledger_balance(entries, kind=balance_kind)
                df.attrs["ledger_summary"] = ls
            except Exception:
                pass
            st.caption(f"**{len(entries):,}** detailed lines" + (
                f" — showing first **{len(show):,}** on screen; Export / Print has all."
                if len(entries) > _SCREEN_CAP else ""
            ))
            render_ledger_detailed_table(show)
            filters = {party_label: f"{party.get('code')} - {party.get('name')}"}
            if include_linked and party.get("linked_party"):
                lp = party["linked_party"]
                filters["Combined with"] = f"{linked_label} {lp.get('code')} — {lp.get('name')}"
            export_df_fn(
                df, export_detailed_name, export_detailed_title,
                period=period,
                filters=filters,
            )
        else:
            st.markdown(
                '<div class="erp-empty-state"><p>No detailed ledger lines in this period.</p></div>',
                unsafe_allow_html=True,
            )
