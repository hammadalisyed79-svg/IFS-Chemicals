"""Contract labour — contractors, payment types, product assignment."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from application import data_gateway as db
from db_contractors import (
    BULK_PREFIX_HINTS,
    PAYMENT_PRODUCTION_QTY,
    PAYMENT_TYPES,
    add_contractor,
    calculate_contractor_month,
    clear_contractor_products,
    deactivate_contractor,
    delete_contractor,
    get_contractor,
    get_contractor_month_run,
    get_contractor_product_ids,
    get_contractor_product_rates,
    list_contractor_month_runs,
    list_contractors,
    month_bounds,
    product_ids_by_code_prefix,
    save_contractor_month_run,
    save_contractor_products,
    update_contractor,
)
from erp_ui import form_flow as ff
from erp_ui import helpers as hlp


def _draft_key(contractor_id: int) -> str:
    return f"cl_prod_draft_{int(contractor_id)}"


def _rates_key(contractor_id: int) -> str:
    return f"cl_prod_rates_{int(contractor_id)}"


def _seed_draft(contractor_id: int):
    """Load remembered products + rates into session draft if not already editing."""
    sk = _draft_key(contractor_id)
    rk = _rates_key(contractor_id)
    if sk not in st.session_state:
        st.session_state[sk] = get_contractor_product_ids(contractor_id)
    if rk not in st.session_state:
        st.session_state[rk] = get_contractor_product_rates(contractor_id)


def _merge_ids(existing: list[int], extra: list[int]) -> list[int]:
    seen = set()
    out = []
    for pid in list(existing or []) + list(extra or []):
        try:
            i = int(pid)
        except (TypeError, ValueError):
            continue
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def page_contract_labour():
    peek = st.session_state.get("cl_page_tab") or "Contractors"
    hlp.std_page_header(
        "Contract Labour",
        subtitle="Payment types · Product assignment · Monthly worksheet",
        status="register" if peek == "Contractors" else None,
        status_kind="shell",
    )
    tab = hlp.sticky_page_tabs(
        ["Contractors", "Products", "Monthly Worksheet"],
        "cl_page_tab",
    )

    if tab == "Contractors":
        _tab_contractors()
    elif tab == "Products":
        _tab_products()
    else:
        _tab_month_preview()


def _tab_contractors():
    st.caption(
        "**Two payment types:** "
        "① Production quantity — completed production qty × **rate per SKU** "
        "(each product has its own rate). "
        "② SKU / cartons × **rate per SKU**. "
        "Assign products and set rates on the **Products** tab (bulk add by code, e.g. DW, DT1, DT2, DT3)."
    )
    rows = list_contractors(active_only=False)
    if rows:
        view = []
        for r in rows:
            view.append({
                "Code": r.get("supplier_code"),
                "Contractor": r.get("supplier_name"),
                "Payment type": PAYMENT_TYPES.get(r.get("payment_type"), r.get("payment_type")),
                "Products": int(r.get("product_count") or 0),
                "Active": "Yes" if r.get("is_active") else "No",
            })
        hlp.render_dataframe_html_table(pd.DataFrame(view))
    else:
        st.info("No contract labourers yet. Add one below (pick an existing supplier).")

    st.subheader("Add contractor")
    suppliers = db.get_suppliers(active_only=True)
    already = {int(r["supplier_id"]) for r in rows}
    avail = [s for s in suppliers if int(s["id"]) not in already]
    if not avail:
        st.warning("All active suppliers are already set up, or add a supplier under Masters first.")
    else:
        # Outside st.form — sticky tab buttons + forms can miss submits in Streamlit.
        type_keys = list(PAYMENT_TYPES.keys())
        sup_opts = {f"{s['code']} — {s['name']}": int(s["id"]) for s in avail}
        c1, c2 = st.columns(2)
        with c1:
            sup_lbl = st.selectbox(
                "Contractor (supplier)",
                list(sup_opts.keys()),
                key="cl_add_sup",
            )
        with c2:
            type_key = st.selectbox(
                "Payment type",
                type_keys,
                format_func=lambda k: PAYMENT_TYPES.get(k, k),
                key="cl_add_type",
            )
        notes = st.text_input("Notes (optional)", key="cl_add_notes")
        st.caption("Rates are set **per SKU** on the Products tab — not a single fixed rate.")
        if st.button("Save contractor", type="primary", key="cl_add_save"):
            try:
                sid = int(sup_opts[sup_lbl])
                cid = add_contractor(
                    {
                        "supplier_id": sid,
                        "payment_type": type_key,
                        "default_rate": 0,
                        "notes": notes,
                    },
                    hlp.uid(),
                )
                saved = get_contractor(cid)
                if not saved:
                    raise RuntimeError("Save did not persist — please try again.")
                st.session_state.pop(_draft_key(cid), None)
                st.session_state.pop(_rates_key(cid), None)
                st.session_state.pop("cl_add_notes", None)
                ff.action_done(
                    f"Contractor **{saved.get('supplier_code')} — {saved.get('supplier_name')}** saved. "
                    "Open the **Products** tab to assign SKUs and rates."
                )
            except Exception as e:
                st.error(f"Could not save contractor: {e}")

    if rows:
        st.subheader("Edit / delete")
        pick = {
            f"{r['supplier_code']} — {r['supplier_name']}": int(r["id"]) for r in rows
        }
        sel = st.selectbox("Contractor", list(pick.keys()), key="cl_edit_pick")
        cid = pick[sel]
        cur = get_contractor(cid)
        if not cur:
            return
        type_keys = list(PAYMENT_TYPES.keys())
        cur_type = cur.get("payment_type") if cur.get("payment_type") in type_keys else type_keys[0]
        type_key = st.selectbox(
            "Payment type",
            type_keys,
            index=type_keys.index(cur_type),
            format_func=lambda k: PAYMENT_TYPES.get(k, k),
            key=f"cl_edit_type_{cid}",
        )
        notes = st.text_input("Notes", value=cur.get("notes") or "", key=f"cl_edit_notes_{cid}")
        active = st.checkbox("Active", value=bool(cur.get("is_active", 1)), key=f"cl_edit_active_{cid}")
        if st.button("Save changes", type="primary", key=f"cl_edit_save_{cid}"):
            try:
                update_contractor(
                    cid,
                    {
                        "payment_type": type_key,
                        "default_rate": float(cur.get("default_rate") or 0),
                        "notes": notes,
                        "is_active": int(active),
                    },
                    hlp.uid(),
                )
                msg = "Contractor updated."
                if not active:
                    msg += " Marked **inactive** (products/rates kept)."
                ff.action_done(msg)
            except Exception as e:
                st.error(f"Could not update: {e}")

        with st.expander("Danger zone — permanent delete"):
            st.caption(
                "Do **not** use this for normal edits. Permanent delete removes the contractor "
                "and all product rates / month worksheets. Prefer unchecking **Active** above."
            )
            typed = st.text_input(
                f"Type supplier code **{cur.get('supplier_code')}** to confirm delete",
                key=f"cl_edit_del_type_{cid}",
            )
            can_del = (typed or "").strip().upper() == str(cur.get("supplier_code") or "").strip().upper()
            if st.button(
                "Delete permanently",
                key=f"cl_edit_del_{cid}",
                disabled=not can_del,
                type="secondary",
            ):
                try:
                    delete_contractor(cid, user_id=hlp.uid())
                    st.session_state.pop(_draft_key(cid), None)
                    st.session_state.pop(_rates_key(cid), None)
                    st.session_state.pop(f"cl_edit_del_type_{cid}", None)
                    ff.action_done("Contractor permanently deleted.")
                except Exception as e:
                    st.error(f"Could not delete: {e}")


def _tab_products():
    rows = list_contractors(active_only=True)
    if not rows:
        st.info("Add a contractor on the **Contractors** tab first.")
        return

    pick = {
        f"{r['supplier_code']} — {r['supplier_name']} "
        f"[{PAYMENT_TYPES.get(r['payment_type'], r['payment_type'])}]": int(r["id"])
        for r in rows
    }
    sel = st.selectbox("Contractor", list(pick.keys()), key="cl_prod_pick")
    cid = pick[sel]
    cur = get_contractor(cid)
    if not cur:
        st.warning("Contractor not found.")
        return

    _seed_draft(cid)
    sk = _draft_key(cid)
    rk = _rates_key(cid)
    saved_ids = set(get_contractor_product_ids(cid))
    draft_ids = [int(x) for x in (st.session_state.get(sk) or [])]
    rate_draft = dict(st.session_state.get(rk) or {})

    is_prod_qty = (cur.get("payment_type") or "") == PAYMENT_PRODUCTION_QTY
    st.caption(
        f"**{cur.get('supplier_name')}** · {PAYMENT_TYPES.get(cur.get('payment_type'))}. "
        + (
            "Payment = **production qty × rate for each SKU** (rates differ by product). "
            if is_prod_qty else
            "Payment = **SKU / carton qty × rate for each SKU**. "
        )
        + "Use **bulk add** for families like **DW**, **DT1**, **DT2**, **DT3**. "
        "Then set each SKU’s rate and click **Update selection**."
    )

    # --- Bulk add by code prefix ---
    st.markdown("**Bulk add SKUs**")
    prefix_key = f"cl_bulk_prefix_{cid}"
    if prefix_key not in st.session_state:
        st.session_state[prefix_key] = "DW"

    b1, b2, b3, b4 = st.columns([1.4, 0.7, 1.2, 1.8])
    b1.text_input(
        "Code prefix",
        key=prefix_key,
        help="Type any prefix (DW, DT1, DT4, DTT, …) then click Find / Add. "
             "Already-selected SKUs are skipped (no duplicates).",
    )
    find_clicked = b2.button("Find", key=f"cl_bulk_find_{cid}")
    prefix = str(st.session_state.get(prefix_key) or "").strip().upper()
    matched = product_ids_by_code_prefix(prefix) if prefix else []
    already = set(int(x) for x in (st.session_state.get(sk) or draft_ids or []))
    new_matches = [r for r in matched if int(r["id"]) not in already]
    b3.metric("Matches / new", f"{len(matched)} / {len(new_matches)}")
    add_label = (
        f"Add new {prefix or '…'}* ({len(new_matches)})"
        if prefix else "Add new …* (0)"
    )
    if b4.button(
        add_label,
        type="primary",
        key=f"cl_bulk_add_{cid}",
        disabled=not new_matches,
    ):
        add_ids = [int(r["id"]) for r in new_matches]
        skipped = len(matched) - len(add_ids)
        draft_ids = _merge_ids(st.session_state.get(sk) or draft_ids, add_ids)
        st.session_state[sk] = draft_ids
        st.session_state.pop(f"cl_prod_ms_{cid}", None)
        msg = f"Added **{len(add_ids)}** new SKU(s) with prefix **{prefix}***."
        if skipped:
            msg += f" Skipped **{skipped}** already in the list (no duplicates)."
        ff.action_done(msg)

    if find_clicked:
        if not prefix:
            st.warning("Enter a code prefix first.")
        elif not matched:
            st.warning(f"No active products found for prefix **{prefix}***.")
        else:
            st.info(
                f"**{prefix}*** → {len(matched)} product(s), "
                f"**{len(new_matches)}** not yet in your selection."
            )

    # Shortcut chips (wrap in rows of 4)
    hints = list(BULK_PREFIX_HINTS)
    for row_start in range(0, len(hints), 4):
        row = hints[row_start:row_start + 4]
        hint_cols = st.columns(4)
        for i, (pref, label) in enumerate(row):
            n = len(product_ids_by_code_prefix(pref))
            if hint_cols[i].button(
                f"{label} · {n}",
                key=f"cl_hint_{cid}_{pref}",
                disabled=n == 0,
            ):
                st.session_state[prefix_key] = pref
                matched_h = product_ids_by_code_prefix(pref)
                already_h = set(int(x) for x in (st.session_state.get(sk) or draft_ids or []))
                add_ids = [int(r["id"]) for r in matched_h if int(r["id"]) not in already_h]
                skipped = len(matched_h) - len(add_ids)
                draft_ids = _merge_ids(st.session_state.get(sk) or draft_ids, add_ids)
                st.session_state[sk] = draft_ids
                st.session_state.pop(f"cl_prod_ms_{cid}", None)
                msg = f"Added **{len(add_ids)}** · {label}."
                if skipped:
                    msg += f" Skipped **{skipped}** duplicates."
                if not add_ids and matched_h:
                    msg = f"All **{len(matched_h)}** {label} SKUs are already in the list."
                ff.action_done(msg)

    draft_ids = _merge_ids([], [int(x) for x in (st.session_state.get(sk) or [])])
    st.session_state[sk] = draft_ids

    items = db.get_items(active_only=True)
    id_to_label = {
        int(it["id"]): f"{it.get('code')} — {it.get('name')}"
        for it in items
    }
    id_to_code = {int(it["id"]): str(it.get("code") or "") for it in items}
    labels = list(id_to_label.values())
    label_to_id = {v: k for k, v in id_to_label.items()}
    default_labels = [id_to_label[i] for i in draft_ids if i in id_to_label]

    dirty = set(draft_ids) != saved_ids
    saved_rates = get_contractor_product_rates(cid)
    if any(
        abs(float(rate_draft.get(pid, saved_rates.get(pid, 0)) or 0)
            - float(saved_rates.get(pid, 0) or 0)) > 1e-9
        for pid in draft_ids if pid in saved_ids
    ):
        dirty = True
    if dirty:
        st.warning(
            "Unsaved changes — **Update selection** to save, "
            "**Reset selection** to restore saved, or **Clear selection** to empty picks."
        )

    chosen = st.multiselect(
        "Products for this contractor (search / pick individually)",
        labels,
        default=default_labels,
        key=f"cl_prod_ms_{cid}",
        help="Or use Bulk add above for whole families (DW*, DP*, …).",
    )
    new_ids = [label_to_id[lbl] for lbl in chosen if lbl in label_to_id]
    # Keep stable order: previous draft order first, then new picks
    new_ids = _merge_ids([i for i in draft_ids if i in set(new_ids)], new_ids)
    st.session_state[sk] = new_ids

    rate_map = {}
    if new_ids:
        st.markdown(
            f"**Rate per SKU** ({len(new_ids)} selected) — "
            + ("used with **production quantity**" if is_prod_qty else "used with SKU / carton qty")
        )
        # Compact editable list
        for pid in new_ids:
            code = id_to_code.get(pid, "")
            name = id_to_label.get(pid, str(pid))
            prev = float(
                rate_draft.get(pid, saved_rates.get(pid, 0)) or 0
            )
            c_a, c_b = st.columns([3, 1])
            c_a.markdown(f"`{code}` · {name.split(' — ', 1)[-1] if ' — ' in name else name}")
            rate_map[pid] = c_b.number_input(
                "Rate",
                min_value=0.0,
                value=prev,
                step=0.5,
                format="%.4f",
                key=f"cl_rate_{cid}_{pid}",
                label_visibility="collapsed",
            )
        st.session_state[rk] = {int(k): float(v) for k, v in rate_map.items()}
    else:
        st.info("No products selected yet. Bulk-add **DW*** for Dish Wash, or search above.")

    a1, a2, a3, a4 = st.columns(4)
    if a1.button("Update selection", type="primary", key="cl_prod_save"):
        try:
            n = save_contractor_products(cid, new_ids, rates=rate_map, user_id=hlp.uid())
            st.session_state[sk] = list(new_ids)
            st.session_state[rk] = dict(rate_map)
            ff.action_done(f"Saved **{n}** SKU(s) with individual rates.")
        except Exception as e:
            st.error(str(e))
    if a2.button("Reset selection", key="cl_prod_reset", help="Restore last saved products and rates"):
        for pid in list(saved_ids) + new_ids:
            st.session_state.pop(f"cl_rate_{cid}_{pid}", None)
        st.session_state[sk] = list(saved_ids)
        st.session_state[rk] = get_contractor_product_rates(cid)
        st.session_state.pop(f"cl_prod_ms_{cid}", None)
        ff.action_done("Selection reset — restored last saved products and rates.")
    if a3.button("Clear selection", key="cl_prod_clear_sel", help="Empty current picks (not saved until Update)"):
        for pid in new_ids:
            st.session_state.pop(f"cl_rate_{cid}_{pid}", None)
        st.session_state[sk] = []
        st.session_state[rk] = {}
        st.session_state.pop(f"cl_prod_ms_{cid}", None)
        ff.action_done(
            "Selection cleared. Click **Update selection** to save empty, "
            "or **Reset selection** to bring back the last saved list."
        )
    if a4.button("Clear all (saved)", key="cl_prod_clear", help="Permanently remove all saved products for this contractor"):
        try:
            clear_contractor_products(cid, user_id=hlp.uid())
            for pid in list(saved_ids) + new_ids:
                st.session_state.pop(f"cl_rate_{cid}_{pid}", None)
            st.session_state[sk] = []
            st.session_state[rk] = {}
            st.session_state.pop(f"cl_prod_ms_{cid}", None)
            ff.action_done("All saved products removed for this contractor.")
        except Exception as e:
            st.error(str(e))

    if cur.get("products"):
        st.markdown("**Currently saved**")
        hlp.render_dataframe_html_table(pd.DataFrame([
            {
                "Code": p.get("product_code"),
                "Product": p.get("product_name"),
                "Rate / unit": float(p["rate"] if p.get("rate") is not None else 0),
            }
            for p in cur["products"]
        ]))


def _tab_month_preview():
    from html import escape
    import calendar

    rows = list_contractors(active_only=True)
    if not rows:
        st.info("Add a contractor and assign products first.")
        return

    pick = {
        f"{r['supplier_code']} — {r['supplier_name']}": int(r["id"]) for r in rows
    }
    today = date.today()
    c1, c2, c3 = st.columns([2, 1, 1])
    sel = c1.selectbox("Contractor", list(pick.keys()), key="cl_prev_pick")
    year = c2.number_input(
        "Year", min_value=2020, max_value=2035, value=today.year, step=1, key="cl_prev_year",
    )
    month = c3.selectbox(
        "Month",
        list(range(1, 13)),
        index=today.month - 1,
        format_func=lambda m: f"{m:02d} — {calendar.month_name[m]}",
        key="cl_prev_month",
    )
    cid = pick[sel]
    fd, td = month_bounds(int(year), int(month))
    ym = f"{int(year):04d}-{int(month):02d}"

    st.caption(
        "**Monthly worksheet only** (full calendar month). "
        "**Closing (billable)** = Sold - Opening - Sale return + Physical Manual · "
        "**Amount** = Closing x Rate. Save stores one record per contractor per month."
    )

    saved = get_contractor_month_run(cid, ym)
    mk = f"cl_manual_{cid}_{ym}"
    if mk not in st.session_state and saved:
        st.session_state[mk] = {
            int(ln["product_id"]): float(ln.get("manual_qty") or 0)
            for ln in (saved.get("lines") or [])
        }

    b1, b2 = st.columns([1, 1])
    if b1.button("Load / refresh month", type="primary", key="cl_prev_go"):
        try:
            prior = st.session_state.get(mk) or {}
            if not prior and saved:
                prior = {
                    int(ln["product_id"]): float(ln.get("manual_qty") or 0)
                    for ln in (saved.get("lines") or [])
                }
            result = calculate_contractor_month(
                cid, fd, td, manual_qty=prior,
            )
            st.session_state["cl_prev_result"] = result
            st.session_state["cl_prev_meta"] = (cid, ym)
        except Exception as e:
            st.error(str(e))
            return

    if saved:
        b2.info(
            f"Saved record for **{ym}**: Gross Rs. {float(saved.get('gross_amount') or 0):,.2f}"
            + (
                f" · updated {saved.get('modified_at') or saved.get('created_at')}"
                if saved.get("modified_at") or saved.get("created_at") else ""
            )
        )
    else:
        b2.caption("No saved record for this month yet.")

    result = st.session_state.get("cl_prev_result")
    meta = st.session_state.get("cl_prev_meta")
    if not result or not meta or meta[0] != cid:
        st.info(
            "Choose **Year / Month**, then **Load / refresh month**. "
            "Enter Physical Manual where needed, then **Save month record**."
        )
        hist = list_contractor_month_runs(cid, limit=12)
        if hist:
            st.markdown("**Recent saved months**")
            hlp.render_dataframe_html_table(pd.DataFrame([
                {
                    "Month": h.get("year_month"),
                    "Closing Qty": round(float(h.get("closing_qty") or 0), 2),
                    "Gross": round(float(h.get("gross_amount") or 0), 2),
                    "Saved": h.get("modified_at") or h.get("created_at"),
                }
                for h in hist
            ]))
        return

    if meta[1] != ym:
        st.warning("Month changed — click **Load / refresh month** to recalculate.")

    c = result["contractor"]
    lines = result.get("lines") or []
    if not lines:
        st.info("No products assigned — set them on the **Products** tab.")
        return

    st.markdown(
        f"### {escape(str(c.get('supplier_name') or ''))}  \n"
        f"<span style='color:#64748b;font-size:0.9rem'>"
        f"{escape(str(result.get('payment_type_label') or ''))} · "
        f"**{ym}** ({escape(fd)} → {escape(td)})"
        f"</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "**Worksheet** — edit **Physical Manual Added Stock** only; "
        "Closing and Amount update below."
    )

    prior_manual = st.session_state.get(mk) or {
        int(ln["product_id"]): float(ln.get("manual_qty") or 0) for ln in lines
    }
    edit_df = pd.DataFrame([
        {
            "product_id": int(ln["product_id"]),
            "Code": ln.get("product_code"),
            "Product": ln.get("product_name"),
            "Sold Qty": float(ln.get("sold_qty") or 0),
            "Stock in hand": float(ln.get("stock_qty") or 0),
            "Sale return": float(ln.get("sale_return_qty") or 0),
            "Physical Manual": float(
                prior_manual.get(int(ln["product_id"]), ln.get("manual_qty") or 0)
            ),
            "Rate": float(ln.get("rate") or 0),
        }
        for ln in lines
    ])

    edited = st.data_editor(
        edit_df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        disabled=[
            "product_id", "Code", "Product", "Sold Qty",
            "Stock in hand", "Sale return", "Rate",
        ],
        column_config={
            "product_id": None,
            "Code": st.column_config.TextColumn("Code", width="small"),
            "Product": st.column_config.TextColumn("Product", width="large"),
            "Sold Qty": st.column_config.NumberColumn(
                "Sold Qty", format="%.2f",
                help="Quantity sold in this month",
            ),
            "Stock in hand": st.column_config.NumberColumn(
                "Stock in hand", format="%.2f",
                help="Opening quantity as of month start",
            ),
            "Sale return": st.column_config.NumberColumn(
                "Sale return", format="%.2f",
                help="Sale return quantity in this month",
            ),
            "Physical Manual": st.column_config.NumberColumn(
                "Physical Manual Added Stock",
                min_value=0.0, step=1.0, format="%.2f",
                help="Add physical/manual stock; included in Closing (billable)",
            ),
            "Rate": st.column_config.NumberColumn("Rate", format="%.4f"),
        },
        key=f"cl_ws_editor_{cid}_{ym}",
    )

    def _f(v):
        try:
            x = float(v)
            if x != x:  # NaN
                return 0.0
            return x
        except (TypeError, ValueError):
            return 0.0

    manual_map = {}
    display_rows = []
    save_lines = []
    gross = 0.0
    sum_sold = sum_stock = sum_ret = sum_man = sum_close = 0.0
    for _, row in edited.iterrows():
        pid = int(row["product_id"])
        sold = _f(row["Sold Qty"])
        stock = _f(row["Stock in hand"])
        ret = _f(row["Sale return"])
        man = _f(row["Physical Manual"])
        rate = _f(row["Rate"])
        closing = round(sold - stock - ret + man, 4)
        amount = round(closing * rate, 2)
        manual_map[pid] = man
        sum_sold += sold
        sum_stock += stock
        sum_ret += ret
        sum_man += man
        sum_close += closing
        gross += amount
        display_rows.append({
            "Code": row["Code"],
            "Product": row["Product"],
            "Sold Qty": sold,
            "Stock in hand": stock,
            "Sale return": ret,
            "Physical Manual": man,
            "Closing Stock": closing,
            "Rate": rate,
            "Amount": amount,
        })
        save_lines.append({
            "product_id": pid,
            "product_code": row["Code"],
            "product_name": row["Product"],
            "sold_qty": sold,
            "stock_qty": stock,
            "sale_return_qty": ret,
            "manual_qty": man,
            "closing_stock": closing,
            "rate": rate,
            "amount": amount,
        })
    st.session_state[mk] = manual_map

    k1, k2, k3, k4, k5 = st.columns(5, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Items</p>"
        f"<p class='txn-kpi-val'>{len(display_rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Sold Qty</p>"
        f"<p class='txn-kpi-val'>{sum_sold:,.2f}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Opening</p>"
        f"<p class='txn-kpi-val'>{sum_stock:,.2f}</p></div>",
        unsafe_allow_html=True,
    )
    k4.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Closing (billable)</p>"
        f"<p class='txn-kpi-val'>{sum_close:,.2f}</p></div>",
        unsafe_allow_html=True,
    )
    k5.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Gross Amount</p>"
        f"<p class='txn-kpi-val'>Rs. {gross:,.2f}</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "**Computed amounts** — Closing (billable) = Sold - Opening - Sale return + Physical Manual · "
        "Amount = Closing x Rate"
    )
    out_df = pd.DataFrame(display_rows)
    footer = {
        "Code": "",
        "Product": "GROSS TOTAL",
        "Sold Qty": round(sum_sold, 2),
        "Stock in hand": round(sum_stock, 2),
        "Sale return": round(sum_ret, 2),
        "Physical Manual": round(sum_man, 2),
        "Closing Stock": round(sum_close, 2),
        "Rate": "",
        "Amount": round(gross, 2),
    }
    show = pd.concat([out_df, pd.DataFrame([footer])], ignore_index=True)
    hlp.render_dataframe_html_table(show)

    st.markdown(
        f"<div style='text-align:right;margin-top:8px;padding:12px 16px;"
        f"background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px'>"
        f"<div style='font-size:0.75rem;text-transform:uppercase;letter-spacing:0.04em;color:#64748b'>"
        f"Gross amount ({len(display_rows)} items) · {ym}</div>"
        f"<div style='font-size:1.45rem;font-weight:700;color:#0f172a'>Rs. {gross:,.2f}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    notes = st.text_input("Save notes (optional)", key=f"cl_month_notes_{cid}_{ym}")
    if st.button("Save month record", type="primary", key=f"cl_month_save_{cid}_{ym}"):
        try:
            run_id = save_contractor_month_run(
                cid, ym, save_lines, notes=notes, user_id=hlp.uid(),
            )
            ff.action_done(
                f"Month **{ym}** saved (record #{run_id}). "
                f"Gross Rs. {gross:,.2f} · Closing qty {sum_close:,.2f}."
            )
        except Exception as e:
            st.error(f"Could not save: {e}")

    from erp_ui.report_print import report_toolbar
    title = f"Contract Labour — {c.get('supplier_name')} — {ym}"
    report_toolbar(
        out_df, title, "contract_labour_month",
        period=f"{fd} to {td}",
        summary={
            "Month": ym,
            "Items": len(display_rows),
            "Sold Qty": round(sum_sold, 2),
            "Opening": round(sum_stock, 2),
            "Sale return": round(sum_ret, 2),
            "Closing Stock": round(sum_close, 2),
            "Gross Amount": round(gross, 2),
        },
        key_prefix="cl_month",
        layout="landscape",
    )
