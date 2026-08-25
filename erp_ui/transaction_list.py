"""Professional paginated transaction registers (sales, purchases, etc.)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import fmt_money, fmt_datetime_from_record
from erp_ui import helpers as hlp


STATUS_OPTIONS = ["All", "draft", "pending_approval", "approved", "rejected", "cancelled"]
DOC_STATUS_OPTIONS = ["All", "draft", "open", "partial", "posted", "approved", "converted", "sent", "closed", "cancelled", "rejected", "pending_approval"]
PAYMENT_OPTIONS = ["All", "credit", "cash", "bank"]
PAGE_SIZES = [25, 50, 100, 200]
REGISTER_SORT_OPTIONS = {
    "Workflow (pending first)": "workflow",
    "Date ↓ newest": "date_desc",
    "Date ↑ oldest": "date_asc",
    "Amount ↓ high": "amount_desc",
    "Amount ↑ low": "amount_asc",
    "Party A–Z": "party",
    "Status": "status",
}
PERIOD_PRESETS = {
    "Today": "today",
    "This Month": "month",
    "Last 30 Days": "30d",
    "This Quarter": "quarter",
    "This Year": "year",
    "All Time": "all",
}


def _period_dates(preset):
    today = date.today()
    if preset == "today":
        return today, today
    if preset == "month":
        return today.replace(day=1), today
    if preset == "30d":
        return today - timedelta(days=30), today
    if preset == "quarter":
        q_start = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)
        return q_start, today
    if preset == "year":
        return today.replace(month=1, day=1), today
    return None, None


def _status_label(s):
    try:
        from erp_ui.invoice_status_ui import status_label
        return status_label(s)
    except Exception:
        return (s or "draft").replace("_", " ").title()


def status_badge_for_row(status):
    """Markdown badge for captions / selected-row chrome."""
    try:
        from erp_ui.invoice_status_ui import status_badge_html
        return status_badge_html(status)
    except Exception:
        return _status_label(status)


def _status_counts_strip(items: list) -> None:
    """Colored status pills — visible redesign cue on every register."""
    if not items:
        return
    from collections import Counter
    from erp_ui.invoice_status_ui import status_badge_html

    counts = Counter((r.get("status") or "draft").lower() for r in items)
    order = ("draft", "pending_approval", "approved", "rejected", "cancelled", "open", "partial")
    parts = []
    for key in order:
        n = counts.get(key) or 0
        if n:
            parts.append(f'{status_badge_html(key)}&nbsp;<strong>{n}</strong>')
    for key, n in counts.items():
        if key not in order and n:
            parts.append(f'{status_badge_html(key)}&nbsp;<strong>{n}</strong>')
    if parts:
        st.markdown(
            f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
            unsafe_allow_html=True,
        )


def _render_register_html_table(items: list, columns: list) -> None:
    """HTML table so Status column can show colored badges (dataframe cannot)."""
    from html import escape
    from erp_ui.invoice_status_ui import status_badge_html

    ths = "".join(f"<th>{escape(c['label'])}</th>" for c in columns)
    body_rows = []
    for r in items:
        cells = []
        for c in columns:
            fmt = c.get("format")
            val = r.get(c["field"])
            if fmt == "status":
                cells.append(f"<td class='txn-status-cell'>{status_badge_html(val)}</td>")
            elif fmt == "money":
                cells.append(f"<td class='txn-num'>{escape(fmt_money(val))}</td>")
            elif fmt == "datetime":
                txt = fmt_datetime_from_record(
                    r, c["field"], time_field=c.get("time_field"),
                )
                cells.append(f"<td>{escape(str(txt or '—'))}</td>")
            else:
                cells.append(f"<td>{escape(str(val if val is not None else '—'))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    html = (
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _build_df(items, columns):
    if not items:
        return pd.DataFrame()
    rows = []
    for r in items:
        row = {}
        for col in columns:
            val = r.get(col["field"])
            if col.get("format") == "money":
                val = float(val or 0)
            elif col.get("format") == "status":
                val = _status_label(val)
            elif col.get("format") == "datetime":
                val = fmt_datetime_from_record(
                    r, col["field"], time_field=col.get("time_field"),
                )
            row[col["label"]] = val
        rows.append(row)
    return pd.DataFrame(rows)


def _sort_items_client(items: list, sort_key: str | None) -> list:
    """Sort register rows (current page / export batch) when SQL sort is unavailable."""
    key = (sort_key or "workflow").strip().lower()
    if not items or key == "workflow":
        status_rank = {
            "pending_approval": 0,
            "draft": 1,
            "rejected": 2,
            "open": 3,
            "partial": 4,
        }
        return sorted(
            items,
            key=lambda r: (
                status_rank.get((r.get("status") or "draft").lower(), 9),
                str(_row_date(r)),
                int(r.get("id") or 0),
            ),
        )

    def amount(r):
        return float(r.get("total") or 0)

    if key == "date_asc":
        return sorted(items, key=lambda r: (str(_row_date(r)), int(r.get("id") or 0)))
    if key == "date_desc":
        return sorted(
            items,
            key=lambda r: (str(_row_date(r)), int(r.get("id") or 0)),
            reverse=True,
        )
    if key == "amount_desc":
        return sorted(items, key=lambda r: (amount(r), int(r.get("id") or 0)), reverse=True)
    if key == "amount_asc":
        return sorted(items, key=lambda r: (amount(r), int(r.get("id") or 0)))
    if key == "party":
        return sorted(
            items,
            key=lambda r: (_row_party(r).lower(), str(_row_date(r)), int(r.get("id") or 0)),
        )
    if key == "status":
        return sorted(
            items,
            key=lambda r: (
                str(r.get("status") or "").lower(),
                str(_row_date(r)),
                int(r.get("id") or 0),
            ),
        )
    return items


def _row_date(row: dict) -> str:
    for field in (
        "sale_date", "purchase_date", "order_date", "invoice_date",
        "document_date", "dn_date", "grn_date", "quotation_date",
    ):
        val = row.get(field)
        if val:
            return str(val)[:10]
    return ""


def _row_party(row: dict) -> str:
    return (
        row.get("customer_name")
        or row.get("supplier_name")
        or row.get("party_name")
        or ""
    )


def _filter_bar(key_prefix, party_label, party_options, default_period="Today",
                show_payment=True, show_status=True, status_options=None):
    status_options = status_options or STATUS_OPTIONS
    if default_period not in PERIOD_PRESETS:
        default_period = "Today"

    # One-time: move legacy register defaults (This Month / Last 30 Days) to Today
    if not st.session_state.get("_reg_default_today_v1"):
        for k in list(st.session_state.keys()):
            if str(k).endswith("_period") and st.session_state.get(k) in ("This Month", "Last 30 Days"):
                st.session_state[k] = "Today"
                prefix = str(k)[: -len("_period")]
                st.session_state.pop(f"{prefix}_period_applied", None)
                st.session_state.pop(f"{prefix}_fd", None)
                st.session_state.pop(f"{prefix}_td", None)
        st.session_state["_reg_default_today_v1"] = True

    st.markdown('<div class="txn-filter-box">', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1.2])
    q = c1.text_input(
        "Search",
        placeholder="Document no, party name/code, notes…",
        key=f"{key_prefix}_q",
    )
    period_key = f"{key_prefix}_period"
    fd_key = f"{key_prefix}_fd"
    td_key = f"{key_prefix}_td"
    if st.session_state.get(period_key) not in PERIOD_PRESETS:
        st.session_state.pop(period_key, None)
    if period_key not in st.session_state:
        st.session_state[period_key] = default_period

    period = c2.selectbox(
        "Period",
        list(PERIOD_PRESETS.keys()),
        key=period_key,
    )
    preset_code = PERIOD_PRESETS[period]
    fd_def, td_def = _period_dates(preset_code)

    # When Period changes, reset From/To to that preset (user can still edit dates after)
    prev_key = f"{key_prefix}_period_applied"
    if st.session_state.get(prev_key) != period:
        if preset_code != "all" and fd_def and td_def:
            st.session_state[fd_key] = fd_def
            st.session_state[td_key] = td_def
        st.session_state[prev_key] = period

    if preset_code != "all":
        if fd_key not in st.session_state and fd_def:
            st.session_state[fd_key] = fd_def
        if td_key not in st.session_state and td_def:
            st.session_state[td_key] = td_def
        fd = c3.date_input("From", key=fd_key)
        td = c4.date_input("To", key=td_key)
    else:
        fd = td = None
        c3.caption("No date limit")
        c4.caption("")

    if party_label and party_options is not None:
        c5, c6, c7, c8 = st.columns([2, 1.2, 1.2, 1])
        party_sel = c5.selectbox(party_label, ["All"] + list(party_options.keys()), key=f"{key_prefix}_party")
        party_id = party_options.get(party_sel) if party_sel != "All" else None
        status = c6.selectbox("Status", status_options, key=f"{key_prefix}_status") if show_status else "All"
        payment = c7.selectbox("Payment", PAYMENT_OPTIONS, key=f"{key_prefix}_pay") if show_payment else "All"
        page_size = c8.selectbox("Rows", PAGE_SIZES, index=1, key=f"{key_prefix}_ps")
    else:
        c5, c6, c7 = st.columns([2, 1.2, 1])
        party_id = None
        status = c5.selectbox("Status", status_options, key=f"{key_prefix}_status") if show_status else "All"
        payment = "All"
        page_size = c6.selectbox("Rows", PAGE_SIZES, index=1, key=f"{key_prefix}_ps")
        c7.caption("")

    sort_labels = list(REGISTER_SORT_OPTIONS.keys())
    from erp_ui.register_prefs import (
        apply_register_filter,
        capture_filter_widgets,
        is_density_compact,
        list_saved_filters,
        save_register_filter,
        set_density_compact,
    )

    r1, r2, r3, r4, r5, r6 = st.columns([1.6, 0.9, 1.2, 1.0, 1.0, 1.0])
    sort_label = r1.selectbox("Sort", sort_labels, key=f"{key_prefix}_sort_label")
    sort_key = REGISTER_SORT_OPTIONS[sort_label]
    compact = r2.checkbox(
        "Compact",
        value=is_density_compact(),
        key=f"{key_prefix}_compact",
        help="Dense register rows — more lines on screen",
    )
    set_density_compact(compact)
    saved = list_saved_filters(key_prefix)
    save_name = r3.text_input(
        "Save filter as",
        key=f"{key_prefix}_save_name",
        placeholder="e.g. This month + customer",
        label_visibility="collapsed",
    )
    r3.caption("Save filter")
    if r4.button("Save", key=f"{key_prefix}_save_btn", use_container_width=True):
        snap = capture_filter_widgets(key_prefix)
        save_register_filter(key_prefix, save_name or "Saved filter", snap)
        st.toast("Filter saved for this register.")
    load_labels = ["— Load saved —"] + [s.get("label") or "Saved" for s in saved]
    load_sel = r5.selectbox(
        "Saved",
        load_labels,
        key=f"{key_prefix}_load_sel",
        label_visibility="collapsed",
    )
    r5.caption("Saved filters")
    if r6.button("Load", key=f"{key_prefix}_load_btn", use_container_width=True, disabled=load_sel == "— Load saved —"):
        match = next((s for s in saved if s.get("label") == load_sel), None)
        if match:
            apply_register_filter(key_prefix, match.get("snapshot") or {})
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "q": (q or "").strip() or None,
        "from_date": str(fd) if fd else None,
        "to_date": str(td) if td else None,
        "party_id": party_id,
        "status": status,
        "payment_mode": payment,
        "page_size": page_size,
        "sort": sort_key,
        "compact": compact,
    }


def _pagination(key_prefix, result):
    total = result["total"]
    page = result["page"]
    pages = result["pages"]
    ps = result["page_size"]
    if total == 0:
        return page
    start = (page - 1) * ps + 1
    end = min(page * ps, total)
    c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
    c1.caption(f"Showing **{start:,}–{end:,}** of **{total:,}**")
    if c2.button("◀ Previous", disabled=page <= 1, key=f"{key_prefix}_prev"):
        st.session_state[f"{key_prefix}_page"] = page - 1
        st.rerun()
    c2.markdown(f"<div style='text-align:center;padding-top:0.4rem;'>Page **{page}** / **{pages}**</div>", unsafe_allow_html=True)
    if c3.button("Next ▶", disabled=page >= pages, key=f"{key_prefix}_next"):
        st.session_state[f"{key_prefix}_page"] = page + 1
        st.rerun()
    jump = c4.number_input("Go to", min_value=1, max_value=pages, value=page, key=f"{key_prefix}_jump")
    if c4.button("Go", key=f"{key_prefix}_go") and jump != page:
        st.session_state[f"{key_prefix}_page"] = int(jump)
        st.rerun()
    return page


def _register_core(
    key_prefix,
    search_fn,
    columns,
    row_label_fn,
    export_name,
    export_title,
    filters,
    party_kw,
    action_panel=None,
    kpi_labels=("Records (filtered)", "Total Amount", "Paid / Received"),
    show_kpi_paid=True,
    open_handler=None,
    empty_message: str | None = None,
    empty_cta_label: str | None = None,
    empty_cta_fn=None,
):
    filter_sig = tuple(sorted((k, str(v)) for k, v in filters.items()))
    if st.session_state.get(f"{key_prefix}_fsig") != filter_sig:
        st.session_state[f"{key_prefix}_page"] = 1
    st.session_state[f"{key_prefix}_fsig"] = filter_sig
    page = st.session_state.get(f"{key_prefix}_page", 1)
    kw = {
        "q": filters["q"],
        "from_date": filters["from_date"],
        "to_date": filters["to_date"],
        "status": filters["status"],
        "page": page,
        "page_size": filters["page_size"],
    }
    if party_kw and filters.get("party_id"):
        kw[party_kw] = filters["party_id"]
    if filters.get("payment_mode") and filters["payment_mode"] != "All":
        kw["payment_mode"] = filters["payment_mode"]
    if filters.get("sort"):
        kw["sort"] = filters["sort"]
    try:
        result = search_fn(**kw)
    except TypeError:
        kw.pop("sort", None)
        result = search_fn(**kw)
    st.session_state[f"{key_prefix}_page"] = result["page"]

    items = _sort_items_client(result["items"], filters.get("sort"))
    result = dict(result)
    result["items"] = items

    if filters.get("compact"):
        st.markdown(
            '<div class="erp-density-compact erp-css-inject" aria-hidden="true">&#8203;</div>',
            unsafe_allow_html=True,
        )

    items = result["items"]
    _status_counts_strip(items)

    tb1, tb2 = st.columns([1, 4])
    with tb1:
        if st.button("Export all filtered", key=f"{key_prefix}_tb_export", use_container_width=True):
            full_kw = {k: v for k, v in kw.items() if k not in ("page", "page_size")}
            try:
                full = search_fn(**full_kw, export_all=True)
            except TypeError:
                full_kw.pop("sort", None)
                full = search_fn(**full_kw, export_all=True)
            full_items = _sort_items_client(full["items"], filters.get("sort"))
            _export_df(_build_df(full_items, columns), export_name, export_title)
    tb2.caption("Excel, PDF, and print — all rows matching filters (not just this page).")

    has_status_col = any(c.get("format") == "status" for c in columns)
    k1, k2, k3 = st.columns(3)
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>{kpi_labels[0]}</p>"
        f"<p class='txn-kpi-val'>{result['total']:,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>{kpi_labels[1]}</p>"
        f"<p class='txn-kpi-val'>{fmt_money(result.get('sum_total', 0))}</p></div>",
        unsafe_allow_html=True,
    )
    if show_kpi_paid and kpi_labels[2]:
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>{kpi_labels[2]}</p>"
            f"<p class='txn-kpi-val'>{fmt_money(result.get('sum_paid', 0))}</p></div>",
            unsafe_allow_html=True,
        )
    else:
        k3.markdown("")

    if not items:
        msg = empty_message or "No records match your filters."
        st.markdown(
            f'<div class="erp-empty-state"><p>{msg}</p></div>',
            unsafe_allow_html=True,
        )
        if empty_cta_label and empty_cta_fn:
            if st.button(empty_cta_label, type="primary", key=f"{key_prefix}_empty_cta"):
                empty_cta_fn()
                st.rerun()
        return None

    if has_status_col:
        _render_register_html_table(items, columns)
    else:
        hlp.render_dataframe_html_table(_build_df(items, columns))

    if open_handler:
        quick_n = min(len(items), 10)
        if quick_n:
            st.caption("Quick open (current page)")
            for r in items[:quick_n]:
                oc1, oc2 = st.columns([1, 5])
                with oc1:
                    if st.button(
                        "Open",
                        key=f"{key_prefix}_qopen_{r.get('id', r.get('invoice_no', ''))}",
                        use_container_width=True,
                    ):
                        open_handler(r)
                        st.rerun()
                with oc2:
                    st.markdown(f"**{row_label_fn(r)}**")
            if len(items) > quick_n:
                st.caption(f"Showing quick open for first {quick_n} rows — use selector below for others.")
    _pagination(key_prefix, result)

    labels = [row_label_fn(r) for r in items]
    id_map = {labels[i]: items[i] for i in range(len(labels))}
    with sel_col:
        sel = st.selectbox("Select record for actions", labels, key=f"{key_prefix}_sel")
    selected = id_map.get(sel)

    if selected:
        from erp_ui.invoice_status_ui import status_badge_html
        badge = (
            f"{status_badge_html(selected.get('status'))}  "
            if selected.get("status") else ""
        )
        if open_handler:
            b1, b2 = st.columns([1, 4])
            if b1.button(
                "Open",
                type="primary",
                key=f"{key_prefix}_open_btn",
                use_container_width=True,
            ):
                open_handler(selected)
                st.rerun()
            b2.markdown(
                f"{badge}**{row_label_fn(selected)}**",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"{badge}**{row_label_fn(selected)}**",
                unsafe_allow_html=True,
            )

    if selected and action_panel:
        st.divider()
        action_panel(selected)
    return selected


def transaction_register(
    key_prefix,
    search_fn,
    columns,
    party_label,
    party_options,
    row_label_fn,
    export_name,
    export_title,
    export_df_fn,
    action_panel=None,
    default_period="Today",
    open_handler=None,
    empty_message: str | None = None,
    empty_cta_label: str | None = None,
    empty_cta_fn=None,
):
    filters = _filter_bar(key_prefix, party_label, party_options, default_period, show_payment=True)
    party_kw = "customer_id" if party_label == "Customer" else "supplier_id"
    return _register_core(
        key_prefix, search_fn, columns, row_label_fn, export_name, export_title,
        filters, party_kw, action_panel, open_handler=open_handler,
        empty_message=empty_message, empty_cta_label=empty_cta_label, empty_cta_fn=empty_cta_fn,
    )


def document_register(
    key_prefix,
    search_fn,
    columns,
    party_label,
    party_options,
    party_kw,
    row_label_fn,
    export_name,
    export_title,
    action_panel=None,
    default_period="Today",
    status_options=None,
    kpi_labels=("Records (filtered)", "Total Amount", None),
    open_handler=None,
):
    filters = _filter_bar(
        key_prefix, party_label, party_options, default_period,
        show_payment=False,
        show_status=len(status_options or DOC_STATUS_OPTIONS) > 1,
        status_options=status_options or DOC_STATUS_OPTIONS,
    )
    return _register_core(
        key_prefix, search_fn, columns, row_label_fn, export_name, export_title,
        filters, party_kw, action_panel, kpi_labels=kpi_labels, show_kpi_paid=False,
        open_handler=open_handler,
    )


def reselect_transaction_picker(key_prefix, record_id):
    """Keep the same record selected after save — apply on next run (before the picker widget)."""
    st.session_state[f"{key_prefix}_pick_pending"] = int(record_id)


def transaction_picker(key_prefix, search_fn, row_label_fn, party_label=None, party_options=None, party_kw=None,
                       placeholder="Type document no or party name…", status_filter=True):
    """Searchable picker for Edit tab — server-side, works with large datasets."""
    pick_key = f"{key_prefix}_pick_sel"
    pending_key = f"{key_prefix}_pick_pending"
    if pending_key in st.session_state:
        st.session_state[pick_key] = st.session_state.pop(pending_key)

    st.caption("Search and pick a record (server-side search).")
    q = st.text_input("Find", placeholder=placeholder, key=f"{key_prefix}_pick_q")
    party_id = None
    status = "All"
    if party_label and party_options:
        c1, c2 = st.columns(2)
        party_sel = c1.selectbox(party_label, ["All"] + list(party_options.keys()), key=f"{key_prefix}_pick_party")
        party_id = party_options.get(party_sel) if party_sel != "All" else None
        if status_filter:
            status = c2.selectbox("Status", STATUS_OPTIONS, key=f"{key_prefix}_pick_st")
    kw = {"q": (q or "").strip() or None, "page": 1, "page_size": 30}
    if party_kw and party_id:
        kw[party_kw] = party_id
    if status_filter and status != "All":
        kw["status"] = status
    result = search_fn(**kw)
    items = result["items"]
    if not items:
        st.info("No match — refine search.")
        return None, None
    ids = [int(r["id"]) for r in items]
    id_to_label = {int(r["id"]): row_label_fn(r) for r in items}
    # Legacy: selectbox used full label strings — drop so labels refresh after edits.
    prev = st.session_state.get(pick_key)
    if prev is not None and prev not in ids:
        st.session_state.pop(pick_key, None)
    if st.session_state.get(pick_key) not in ids:
        st.session_state[pick_key] = ids[0]
    sel_id = st.selectbox(
        "Select",
        options=ids,
        format_func=lambda i: id_to_label.get(i, str(i)),
        key=pick_key,
    )
    return sel_id, items


def document_picker(key_prefix, search_fn, row_label_fn, party_label=None, party_options=None, party_kw=None):
    return transaction_picker(
        key_prefix, search_fn, row_label_fn, party_label, party_options, party_kw,
        placeholder="Type document no or name…", status_filter=False,
    )


def linked_invoice_picker(key_prefix, search_fn, party_id, party_kw, row_label_fn, label="Linked invoice (optional)"):
    """Pick parent invoice for returns — filtered by party."""
    st.markdown(f"**{label}**")
    q = st.text_input("Search invoice", placeholder="Invoice no…", key=f"{key_prefix}_lnk_q")
    kw = {"q": (q or "").strip() or None, "page": 1, "page_size": 20}
    if party_id:
        kw[party_kw] = party_id
    result = search_fn(**kw)
    opts = {"— None —": None}
    opts.update({row_label_fn(r): r["id"] for r in result["items"]})
    sel = st.selectbox("Invoice", list(opts.keys()), key=f"{key_prefix}_lnk_sel")
    return opts[sel]


def sales_register_list(action_panel=None, open_handler=None):
    from erp_ui.doc_workflow import go_sale_new, open_sale_from_register

    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
    cols = [
        {"field": "invoice_no", "label": "Invoice"},
        {"field": "sale_date", "label": "Date / Time", "format": "datetime"},
        {"field": "customer_name", "label": "Customer"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
        {"field": "paid_amount", "label": "Paid", "format": "money"},
        {"field": "payment_mode", "label": "Payment"},
    ]
    handler = open_handler or open_sale_from_register
    return transaction_register(
        "sal_reg",
        db.search_sales_invoices,
        cols,
        "Customer",
        party_opts,
        lambda r: (
            f"{r['invoice_no']} — {r['customer_name']} "
            f"({fmt_datetime_from_record(r, 'sale_date')}) [{_status_label(r.get('status'))}]"
        ),
        "sales_list",
        "Sales Register",
        _export_df,
        action_panel=action_panel,
        open_handler=handler,
        empty_message="No sales invoices match your filters.",
        empty_cta_label="New Sale",
        empty_cta_fn=go_sale_new,
    )


def purchase_register_list(action_panel=None, open_handler=None):
    from erp_ui.doc_workflow import go_purchase_new, open_purchase_from_register

    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}
    cols = [
        {"field": "invoice_no", "label": "Invoice"},
        {"field": "purchase_date", "label": "Date / Time", "format": "datetime"},
        {"field": "supplier_name", "label": "Supplier"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
        {"field": "paid_amount", "label": "Paid", "format": "money"},
        {"field": "payment_mode", "label": "Payment"},
    ]
    handler = open_handler or open_purchase_from_register
    return transaction_register(
        "pur_reg",
        db.search_purchases,
        cols,
        "Supplier",
        party_opts,
        lambda r: (
            f"{r['invoice_no']} — {r['supplier_name']} "
            f"({fmt_datetime_from_record(r, 'purchase_date')}) [{_status_label(r.get('status'))}]"
        ),
        "purchase_list",
        "Purchase Register",
        _export_df,
        action_panel=action_panel,
        open_handler=handler,
        empty_message="No purchase invoices match your filters.",
        empty_cta_label="New Purchase",
        empty_cta_fn=go_purchase_new,
    )


def purchase_return_register_list(action_panel=None):
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}
    cols = [
        {"field": "return_no", "label": "Return No"},
        {"field": "return_date", "label": "Date / Time", "format": "datetime"},
        {"field": "supplier_name", "label": "Supplier"},
        {"field": "invoice_no", "label": "Invoice"},
        {"field": "total", "label": "Total", "format": "money"},
        {"field": "notes", "label": "Notes"},
    ]
    return document_register(
        "pr_reg", db.search_purchase_returns, cols, "Supplier", party_opts, "supplier_id",
        lambda r: (
            f"{r['return_no']} — {r['supplier_name']} "
            f"({fmt_datetime_from_record(r, 'return_date')})"
            + (f" · {r['invoice_no']}" if r.get("invoice_no") else "")
        ),
        "purchase_returns", "Purchase Returns",
        action_panel=action_panel,
        kpi_labels=("Returns (filtered)", "Return Total", None),
        status_options=["All"],
    )


def sale_return_register_list(action_panel=None):
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
    cols = [
        {"field": "return_no", "label": "Return No"},
        {"field": "return_date", "label": "Date / Time", "format": "datetime"},
        {"field": "customer_name", "label": "Customer"},
        {"field": "invoice_no", "label": "Invoice"},
        {"field": "total", "label": "Total", "format": "money"},
        {"field": "notes", "label": "Notes"},
    ]
    return document_register(
        "sr_reg", db.search_sale_returns, cols, "Customer", party_opts, "customer_id",
        lambda r: (
            f"{r['return_no']} — {r['customer_name']} "
            f"({fmt_datetime_from_record(r, 'return_date')})"
            + (f" · {r['invoice_no']}" if r.get("invoice_no") else "")
        ),
        "sale_returns", "Sale Returns",
        action_panel=action_panel,
        kpi_labels=("Returns (filtered)", "Return Total", None),
        status_options=["All"],
    )


def quotation_register_list():
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
    cols = [
        {"field": "document_no", "label": "Quote No"},
        {"field": "quote_date", "label": "Date / Time", "format": "datetime"},
        {"field": "customer_name", "label": "Customer"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
        {"field": "valid_until", "label": "Valid Until"},
    ]
    return document_register(
        "qt_reg", db.search_quotations, cols, "Customer", party_opts, "customer_id",
        lambda r: f"{r['document_no']} — {r['customer_name']}",
        "quotations", "Quotations",
    )


def sales_order_register_list(open_handler=None):
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
    cols = [
        {"field": "document_no", "label": "Order No"},
        {"field": "order_date", "label": "Date / Time", "format": "datetime"},
        {"field": "customer_name", "label": "Customer"},
        {"field": "dispatch_town", "label": "Delivery Stop"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
    ]
    st.caption(
        "Pending orders (**Active** / **Partial**) are always listed here, even when Period is Today."
    )
    so_status = [
        "All",
        "Pending",
        "open",
        "partial",
        "closed",
        "cancelled",
        "draft",
        "pending_approval",
        "approved",
        "rejected",
    ]
    return document_register(
        "so_reg", db.search_sales_orders, cols, "Customer", party_opts, "customer_id",
        lambda r: hlp.sales_order_picker_label(r, show_total=False),
        "sales_orders", "Sales Orders",
        open_handler=open_handler,
        status_options=so_status,
    )


def purchase_order_register_list():
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}
    cols = [
        {"field": "document_no", "label": "PO No"},
        {"field": "order_date", "label": "Date / Time", "format": "datetime"},
        {"field": "supplier_name", "label": "Supplier"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
    ]
    return document_register(
        "po_reg", db.search_purchase_orders, cols, "Supplier", party_opts, "supplier_id",
        lambda r: f"{r['document_no']} — {r['supplier_name']}",
        "purchase_orders", "Purchase Orders",
    )


def grn_register_list(action_panel=None):
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}
    cols = [
        {"field": "document_no", "label": "GRN No"},
        {"field": "grn_date", "label": "Date / Time", "format": "datetime"},
        {"field": "supplier_name", "label": "Supplier"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
    ]
    return document_register(
        "grn_reg", db.search_grns, cols, "Supplier", party_opts, "supplier_id",
        lambda r: f"{r['document_no']} — {r['supplier_name']}",
        "grns", "Goods Receipt Notes", action_panel=action_panel,
    )


def delivery_note_register_list(action_panel=None):
    party_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
    cols = [
        {"field": "document_no", "label": "DN No"},
        {"field": "dn_date", "label": "Date / Time", "format": "datetime"},
        {"field": "customer_name", "label": "Customer"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
    ]
    return document_register(
        "dn_reg", db.search_delivery_notes, cols, "Customer", party_opts, "customer_id",
        lambda r: f"{r['document_no']} — {r['customer_name']}",
        "delivery_notes", "Delivery Notes", action_panel=action_panel,
    )


def purchase_requisition_register_list():
    cols = [
        {"field": "document_no", "label": "Req No"},
        {"field": "req_date", "label": "Date / Time", "format": "datetime"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "subtotal", "label": "Subtotal", "format": "money"},
    ]
    return document_register(
        "prq_reg", db.search_purchase_requisitions, cols, None, None, None,
        lambda r: f"{r['document_no']} ({fmt_datetime_from_record(r, 'req_date')})",
        "purchase_requisitions", "Purchase Requisitions",
        kpi_labels=("Requisitions (filtered)", "Estimated Total", None),
    )


def invoice_workflow_tab(key_prefix, search_fn, status, party_label, review_fn, extra_actions=None):
    """Paginated invoice list for approval workflow tabs."""
    party_opts = (
        {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
        if party_label == "Customer"
        else {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}
    )
    party_kw = "customer_id" if party_label == "Customer" else "supplier_id"
    date_field = "sale_date" if party_label == "Customer" else "purchase_date"
    party_field = "customer_name" if party_label == "Customer" else "supplier_name"
    cols = [
        {"field": "invoice_no", "label": "Invoice"},
        {"field": date_field, "label": "Date / Time", "format": "datetime"},
        {"field": party_field, "label": party_label},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "total", "label": "Total", "format": "money"},
        {"field": "weight_slip_no", "label": "Weight Slip"},
        {"field": "gate_pass_no", "label": "Gate Pass"},
        {"field": "weight_match_status", "label": "Weight Match"},
    ]
    from erp_ui.invoice_status_ui import status_badge_html
    st.markdown(
        f'<div class="txn-status-strip">{status_badge_html(status)}'
        f'&nbsp;<span class="txn-queue-label">Approval queue</span></div>',
        unsafe_allow_html=True,
    )
    filters = _filter_bar(
        key_prefix, party_label, party_opts, default_period="Today",
        show_payment=False, show_status=False,
    )
    filters["status"] = status
    selected = _register_core(
        key_prefix, search_fn, cols,
        lambda r: f"{r['invoice_no']} — {r.get(party_field, '')}",
        f"{key_prefix}_export", f"Invoices — {status.replace('_', ' ').title()}",
        filters, party_kw,
        kpi_labels=(f"Records ({status.replace('_', ' ')})", "Total Amount", None),
        show_kpi_paid=False,
    )
    if selected:
        st.divider()
        review_fn(selected["id"], extra_actions)
    return selected


def weight_slip_register_list():
    ws_status = ["All", "first_weigh", "completed"]
    filters = _filter_bar(
        "ws_reg", None, None, "Today",
        show_payment=False, show_status=True, status_options=ws_status,
    )
    status = filters["status"] if filters.get("status") not in (None, "All") else None
    filter_sig = tuple(sorted((k, str(v)) for k, v in filters.items()))
    if st.session_state.get("ws_reg_fsig") != filter_sig:
        st.session_state["ws_reg_page"] = 1
    st.session_state["ws_reg_fsig"] = filter_sig
    page = st.session_state.get("ws_reg_page", 1)
    result = db.search_weight_slips(
        q=filters["q"], from_date=filters["from_date"], to_date=filters["to_date"],
        status=status, page=page, page_size=filters["page_size"],
    )
    st.session_state["ws_reg_page"] = result["page"]
    cols = [
        {"field": "document_no", "label": "Slip No"},
        {"field": "slip_date", "label": "Date / Time", "format": "datetime", "time_field": "slip_time"},
        {"field": "status", "label": "Status", "format": "status"},
        {"field": "vehicle_no", "label": "Vehicle"},
        {"field": "party_name", "label": "Party"},
        {"field": "product_name", "label": "Item"},
        {"field": "net_weight", "label": "Net (kg)"},
        {"field": "sales_invoice_no", "label": "Sales Inv"},
        {"field": "purchase_invoice_no", "label": "Purchase Inv"},
    ]
    k1, k2 = st.columns(2)
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Records (filtered)</p>"
        f"<p class='txn-kpi-val'>{result['total']:,}</p></div>",
        unsafe_allow_html=True,
    )
    items = result["items"]
    if not items:
        st.info("No weight slips match your filters.")
        return None
    # Single Party column (customer or supplier account code + name)
    from erp_ui.helpers import slip_party_display
    for r in items:
        r["party_name"] = slip_party_display(r)
    _status_counts_strip(items)
    _render_register_html_table(items, cols)
    _pagination("ws_reg", result)
    if st.button("Export filtered (all pages)", key="ws_reg_export"):
        full = db.search_weight_slips(
            q=filters["q"], from_date=filters["from_date"], to_date=filters["to_date"],
            status=status, export_all=True,
        )
        for r in full["items"]:
            r["party_name"] = slip_party_display(r)
        _export_df(_build_df(full["items"], cols), "weight_slips", "Weight Slips Register")
    if st.button("Sync item from linked invoices", key="ws_reg_sync_item", help="Updates slip item/party from invoice lines for old links"):
        try:
            n = db.backfill_slip_items_from_linked_invoices(None)
            ff.action_done(f"Updated **{n}** slip(s) from their sales/purchase invoices.")
        except Exception as e:
            st.error(str(e))
    return items


def gate_pass_register_list():
    gp_status = ["All", "draft", "approved", "cancelled"]
    filters = _filter_bar(
        "gp_reg", None, None, "Today",
        show_payment=False, show_status=True, status_options=gp_status,
    )
    status = filters["status"] if filters.get("status") not in (None, "All") else None
    filter_sig = tuple(sorted((k, str(v)) for k, v in filters.items()))
    if st.session_state.get("gp_reg_fsig") != filter_sig:
        st.session_state["gp_reg_page"] = 1
    st.session_state["gp_reg_fsig"] = filter_sig
    page = st.session_state.get("gp_reg_page", 1)
    type_lbl = st.selectbox(
        "Pass Type", ["All", "Material In", "Material Out", "FG Dispatch"], key="gp_reg_type",
    )
    type_map = {"Material In": "material_in", "Material Out": "material_out", "FG Dispatch": "fg_dispatch"}
    pass_type = type_map.get(type_lbl)
    result = db.search_gate_passes(
        q=filters["q"], pass_type=pass_type, from_date=filters["from_date"], to_date=filters["to_date"],
        status=status, page=page, page_size=filters["page_size"],
    )
    st.session_state["gp_reg_page"] = result["page"]
    cols = [
        {"field": "document_no", "label": "Gate Pass"},
        {"field": "pass_date", "label": "Date / Time", "format": "datetime", "time_field": "pass_time"},
        {"field": "pass_type", "label": "Type"},
        {"field": "party_name", "label": "Party"},
        {"field": "vehicle_no", "label": "Vehicle"},
        {"field": "quantity", "label": "Qty"},
        {"field": "weight", "label": "Weight (kg)"},
        {"field": "sales_invoice_no", "label": "Sales Inv"},
        {"field": "purchase_invoice_no", "label": "Purchase Inv"},
        {"field": "status", "label": "Status", "format": "status"},
    ]
    st.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Records (filtered)</p>"
        f"<p class='txn-kpi-val'>{result['total']:,}</p></div>",
        unsafe_allow_html=True,
    )
    items = result["items"]
    if not items:
        st.info("No gate passes match your filters.")
        return None
    _status_counts_strip(items)
    _render_register_html_table(items, cols)
    _pagination("gp_reg", result)
    if st.button("Export filtered (all pages)", key="gp_reg_export"):
        full = db.search_gate_passes(
            q=filters["q"], pass_type=pass_type, from_date=filters["from_date"], to_date=filters["to_date"],
            status=status, export_all=True,
        )
        _export_df(_build_df(full["items"], cols), "gate_pass_register", "Gate Pass Register")
    return items


def workflow_register_list(key_prefix, search_fn, status, title, party_label="Customer"):
    """Deprecated alias — use invoice_workflow_tab."""
    return invoice_workflow_tab(key_prefix, search_fn, status, party_label, lambda _id, _ea: None)


def _export_df(df, name, title):
    if df is None or df.empty:
        return
    from erp_ui.report_print import report_toolbar
    report_toolbar(df, title or name.replace("_", " ").title(), name, key_prefix=f"ex_{name}")
