"""Bulk production from physical stock — Inventory worksheet."""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd
import streamlit as st

from application import data_gateway as db
from erp_ui import form_flow as ff
from erp_ui import helpers as hlp


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _user_id():
    u = st.session_state.get("user") or {}
    try:
        return int(u.get("id") or 0) or None
    except (TypeError, ValueError):
        return None


def page_production_from_physical():
    from erp_ui.helpers import sticky_page_tabs

    hlp.std_page_header(
        "Production from Physical",
        status="register",
        status_kind="shell",
    )
    tab = sticky_page_tabs(["Worksheet", "History"], "prod_phy_tab")

    if tab == "History":
        _tab_history()
        return
    _tab_worksheet()


def _tab_history():
    runs = db.list_production_month_runs(limit=48)
    if not runs:
        st.info("No saved production worksheets yet.")
        return
    df = pd.DataFrame([
        {
            "ID": r["id"],
            "Month": r.get("year_month"),
            "Warehouse": f"{r.get('warehouse_code') or ''} — {r.get('warehouse_name') or ''}".strip(" —"),
            "Status": (r.get("status") or "").upper(),
            "Production": float(r.get("total_production") or 0),
            "Physical": float(r.get("total_physical") or 0),
            "Posted": r.get("posted_at") or "",
            "Updated": r.get("modified_at") or r.get("created_at") or "",
        }
        for r in runs
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _bump_pick_editor(wh_id: int, ym: str) -> None:
    ver_key = f"prod_phy_pick_ver_{wh_id}_{ym}"
    st.session_state[ver_key] = int(st.session_state.get(ver_key, 0) or 0) + 1


def _tab_worksheet():
    wh_opts = hlp.warehouse_opts()
    if not wh_opts:
        st.warning("Create a warehouse first.")
        return

    today = date.today()
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    wh_lbl = c1.selectbox("Warehouse", list(wh_opts.keys()), key="prod_phy_wh")
    year = int(
        c2.number_input(
            "Year",
            min_value=2020,
            max_value=2035,
            value=today.year,
            step=1,
            key="prod_phy_year",
        )
    )
    month = c3.selectbox(
        "Month",
        list(range(1, 13)),
        index=max(0, today.month - 2) if today.month > 1 else 0,
        format_func=lambda m: f"{m:02d} — {calendar.month_name[m]}",
        key="prod_phy_month",
    )
    wh_id = int(wh_opts[wh_lbl])
    from db_contractors import month_bounds

    fd, td = month_bounds(year, int(month))
    ym = f"{year:04d}-{int(month):02d}"

    st.caption(
        "**Production** = Phy − OS − Return + Sale − Adj · "
        "**Closing** = Phy (physical count). "
        "Tick products below, then **Load / refresh month**. "
        "Enter **Phy** only; production posts as stock-in (excluded from Adj on reload)."
    )

    saved = db.get_production_month_run(wh_id, ym)
    is_posted = bool(saved and (saved.get("status") or "") == "posted")
    if saved:
        st.info(
            f"Saved **{ym}** — status **{(saved.get('status') or 'draft').upper()}** · "
            f"Production {float(saved.get('total_production') or 0):,.2f} · "
            f"Physical {float(saved.get('total_physical') or 0):,.2f}"
            + (
                f" · posted {saved.get('posted_at')}"
                if saved.get("posted_at")
                else ""
            )
        )

    items = sorted(
        db.get_items(active_only=True) or [],
        key=lambda r: hlp.natural_code_sort_key(r.get("code")),
    )
    code_to_id = {
        str(r.get("code") or "").strip(): int(r["id"])
        for r in items
        if r.get("id") and str(r.get("code") or "").strip()
    }
    id_to_item = {int(r["id"]): r for r in items if r.get("id")}

    filter_q = st.text_input(
        "Filter products (code / name / category)",
        key="prod_phy_filter",
        placeholder="e.g. DW or DISHWASH…",
    ).strip()
    filtered = hlp.filter_master_records(items, filter_q) if filter_q else items
    shown_codes = [
        str(r.get("code") or "").strip()
        for r in filtered
        if str(r.get("code") or "").strip() in code_to_id
    ]

    default_codes = []
    if saved and saved.get("lines"):
        default_codes = [
            str(ln.get("product_code") or "").strip()
            for ln in saved["lines"]
            if str(ln.get("product_code") or "").strip() in code_to_id
        ]

    sel_key = f"prod_phy_sel_{wh_id}_{ym}"
    ver_key = f"prod_phy_pick_ver_{wh_id}_{ym}"
    filt_key = f"prod_phy_filt_applied_{wh_id}_{ym}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = list(default_codes)
    if ver_key not in st.session_state:
        st.session_state[ver_key] = 0

    # Remount picker when filter text changes (row set changes)
    if st.session_state.get(filt_key) != filter_q:
        st.session_state[filt_key] = filter_q
        st.session_state[ver_key] = int(st.session_state.get(ver_key, 0) or 0) + 1

    b1, b2, b3, b4 = st.columns([1, 1, 1, 2])
    if b1.button("Select all shown", key="prod_phy_sel_all"):
        # Keep off-filter picks; add every visible code
        keep = [
            c for c in (st.session_state.get(sel_key) or [])
            if c not in shown_codes and c in code_to_id
        ]
        st.session_state[sel_key] = sorted(
            set(keep) | set(shown_codes),
            key=lambda c: hlp.natural_code_sort_key(c),
        )
        _bump_pick_editor(wh_id, ym)
        st.rerun()
    if b2.button("Clear shown", key="prod_phy_sel_clr_shown"):
        # Uncheck only visible rows; keep selections hidden by filter
        st.session_state[sel_key] = [
            c for c in (st.session_state.get(sel_key) or [])
            if c not in shown_codes and c in code_to_id
        ]
        _bump_pick_editor(wh_id, ym)
        st.rerun()
    if b3.button("Clear all", key="prod_phy_sel_clr_all"):
        st.session_state[sel_key] = []
        _bump_pick_editor(wh_id, ym)
        st.rerun()

    selected_now = [
        c for c in (st.session_state.get(sel_key) or []) if c in code_to_id
    ]
    b4.caption(f"Selected: **{len(selected_now)}** of {len(items)} items")
    if selected_now:
        preview = ", ".join(selected_now[:12])
        more = f" (+{len(selected_now) - 12} more)" if len(selected_now) > 12 else ""
        st.caption(f"Current selection: `{preview}{more}`")

    pick_df = pd.DataFrame([
        {
            "Select": code in selected_now,
            "Code": code,
            "Product": (id_to_item.get(code_to_id[code]) or {}).get("name") or "",
            "Category": (id_to_item.get(code_to_id[code]) or {}).get("category") or "",
            "Stock": float(
                (id_to_item.get(code_to_id[code]) or {}).get("stock_qty") or 0
            ),
        }
        for code in shown_codes[:500]
    ])
    if len(shown_codes) > 500:
        st.caption(
            f"Showing first 500 of {len(shown_codes)} filtered products — narrow the filter."
        )

    pick_editor_key = (
        f"prod_phy_pick_{wh_id}_{ym}_v{int(st.session_state.get(ver_key, 0))}"
    )
    if pick_df.empty:
        st.info("No products match this filter.")
        edited_pick = pick_df
    else:
        edited_pick = st.data_editor(
            pick_df,
            hide_index=True,
            use_container_width=True,
            disabled=["Code", "Product", "Category", "Stock"],
            column_config={
                "Select": st.column_config.CheckboxColumn(
                    "Select",
                    help="Tick to include in the worksheet",
                    default=False,
                    width="small",
                ),
                "Stock": st.column_config.NumberColumn(format="%.2f"),
            },
            key=pick_editor_key,
            height=260,
        )

    # Apply checkbox edits: shown rows from editor; keep off-filter selection
    if not edited_pick.empty:
        selected_shown = set()
        for _, row in edited_pick.iterrows():
            code = str(row.get("Code") or "").strip()
            flag = row.get("Select")
            checked = bool(flag) if not isinstance(flag, float) else False
            # pandas may use numpy.bool_
            try:
                checked = bool(flag)
            except Exception:
                checked = False
            if checked and code in code_to_id:
                selected_shown.add(code)
        off_filter = {
            c for c in selected_now if c not in shown_codes and c in code_to_id
        }
        new_sel = sorted(
            selected_shown | off_filter,
            key=lambda c: hlp.natural_code_sort_key(c),
        )
        if new_sel != selected_now:
            st.session_state[sel_key] = new_sel
            selected_now = new_sel

    product_ids = [code_to_id[c] for c in selected_now if c in code_to_id]

    phy_key = f"prod_phy_map_{wh_id}_{ym}"
    if phy_key not in st.session_state:
        if saved and saved.get("lines"):
            st.session_state[phy_key] = {
                int(ln["product_id"]): float(ln.get("physical_qty") or 0)
                for ln in saved["lines"]
                if ln.get("product_id")
            }
        else:
            st.session_state[phy_key] = {}

    load = st.button("Load / refresh month", type="primary", key="prod_phy_load")
    result_key = f"prod_phy_result_{wh_id}_{ym}"
    meta_key = f"prod_phy_meta_{wh_id}_{ym}"

    if load:
        if not product_ids:
            st.warning("Select at least one product (tick the Select column).")
        else:
            calc = db.calculate_production_month(
                wh_id,
                fd,
                td,
                product_ids,
                physical_map=st.session_state.get(phy_key) or {},
            )
            st.session_state[result_key] = calc
            st.session_state[meta_key] = {
                "wh_id": wh_id,
                "ym": ym,
                "fd": fd,
                "td": td,
                "product_ids": list(product_ids),
            }
            for k in list(st.session_state.keys()):
                if str(k).startswith(f"prod_phy_editor_{wh_id}_{ym}"):
                    st.session_state.pop(k, None)
            st.session_state.pop(f"prod_phy_seed_{wh_id}_{ym}", None)
            st.rerun()

    calc = st.session_state.get(result_key)
    meta = st.session_state.get(meta_key) or {}
    if not calc or meta.get("ym") != ym or meta.get("wh_id") != wh_id:
        st.info("Select products (tick **Select**), then click **Load / refresh month**.")
        return

    # If selection changed since last load, prompt to reload
    loaded_ids = set(int(x) for x in (meta.get("product_ids") or []))
    if set(product_ids) != loaded_ids:
        st.warning(
            "Selection changed since last load — click **Load / refresh month** "
            "to rebuild the worksheet."
        )

    lines = calc.get("lines") or []
    if not lines:
        st.warning("No lines loaded.")
        return

    seed_key = f"prod_phy_seed_{wh_id}_{ym}"
    editor_key = f"prod_phy_editor_{wh_id}_{ym}"
    if seed_key not in st.session_state:
        phy_map = st.session_state.get(phy_key) or {}
        st.session_state[seed_key] = pd.DataFrame([
            {
                "product_id": int(ln["product_id"]),
                "Code": ln.get("product_code"),
                "Product": ln.get("product_name"),
                "OS": float(ln.get("opening_qty") or 0),
                "Sale": float(ln.get("sold_qty") or 0),
                "Return": float(ln.get("return_qty") or 0),
                "Adj": float(ln.get("adj_qty") or 0),
                "Phy": float(
                    phy_map.get(int(ln["product_id"]), ln.get("physical_qty") or 0)
                ),
            }
            for ln in lines
        ])

    st.subheader("Worksheet — edit Phy only")
    edit_df = st.session_state[seed_key]
    disabled_cols = ["product_id", "Code", "Product", "OS", "Sale", "Return", "Adj"]
    if is_posted:
        disabled_cols.append("Phy")

    edited = st.data_editor(
        edit_df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=disabled_cols,
        column_config={
            "product_id": None,
            "Code": st.column_config.TextColumn("Code", width="small"),
            "Product": st.column_config.TextColumn("Product", width="large"),
            "OS": st.column_config.NumberColumn("OS", format="%.2f"),
            "Sale": st.column_config.NumberColumn("Sale", format="%.2f"),
            "Return": st.column_config.NumberColumn("Return", format="%.2f"),
            "Adj": st.column_config.NumberColumn("Adj", format="%.2f"),
            "Phy": st.column_config.NumberColumn(
                "Phy", min_value=0.0, step=1.0, format="%.2f"
            ),
        },
        key=editor_key,
    )

    out_lines = []
    phy_map = {}
    sum_os = sum_sale = sum_ret = sum_adj = sum_phy = sum_prod = sum_close = 0.0
    for _, row in edited.iterrows():
        pid = int(row["product_id"])
        os_ = _f(row["OS"])
        sale = _f(row["Sale"])
        ret = _f(row["Return"])
        adj = _f(row["Adj"])
        phy = _f(row["Phy"])
        prod, closing = db.production_qty_formula(os_, sale, ret, adj, phy)
        phy_map[pid] = phy
        item = id_to_item.get(pid) or {}
        out_lines.append({
            "product_id": pid,
            "product_code": row.get("Code") or item.get("code"),
            "product_name": row.get("Product") or item.get("name"),
            "opening_qty": os_,
            "sold_qty": sale,
            "return_qty": ret,
            "adj_qty": adj,
            "physical_qty": phy,
            "production_qty": prod,
            "closing_qty": closing,
        })
        sum_os += os_
        sum_sale += sale
        sum_ret += ret
        sum_adj += adj
        sum_phy += phy
        sum_prod += prod
        sum_close += closing

    st.session_state[phy_key] = phy_map
    # Keep seed in sync with Phy edits so remounts don't wipe typing
    try:
        seed = st.session_state[seed_key].copy()
        for i, ln in enumerate(out_lines):
            if i < len(seed):
                seed.at[seed.index[i], "Phy"] = ln["physical_qty"]
        st.session_state[seed_key] = seed
    except Exception:
        pass

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Items", len(out_lines))
    k2.metric("OS", f"{sum_os:,.2f}")
    k3.metric("Sale", f"{sum_sale:,.2f}")
    k4.metric("Phy", f"{sum_phy:,.2f}")
    k5.metric("Production", f"{sum_prod:,.2f}")
    k6.metric("Closing", f"{sum_close:,.2f}")

    result_df = pd.DataFrame([
        {
            "Code": ln["product_code"],
            "Product": ln["product_name"],
            "OS": ln["opening_qty"],
            "Sale": ln["sold_qty"],
            "Return": ln["return_qty"],
            "Adj": ln["adj_qty"],
            "Phy": ln["physical_qty"],
            "Production": ln["production_qty"],
            "Closing": ln["closing_qty"],
        }
        for ln in out_lines
    ])
    st.caption(
        "Computed — Production = Phy − OS − Return + Sale − Adj; Closing = Phy. "
        "Negative Production means Phy is below book movement (post blocked unless allowed)."
    )
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    from erp_ui.report_print import report_toolbar

    report_toolbar(
        result_df,
        "Production from Physical",
        f"prod_phy_{ym}",
        period=f"{fd} → {td}",
        filters={"warehouse": wh_lbl, "month": ym},
        summary={
            "items": len(out_lines),
            "production": round(sum_prod, 2),
            "physical": round(sum_phy, 2),
        },
        key_prefix=f"prod_phy_ex_{wh_id}_{ym}",
    )

    notes = st.text_input("Notes", key=f"prod_phy_notes_{wh_id}_{ym}")
    allow_neg = st.checkbox(
        "Allow negative production on post (stock out)",
        value=False,
        key=f"prod_phy_allow_neg_{wh_id}_{ym}",
        disabled=is_posted,
    )

    a1, a2, a3 = st.columns(3)
    if a1.button("Save draft", type="primary", disabled=is_posted, key="prod_phy_save"):
        try:
            rid = db.save_production_month_run(
                wh_id,
                ym,
                out_lines,
                notes=notes or None,
                user_id=_user_id(),
            )
            ff.action_done(f"Draft saved (run #{rid}).")
        except Exception as e:
            st.error(str(e))

    if a2.button("Post production", disabled=is_posted, key="prod_phy_post"):
        try:
            rid = db.save_production_month_run(
                wh_id,
                ym,
                out_lines,
                notes=notes or None,
                user_id=_user_id(),
            )
            result = db.post_production_month_run(
                rid,
                user_id=_user_id(),
                allow_negative=allow_neg,
            )
            mm = result.get("mismatches") or []
            msg = (
                f"Posted {result.get('posted_lines', 0)} line(s) · "
                f"qty {result.get('posted_production_qty', 0):,.2f} · "
                f"{result.get('batch_ref')}"
            )
            if mm:
                msg += f" · {len(mm)} stock vs Phy mismatch(es) — check warehouse stock."
            ff.action_done(msg)
        except Exception as e:
            st.error(str(e))

    if is_posted and saved and a3.button(
        "Admin unlock (draft again)",
        key="prod_phy_unlock",
    ):
        try:
            db.unlock_production_month_run(int(saved["id"]), user_id=_user_id())
            ff.action_done(
                "Unlocked to draft. Stock movements were NOT reversed — "
                "do not re-post without reversing manually."
            )
        except Exception as e:
            st.error(str(e))
