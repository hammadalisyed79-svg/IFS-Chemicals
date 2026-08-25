"""Inventory / stock pages — extracted from app.py."""

from datetime import date

import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff


def item_options(active_only=True):
    rows = sorted(
        db.get_items(active_only=active_only),
        key=lambda r: hlp.natural_code_sort_key(r.get("code")),
    )
    return {f"{r['code']} - {r['name']} ({r['stock_qty']} {r['unit']})": r for r in rows}


def export_df(df, name, title=None, period="", filters=None, summary=None):
    if df is None or getattr(df, 'empty', True):
        return
    from erp_ui.report_print import report_toolbar
    from erp_ui.report_profiles import report_layout, _report_profile_key
    lbl = title or name.replace("_", " ").title()
    layout_key = _report_profile_key(lbl) or lbl
    report_toolbar(
        df, lbl, name,
        period=period or "",
        filters=filters,
        summary=summary,
        key_prefix=f"ex_{name}",
        layout=report_layout(layout_key),
    )



def page_inventory():
    from erp_ui.helpers import sticky_page_tabs, render_stock_kpi_strip, render_stock_html_table

    peek = st.session_state.get("inv_page_tab") or "Current Stock"
    hlp.std_page_header(
        "Stock",
        title="Inventory",
        status="register" if peek == "Current Stock" else None,
        status_kind="shell" if peek == "Current Stock" else "invoice",
    )
    tab = sticky_page_tabs(
        ["Current Stock", "Stock Adjustment", "Adjustment History"],
        "inv_page_tab",
    )

    if tab == "Current Stock":
        rows = db.get_inventory()
        if rows:
            render_stock_kpi_strip(rows)
            render_stock_html_table(rows)
        else:
            st.info("No inventory data.")

    elif tab == "Stock Adjustment":
        items_dict = item_options()
        if not items_dict:
            st.warning("Add items first.")
            return
        with st.form("stock_adjust"):
            item_lbl = st.selectbox("Item", list(items_dict.keys()))
            adj_date = st.date_input("Date", value=date.today())
            adj_type = st.selectbox("Adjustment Type", ["in", "out"])
            qty = st.number_input("Quantity", min_value=0.01, value=1.0)
            reason = st.text_input("Reason")
            if st.form_submit_button("Apply Adjustment"):
                item = items_dict[item_lbl]
                db.add_inventory_adjustment(item["id"], str(adj_date), adj_type, qty, reason)
                ff.finish_new_entry(form_id="inv_adj", message="Stock adjusted.")

    elif tab == "Adjustment History":
        from erp_ui.helpers import render_adjustment_html_table

        hist = db.get_inventory_adjustments()
        if hist:
            render_adjustment_html_table(hist)
            del_sel = st.selectbox("Delete adjustment", ["—"] + [f"{h['id']} - {h['item_name']} ({h['adjustment_date']})" for h in hist])
            if del_sel != "—" and st.button("Delete Selected Adjustment"):
                adj_id = int(del_sel.split(" - ")[0])
                db.delete_inventory_adjustment(adj_id)
                ff.action_done("Adjustment deleted.")
        else:
            st.info("No adjustments recorded.")


def page_stock():
    from erp_ui.helpers import render_stock_kpi_strip

    hlp.std_page_header("Stock", status="register", status_kind="shell")
    rows = db.get_inventory()
    if not rows:
        st.info("No inventory data.")
        return

    render_stock_kpi_strip(rows)

    q = st.text_input(
        "Search stock / item",
        key="stock_page_search",
        placeholder="Type code, name, category, or unit…",
    ).strip()
    filtered = hlp.filter_master_records(rows, q) if q else rows
    filtered = sorted(filtered, key=lambda r: hlp.natural_code_sort_key(r.get("code")))

    c_f1, c_f2, c_f3 = st.columns([1, 1, 2])
    only_neg = c_f1.checkbox("Negative qty only", key="stock_page_neg", value=False)
    only_pos = c_f2.checkbox("Positive qty only", key="stock_page_pos", value=False)
    if only_neg:
        filtered = [r for r in filtered if float(r.get("stock_qty") or 0) < 0]
    elif only_pos:
        filtered = [r for r in filtered if float(r.get("stock_qty") or 0) > 0]

    if q:
        st.caption(f"**{len(filtered):,}** match(es) of **{len(rows):,}** items")
    else:
        st.caption(f"Showing **{len(filtered):,}** items — type above to search")

    if not filtered:
        st.warning("No items match this search.")
        return

    df = pd.DataFrame(filtered)[
        ["code", "name", "category", "unit", "stock_qty", "purchase_price", "reorder_level"]
    ]
    df["stock_value"] = df["stock_qty"] * df["purchase_price"]
    df.columns = ["Code", "Name", "Category", "Unit", "Qty", "Cost Price", "Reorder Level", "Stock Value"]

    sel_key = "stock_page_sel_codes"
    editor_ver_key = "stock_page_editor_ver"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = []
    if editor_ver_key not in st.session_state:
        st.session_state[editor_ver_key] = 0

    shown_codes = set(df["Code"].astype(str).tolist())
    # Drop selections that are no longer in the filtered view
    st.session_state[sel_key] = [c for c in st.session_state[sel_key] if c in shown_codes]

    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("Select all shown", key="stock_page_sel_all"):
        st.session_state[sel_key] = list(df["Code"].astype(str))
        st.session_state[editor_ver_key] = int(st.session_state[editor_ver_key]) + 1
        st.rerun()
    if b2.button("Clear selection", key="stock_page_sel_clr"):
        st.session_state[sel_key] = []
        st.session_state[editor_ver_key] = int(st.session_state[editor_ver_key]) + 1
        st.rerun()
    b3.caption(f"Selected: **{len(st.session_state[sel_key])}**")

    # Checkbox column for multi-select download
    edit_df = df.copy()
    edit_df.insert(0, "Select", edit_df["Code"].astype(str).isin(st.session_state[sel_key]))
    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[c for c in edit_df.columns if c != "Select"],
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "Qty": st.column_config.NumberColumn(format="%.3f"),
            "Cost Price": st.column_config.NumberColumn(format="%.2f"),
            "Stock Value": st.column_config.NumberColumn(format="%.2f"),
        },
        key=f"stock_page_editor_{st.session_state[editor_ver_key]}",
    )
    picked = edited["Select"].fillna(False).astype(bool)
    st.session_state[sel_key] = edited.loc[picked, "Code"].astype(str).tolist()

    selected_codes = set(st.session_state[sel_key])
    df_selected = df[df["Code"].astype(str).isin(selected_codes)] if selected_codes else df.iloc[0:0]
    value_scope = df_selected if len(df_selected) else df
    scope_lbl = "selected" if len(df_selected) else "shown"
    st.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Stock Value ({scope_lbl})</p>"
        f"<p class='txn-kpi-val'>{hlp.fmt_money(value_scope['Stock Value'].sum())}</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown("**Download**")
    d1, d2 = st.columns(2)
    with d1:
        st.caption("Selected items" if len(df_selected) else "Select rows above (or Select all shown)")
        if len(df_selected):
            hlp.export_buttons(df_selected, "stock_selected", title="Stock — Selected Items")
        else:
            st.info("Tick items to download a selection.")
    with d2:
        st.caption("All shown (search / filter result)")
        hlp.export_buttons(df, "stock_filtered", title="Stock — Filtered List")


def page_stock_adjustments():
    from erp_ui.helpers import sticky_page_tabs, render_adjustment_html_table

    hlp.std_page_header("Stock Adjustments")
    tab = sticky_page_tabs(["New Adjustment", "History"], "stock_adj_tab")
    if tab == "New Adjustment":
        _, item_id, item_row = hlp.smart_select("Product", db.get_items(), "adj_item", "id",
                                                lambda r: f"{r['code']} - {r['name']} ({r.get('stock_qty',0)})")
        if item_id:
            with st.form("stock_adjust"):
                adj_date = st.date_input("Date", value=date.today())
                adj_type = st.selectbox("Adjustment Type", ["in", "out"])
                qty = st.number_input("Quantity", min_value=0.01, value=1.0)
                reason = st.text_input("Reason")
                if st.form_submit_button("Apply Adjustment"):
                    db.add_inventory_adjustment(item_id, str(adj_date), adj_type, qty, reason)
                    ff.finish_new_entry(form_id="inv_adj", message="Stock adjusted.")
    elif tab == "History":
        hist = db.get_inventory_adjustments()
        if hist:
            render_adjustment_html_table(hist)
        else:
            st.info("No adjustments recorded.")


def page_stock_transfers():
    hlp.std_page_header("Stock Transfers", status="posted", status_kind="shell")
    wh_opts = hlp.warehouse_opts()
    if len(wh_opts) < 2:
        st.warning("Add at least two warehouses to transfer stock.")
        return
    with st.container(border=True):
        _, pid, _ = hlp.smart_select("Product", db.get_items(), "xfer_prod", "id",
                                     lambda r: f"{r['code']} - {r['name']}")
        wh_keys = list(wh_opts.keys())
        c1, c2 = st.columns(2)
        from_wh = c1.selectbox("From Warehouse", wh_keys)
        to_wh = c2.selectbox("To Warehouse", wh_keys)
        qty = st.number_input("Quantity", min_value=0.01, value=1.0)
        xfer_date = st.date_input("Transfer Date", value=date.today())
        if st.button("Transfer Stock", type="primary") and pid and from_wh != to_wh:
            db.add_inventory_adjustment(pid, str(xfer_date), "out", qty, f"Transfer to {to_wh}")
            db.add_inventory_adjustment(pid, str(xfer_date), "in", qty, f"Transfer from {from_wh}")
            ff.action_done("Transfer recorded.")


def page_stock_report():
    hlp.std_page_header("Stock Report", status="register", status_kind="shell")
    st.caption("View stock **item-wise**, **group-wise**, or **BOM / composition-wise**.")

    from erp_ui.helpers import form_compact, master_group_filter, render_stock_report_item_table
    from application.data_gateway import COMPOSITION_TYPES

    with form_compact("stock_rpt"):
        c1, c2, c3 = st.columns([1.8, 1.3, 1.3])
        view = c1.radio(
            "View",
            ["Item wise", "Group wise", "BOM wise"],
            horizontal=True,
            key="stock_rpt_view",
        )
        with c2:
            gid = master_group_filter("product", "sr") if view != "BOM wise" else None
        sort_opts = {
            "Item wise": ["Code", "Name", "Stock qty", "Stock value", "Status"],
            "Group wise": ["Group code", "Group name", "Items", "Stock value"],
            "BOM wise": ["BOM", "Finished code", "Role", "Item code", "Stock qty", "Stock value"],
        }
        sort_by = c3.selectbox("Sort by", sort_opts[view], key=f"stock_rpt_sort_{view}")

        q = st.text_input(
            "Search",
            key="stock_rpt_q",
            placeholder="Code, name, group, BOM…",
        ).strip().lower()

        bom_type = None
        bom_status = "approved"
        if view == "BOM wise":
            b1, b2 = st.columns(2)
            type_opts = {"All compositions": None}
            for code, label in COMPOSITION_TYPES.items():
                type_opts[label] = code
            bom_lbl = b1.selectbox("Composition type", list(type_opts.keys()), key="stock_rpt_bom_type")
            bom_type = type_opts[bom_lbl]
            bom_status = b2.selectbox(
                "BOM status",
                ["approved", "All", "draft", "inactive"],
                key="stock_rpt_bom_st",
            )

    if view == "Item wise":
        rows = db.get_stock_report(product_group_id=gid)
        if q:
            rows = [
                r for r in rows
                if q in " ".join(
                    str(r.get(k) or "") for k in ("code", "name", "category", "group_code", "group_name", "item_type")
                ).lower()
            ]
        sort_key = {
            "Code": lambda r: str(r.get("code") or ""),
            "Name": lambda r: str(r.get("name") or "").lower(),
            "Stock qty": lambda r: float(r.get("stock_qty") or 0),
            "Stock value": lambda r: float(r.get("stock_value") or 0),
            "Status": lambda r: str(r.get("status") or ""),
        }[sort_by]
        reverse = sort_by in ("Stock qty", "Stock value")
        rows = sorted(rows, key=sort_key, reverse=reverse)

        if not rows:
            st.info("No stock data for this view.")
            return
        low_n = sum(1 for r in rows if (r.get("status") or "OK") == "Low")
        neg_n = sum(1 for r in rows if float(r.get("stock_qty") or 0) < 0)
        total_val = sum(float(r.get("stock_value") or 0) for r in rows)
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Items</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Stock Value</p>"
            f"<p class='txn-kpi-val'>{hlp.fmt_money(total_val)}</p></div>",
            unsafe_allow_html=True,
        )
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Below Reorder</p>"
            f"<p class='txn-kpi-val'>{low_n:,}</p></div>",
            unsafe_allow_html=True,
        )
        if low_n or neg_n:
            parts = []
            if low_n:
                parts.append(
                    f'<span class="inv-badge inv-badge-pending">Low</span>&nbsp;<strong>{low_n}</strong>'
                )
            if neg_n:
                parts.append(
                    f'<span class="inv-badge inv-badge-rejected">Negative</span>&nbsp;<strong>{neg_n}</strong>'
                )
            st.markdown(
                f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
                unsafe_allow_html=True,
            )
        render_stock_report_item_table(rows)
        df = pd.DataFrame([{
            "Code": r.get("code"),
            "Name": r.get("name"),
            "Category": r.get("category") or "—",
            "Group": r.get("group_name") or "Unassigned",
            "Type": r.get("item_type") or "",
            "Unit": r.get("unit") or "",
            "Stock Qty": round(float(r.get("stock_qty") or 0), 4),
            "Unit Cost": round(float(r.get("unit_cost") or r.get("purchase_price") or 0), 2),
            "Stock Value": round(float(r.get("stock_value") or 0), 2),
            "Reorder": round(float(r.get("reorder_level") or 0), 4),
            "Status": r.get("status") or "OK",
        } for r in rows])
        export_df(df, "stock_report_item", "Stock Report — Item wise")
        if low_n:
            st.warning(f"{low_n} item(s) below reorder level.")

    elif view == "Group wise":
        rows = db.get_stock_report_group_wise(product_group_id=gid)
        if q:
            rows = [
                r for r in rows
                if q in f"{r.get('group_code')} {r.get('group_name')}".lower()
            ]
        sort_key = {
            "Group code": lambda r: str(r.get("group_code") or ""),
            "Group name": lambda r: str(r.get("group_name") or "").lower(),
            "Items": lambda r: int(r.get("items") or 0),
            "Stock value": lambda r: float(r.get("stock_value") or 0),
        }[sort_by]
        reverse = sort_by in ("Items", "Stock value")
        rows = sorted(rows, key=sort_key, reverse=reverse)
        if not rows:
            st.info("No group stock data.")
            return
        total_val = sum(float(r.get("stock_value") or 0) for r in rows)
        low_groups = sum(1 for r in rows if int(r.get("low_items") or 0) > 0)
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Groups</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Stock Value</p>"
            f"<p class='txn-kpi-val'>{hlp.fmt_money(total_val)}</p></div>",
            unsafe_allow_html=True,
        )
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Groups with Low Items</p>"
            f"<p class='txn-kpi-val'>{low_groups:,}</p></div>",
            unsafe_allow_html=True,
        )
        from html import escape
        ths = "".join(
            f"<th>{h}</th>"
            for h in ("Group Code", "Group Name", "Items", "Stock Qty", "Stock Value", "Low Items")
        )
        body = []
        for r in rows:
            low_i = int(r.get("low_items") or 0)
            low_badge = (
                f'<span class="inv-badge inv-badge-pending">{low_i}</span>'
                if low_i
                else '<span class="inv-badge inv-badge-approved">0</span>'
            )
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('group_code') or ''))}</td>"
                f"<td>{escape(str(r.get('group_name') or ''))}</td>"
                f"<td class='txn-num'>{int(r.get('items') or 0):,}</td>"
                f"<td class='txn-num'>{float(r.get('stock_qty') or 0):,.4f}</td>"
                f"<td class='txn-num'>{escape(hlp.fmt_money(r.get('stock_value')))}</td>"
                f"<td class='txn-status-cell'>{low_badge}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        df = pd.DataFrame([{
            "Group Code": r.get("group_code"),
            "Group Name": r.get("group_name"),
            "Items": int(r.get("items") or 0),
            "Stock Qty": round(float(r.get("stock_qty") or 0), 4),
            "Stock Value": round(float(r.get("stock_value") or 0), 2),
            "Low Items": int(r.get("low_items") or 0),
        } for r in rows])
        export_df(df, "stock_report_group", "Stock Report — Group wise")

    else:  # BOM wise
        rows = db.get_stock_report_bom_wise(
            composition_type=bom_type,
            status=bom_status or "approved",
        )
        if q:
            rows = [
                r for r in rows
                if q in " ".join(
                    str(r.get(k) or "")
                    for k in ("bom_no", "finished_code", "finished_name", "code", "name", "composition_type")
                ).lower()
            ]
        sort_key = {
            "BOM": lambda r: str(r.get("bom_no") or ""),
            "Finished code": lambda r: str(r.get("finished_code") or ""),
            "Role": lambda r: str(r.get("role") or ""),
            "Item code": lambda r: str(r.get("code") or ""),
            "Stock qty": lambda r: float(r.get("stock_qty") or 0),
            "Stock value": lambda r: float(r.get("stock_value") or 0),
        }[sort_by]
        reverse = sort_by in ("Stock qty", "Stock value")
        # Stable: keep BOM then role (Finished first) when sorting by BOM/finished
        if sort_by in ("BOM", "Finished code"):
            rows = sorted(
                rows,
                key=lambda r: (
                    sort_key(r),
                    0 if r.get("role") == "Finished" else 1,
                    str(r.get("code") or ""),
                ),
                reverse=reverse,
            )
        else:
            rows = sorted(rows, key=sort_key, reverse=reverse)

        if not rows:
            st.info("No BOM / composition stock data. Approve compositions under Production → BOM.")
            return
        fg_val = sum(float(r.get("stock_value") or 0) for r in rows if r.get("role") == "Finished")
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>BOM Lines</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Finished Goods Value</p>"
            f"<p class='txn-kpi-val'>{hlp.fmt_money(fg_val)}</p></div>",
            unsafe_allow_html=True,
        )
        bom_n = len({r.get("bom_no") for r in rows if r.get("bom_no")})
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Compositions</p>"
            f"<p class='txn-kpi-val'>{bom_n:,}</p></div>",
            unsafe_allow_html=True,
        )
        from html import escape
        ths = "".join(
            f"<th>{h}</th>"
            for h in (
                "BOM", "Ver", "Composition", "Finished", "Role", "Item",
                "BOM Qty", "Unit", "Stock Qty", "Unit Cost", "Stock Value",
            )
        )
        body = []
        for r in rows:
            role = r.get("role") or ""
            role_badge = (
                '<span class="inv-badge inv-badge-approved">Finished</span>'
                if role == "Finished"
                else f'<span class="inv-badge inv-badge-draft">{escape(role)}</span>'
            )
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('bom_no') or ''))}</td>"
                f"<td>{escape(str(r.get('version') or ''))}</td>"
                f"<td>{escape(str(r.get('composition_type') or ''))}</td>"
                f"<td>{escape(str(r.get('finished_code') or ''))} — {escape(str(r.get('finished_name') or ''))}</td>"
                f"<td class='txn-status-cell'>{role_badge}</td>"
                f"<td>{escape(str(r.get('code') or ''))} — {escape(str(r.get('name') or ''))}</td>"
                f"<td class='txn-num'>{float(r.get('bom_qty') or 0):,.4f}</td>"
                f"<td>{escape(str(r.get('unit') or ''))}</td>"
                f"<td class='txn-num'>{float(r.get('stock_qty') or 0):,.4f}</td>"
                f"<td class='txn-num'>{escape(hlp.fmt_money(r.get('unit_cost')))}</td>"
                f"<td class='txn-num'>{escape(hlp.fmt_money(r.get('stock_value')))}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        df = pd.DataFrame([{
            "BOM": r.get("bom_no"),
            "Ver": r.get("version"),
            "Composition": r.get("composition_type"),
            "Finished Code": r.get("finished_code"),
            "Finished Name": r.get("finished_name"),
            "Role": r.get("role"),
            "Item Code": r.get("code"),
            "Item Name": r.get("name"),
            "BOM Qty": round(float(r.get("bom_qty") or 0), 4),
            "Unit": r.get("unit") or "",
            "Stock Qty": round(float(r.get("stock_qty") or 0), 4),
            "Unit Cost": round(float(r.get("unit_cost") or 0), 2),
            "Stock Value": round(float(r.get("stock_value") or 0), 2),
        } for r in rows])
        export_df(df, "stock_report_bom", "Stock Report — BOM wise")

