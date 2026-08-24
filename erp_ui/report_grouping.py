"""Shared group filters and view modes for finance & analytical reports."""

import streamlit as st
from db_report_groups import TRIAL_VIEW_LABELS, PARTY_VIEW_LABELS, TRIAL_VIEW_DETAIL, PARTY_VIEW_DETAIL
from db_groups import group_options


def _mode_from_widget(labels_map: dict, session_key: str, default: str) -> str:
    label = st.session_state.get(session_key)
    for mode, lbl in labels_map.items():
        if lbl == label:
            return mode
    return default


def finance_group_filters(key_prefix: str = "fin"):
    """Trial balance / balance sheet / GL — chart account group + view mode."""
    st.markdown("**Group reporting**")
    c1, c2 = st.columns(2)
    opts = group_options("account", include_none=False, active_only=True)
    if opts:
        glabels = ["(All chart account groups)"] + list(opts.keys())
        gsel = c1.selectbox("Chart account group", glabels, key=f"{key_prefix}_ag")
        account_group_id = opts[gsel] if gsel != "(All chart account groups)" else None
    else:
        c1.caption("No chart account groups — create under **Account & Item Groups**.")
        account_group_id = None
    view_labels = list(TRIAL_VIEW_LABELS.values())
    c2.selectbox(
        "View",
        view_labels,
        key=f"{key_prefix}_fview",
        help="Summary rolls up accounts by type or by your custom chart account groups.",
    )
    view_mode = _mode_from_widget(TRIAL_VIEW_LABELS, f"{key_prefix}_fview", TRIAL_VIEW_DETAIL)
    return account_group_id, view_mode


def party_group_filter(entity_type: str, key_prefix: str, label: str | None = None):
    """Filter by customer / supplier / product master group."""
    opts = group_options(entity_type, include_none=False, active_only=True)
    if not opts:
        return None
    label = label or f"{entity_type.title()} group"
    glabels = ["(All groups)"] + list(opts.keys())
    gsel = st.selectbox(label, glabels, key=f"{key_prefix}_{entity_type}_grp")
    return opts[gsel] if gsel != "(All groups)" else None


def party_view_mode(key_prefix: str):
    st.selectbox("View", list(PARTY_VIEW_LABELS.values()), key=f"{key_prefix}_pview")
    return _mode_from_widget(PARTY_VIEW_LABELS, f"{key_prefix}_pview", PARTY_VIEW_DETAIL)


def report_group_filter_row(meta: dict, key_prefix: str = "rpt"):
    """Optional group filters from report catalog flags. Returns dict of filter values."""
    f = meta.get("filters", {})
    out = {
        "customer_group_id": None,
        "supplier_group_id": None,
        "product_group_id": None,
        "account_group_id": None,
        "view_mode": TRIAL_VIEW_DETAIL,
        "party_view_mode": PARTY_VIEW_DETAIL,
    }
    flags = [
        f.get("customer_group"),
        f.get("supplier_group"),
        f.get("product_group"),
        f.get("account_group"),
        f.get("group_view"),
        f.get("party_group_view"),
    ]
    if not any(flags):
        return out

    st.markdown("**Group reporting**")
    n_slots = sum([
        bool(f.get("account_group") or f.get("group_view")),
        bool(f.get("customer_group")),
        bool(f.get("supplier_group")),
        bool(f.get("product_group")),
        bool(f.get("group_view")),
        bool(f.get("party_group_view")),
    ])
    ncol = min(max(n_slots, 1), 4)
    cols = st.columns(ncol)
    ci = 0

    def _col():
        nonlocal ci
        c = cols[ci % ncol]
        ci += 1
        return c

    if f.get("account_group") or f.get("group_view"):
        with _col():
            opts = group_options("account", include_none=False, active_only=True)
            if opts:
                glabels = ["(All chart account groups)"] + list(opts.keys())
                gsel = st.selectbox("Chart account group", glabels, key=f"{key_prefix}_ag")
                out["account_group_id"] = opts[gsel] if gsel != "(All chart account groups)" else None
            else:
                st.caption("No chart account groups defined.")
    if f.get("customer_group"):
        with _col():
            out["customer_group_id"] = party_group_filter("customer", key_prefix, "Customer group")
    if f.get("supplier_group"):
        with _col():
            out["supplier_group_id"] = party_group_filter("supplier", key_prefix, "Supplier group")
    if f.get("product_group"):
        with _col():
            out["product_group_id"] = party_group_filter("product", key_prefix, "Product group")
    if f.get("group_view"):
        with _col():
            st.selectbox("View", list(TRIAL_VIEW_LABELS.values()), key=f"{key_prefix}_fview")
            out["view_mode"] = _mode_from_widget(TRIAL_VIEW_LABELS, f"{key_prefix}_fview", TRIAL_VIEW_DETAIL)
    if f.get("party_group_view"):
        with _col():
            out["party_view_mode"] = party_view_mode(key_prefix)
    return out
