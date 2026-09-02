"""Contract labour — contractors, payment types, product assignment."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from application import data_gateway as db
from db_contractors import (
    PAYMENT_TYPES,
    add_contractor,
    calculate_contractor_month,
    clear_contractor_products,
    delete_contractor,
    get_contractor,
    get_contractor_product_ids,
    list_contractors,
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
        subtitle="Payment types · Product assignment · Monthly preview",
        status="register" if peek == "Contractors" else None,
        status_kind="shell",
    )
    tab = hlp.sticky_page_tabs(
        ["Contractors", "Products", "Month Preview"],
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
        "Assign products and set rates on the **Products** tab (bulk add by code, e.g. DW = Dish Wash)."
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
        return

    sup_opts = {f"{s['code']} — {s['name']}": int(s["id"]) for s in avail}
    type_labels = list(PAYMENT_TYPES.values())
    type_by_label = {v: k for k, v in PAYMENT_TYPES.items()}

    with st.form("cl_add"):
        c1, c2 = st.columns(2)
        sup_lbl = c1.selectbox("Contractor (supplier)", list(sup_opts.keys()))
        type_lbl = c2.selectbox("Payment type", type_labels)
        notes = st.text_input("Notes (optional)")
        st.caption("Rates are set **per SKU** on the Products tab — not a single fixed rate.")
        if st.form_submit_button("Save contractor", type="primary"):
            try:
                cid = add_contractor(
                    {
                        "supplier_id": sup_opts[sup_lbl],
                        "payment_type": type_by_label[type_lbl],
                        "default_rate": 0,
                        "notes": notes,
                    },
                    hlp.uid(),
                )
                st.session_state.pop(_draft_key(cid), None)
                st.session_state.pop(_rates_key(cid), None)
                ff.action_done(f"Contractor saved. Open **Products** to assign SKUs and rates for **{sup_lbl}**.")
            except Exception as e:
                st.error(str(e))

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
        with st.form("cl_edit"):
            type_lbl = st.selectbox(
                "Payment type",
                type_labels,
                index=type_labels.index(PAYMENT_TYPES.get(cur["payment_type"], type_labels[0]))
                if PAYMENT_TYPES.get(cur["payment_type"]) in type_labels else 0,
            )
            notes = st.text_input("Notes", value=cur.get("notes") or "")
            active = st.checkbox("Active", value=bool(cur.get("is_active", 1)))
            b1, b2 = st.columns(2)
            save = b1.form_submit_button("Update", type="primary")
            delete = b2.form_submit_button("Delete")
            if save:
                try:
                    update_contractor(
                        cid,
                        {
                            "payment_type": type_by_label[type_lbl],
                            "default_rate": float(cur.get("default_rate") or 0),
                            "notes": notes,
                            "is_active": int(active),
                        },
                        hlp.uid(),
                    )
                    ff.action_done("Contractor updated.")
                except Exception as e:
                    st.error(str(e))
            if delete:
                try:
                    delete_contractor(cid)
                    st.session_state.pop(_draft_key(cid), None)
                    st.session_state.pop(_rates_key(cid), None)
                    ff.action_done("Contractor deleted.")
                except Exception as e:
                    st.error(str(e))


def _tab_products():
    from db_contractors import (
        BULK_PREFIX_HINTS,
        PAYMENT_PRODUCTION_QTY,
        get_contractor_product_rates,
        product_ids_by_code_prefix,
    )

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
        + "Use **bulk add** for families like **DW = Dish Wash**. "
        "Then set each SKU’s rate and click **Update selection**."
    )

    # --- Bulk add by code prefix ---
    st.markdown("**Bulk add SKUs**")
    b1, b2, b3 = st.columns([1.2, 1.5, 2])
    prefix = b1.text_input(
        "Code prefix",
        value="DW",
        key=f"cl_bulk_prefix_{cid}",
        help="e.g. DW for all Dish Wash products",
    ).strip().upper()
    matched = product_ids_by_code_prefix(prefix) if prefix else []
    b2.metric("Matching SKUs", len(matched))
    if b3.button(
        f"Add all {prefix or '…'}* ({len(matched)})",
        type="primary",
        key=f"cl_bulk_add_{cid}",
        disabled=not matched,
    ):
        add_ids = [int(r["id"]) for r in matched]
        draft_ids = _merge_ids(draft_ids, add_ids)
        st.session_state[sk] = draft_ids
        st.session_state.pop(f"cl_prod_ms_{cid}", None)
        ff.action_done(f"Added **{len(add_ids)}** SKU(s) with prefix **{prefix}*** — set rates below.")

    hint_cols = st.columns(len(BULK_PREFIX_HINTS))
    for i, (pref, label) in enumerate(BULK_PREFIX_HINTS):
        n = len(product_ids_by_code_prefix(pref))
        if hint_cols[i].button(f"{label} · {n}", key=f"cl_hint_{cid}_{pref}", disabled=n == 0):
            add_ids = [int(r["id"]) for r in product_ids_by_code_prefix(pref)]
            draft_ids = _merge_ids(st.session_state.get(sk) or [], add_ids)
            st.session_state[sk] = draft_ids
            st.session_state.pop(f"cl_prod_ms_{cid}", None)
            ff.action_done(f"Added **{len(add_ids)}** · {label}")

    draft_ids = [int(x) for x in (st.session_state.get(sk) or [])]

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
        st.warning("Unsaved changes — **Update selection** to save, or **Discard changes**.")

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

    a1, a2, a3 = st.columns(3)
    if a1.button("Update selection", type="primary", key="cl_prod_save"):
        try:
            n = save_contractor_products(cid, new_ids, rates=rate_map, user_id=hlp.uid())
            st.session_state[sk] = list(new_ids)
            st.session_state[rk] = dict(rate_map)
            ff.action_done(f"Saved **{n}** SKU(s) with individual rates.")
        except Exception as e:
            st.error(str(e))
    if a2.button("Discard changes", key="cl_prod_discard"):
        st.session_state[sk] = list(saved_ids)
        st.session_state[rk] = get_contractor_product_rates(cid)
        st.session_state.pop(f"cl_prod_ms_{cid}", None)
        for pid in list(saved_ids) + new_ids:
            st.session_state.pop(f"cl_rate_{cid}_{pid}", None)
        ff.action_done("Draft discarded — restored last saved products and rates.")
    if a3.button("Clear all products", key="cl_prod_clear"):
        try:
            clear_contractor_products(cid, user_id=hlp.uid())
            st.session_state[sk] = []
            st.session_state[rk] = {}
            st.session_state.pop(f"cl_prod_ms_{cid}", None)
            ff.action_done("All products removed for this contractor.")
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
    from db_contractors import PAYMENT_PRODUCTION_QTY

    rows = list_contractors(active_only=True)
    if not rows:
        st.info("Add a contractor and assign products first.")
        return

    pick = {
        f"{r['supplier_code']} — {r['supplier_name']}": int(r["id"]) for r in rows
    }
    c1, c2, c3 = st.columns([2, 1, 1])
    sel = c1.selectbox("Contractor", list(pick.keys()), key="cl_prev_pick")
    today = date.today()
    month_start = today.replace(day=1)
    fd = c2.date_input("From", value=month_start, key="cl_prev_fd")
    td = c3.date_input("To", value=today, key="cl_prev_td")
    if fd > td:
        st.error("From must be on or before To.")
        return

    if st.button("Calculate", type="primary", key="cl_prev_go"):
        try:
            result = calculate_contractor_month(pick[sel], str(fd), str(td))
            st.session_state["cl_prev_result"] = result
        except Exception as e:
            st.error(str(e))
            return

    result = st.session_state.get("cl_prev_result")
    if not result:
        st.caption(
            "Quantities come from **completed** production orders for assigned products. "
            "Each line uses that SKU’s own rate."
        )
        return

    c = result["contractor"]
    st.markdown(
        f"**{c.get('supplier_name')}** · {result.get('payment_type_label')} · "
        f"{result['from_date']} → {result['to_date']}"
    )
    k1, k2 = st.columns(2)
    k1.metric("Lines", len(result.get("lines") or []))
    k2.metric("Total", f"Rs. {float(result.get('total') or 0):,.2f}")

    lines = result.get("lines") or []
    if lines:
        df = pd.DataFrame([
            {
                "Code": ln.get("product_code"),
                "Product": ln.get("product_name"),
                "Batches": ln.get("batch_count"),
                "Qty": float(ln.get("quantity") or 0),
                "Rate": float(ln.get("rate") or 0),
                "Amount": float(ln.get("amount") or 0),
            }
            for ln in lines
        ])
        hlp.render_dataframe_html_table(df)
        from erp_ui.report_print import report_toolbar
        title = f"Contract Labour — {c.get('supplier_name')} ({result['from_date']} to {result['to_date']})"
        report_toolbar(
            df, title, "contract_labour_month",
            period=f"{result['from_date']} to {result['to_date']}",
            summary={"Total": float(result.get("total") or 0)},
            key_prefix="cl_month",
            layout="portrait",
        )
    else:
        st.info("No products assigned — set them on the **Products** tab.")