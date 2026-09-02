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


def _seed_draft(contractor_id: int):
    """Load remembered products into session draft if not already editing."""
    sk = _draft_key(contractor_id)
    if sk not in st.session_state:
        st.session_state[sk] = get_contractor_product_ids(contractor_id)


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
        "① Production quantity (monthly batches / qty × rate) — e.g. detergent powder plant. "
        "② SKU / product / cartons × rate. "
        "Assign products on the **Products** tab; selection is saved until you update or discard it."
    )
    rows = list_contractors(active_only=False)
    if rows:
        view = []
        for r in rows:
            view.append({
                "Code": r.get("supplier_code"),
                "Contractor": r.get("supplier_name"),
                "Payment type": PAYMENT_TYPES.get(r.get("payment_type"), r.get("payment_type")),
                "Default rate": float(r.get("default_rate") or 0),
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
        rate = st.number_input("Default rate", min_value=0.0, value=0.0, step=0.5, format="%.4f")
        notes = st.text_input("Notes (optional)")
        if st.form_submit_button("Save contractor", type="primary"):
            try:
                cid = add_contractor(
                    {
                        "supplier_id": sup_opts[sup_lbl],
                        "payment_type": type_by_label[type_lbl],
                        "default_rate": rate,
                        "notes": notes,
                    },
                    hlp.uid(),
                )
                st.session_state.pop(_draft_key(cid), None)
                ff.action_done(f"Contractor saved. Open **Products** to assign items for **{sup_lbl}**.")
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
            rate = st.number_input(
                "Default rate", min_value=0.0,
                value=float(cur.get("default_rate") or 0), step=0.5, format="%.4f",
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
                            "default_rate": rate,
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
                    ff.action_done("Contractor deleted.")
                except Exception as e:
                    st.error(str(e))


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
    saved_ids = set(get_contractor_product_ids(cid))
    draft_ids = [int(x) for x in (st.session_state.get(sk) or [])]

    st.caption(
        f"**{cur.get('supplier_name')}** · {PAYMENT_TYPES.get(cur.get('payment_type'))}. "
        "Tick products used for this contractor’s payment. "
        "**Update selection** saves permanently; **Discard changes** restores the last saved list; "
        "**Clear all products** removes the remembered assignment."
    )

    items = db.get_items(active_only=True)
    # Prefer finished / packaging-looking items first but show all
    id_to_label = {
        int(it["id"]): f"{it.get('code')} — {it.get('name')}"
        for it in items
    }
    labels = list(id_to_label.values())
    label_to_id = {v: k for k, v in id_to_label.items()}
    default_labels = [id_to_label[i] for i in draft_ids if i in id_to_label]

    dirty = set(draft_ids) != saved_ids
    if dirty:
        st.warning("Unsaved product changes — use **Update selection** to remember, or **Discard changes**.")

    chosen = st.multiselect(
        "Products for this contractor",
        labels,
        default=default_labels,
        key=f"cl_prod_ms_{cid}",
        help="Selection is remembered when you click Update selection.",
    )
    # Sync draft from widget
    new_ids = [label_to_id[lbl] for lbl in chosen if lbl in label_to_id]
    st.session_state[sk] = new_ids

    # Per-product rate overrides (optional)
    default_rate = float(cur.get("default_rate") or 0)
    saved_rates = {
        int(p["product_id"]): float(p["rate"] if p.get("rate") is not None else default_rate)
        for p in (cur.get("products") or [])
    }
    rate_map = {}
    if new_ids:
        st.markdown("**Rates** (blank uses contractor default)")
        for pid in new_ids:
            lbl = id_to_label.get(pid, str(pid))
            rate_map[pid] = st.number_input(
                lbl,
                min_value=0.0,
                value=float(saved_rates.get(pid, default_rate)),
                step=0.5,
                format="%.4f",
                key=f"cl_rate_{cid}_{pid}",
            )

    a1, a2, a3 = st.columns(3)
    if a1.button("Update selection", type="primary", key="cl_prod_save"):
        try:
            n = save_contractor_products(cid, new_ids, rates=rate_map, user_id=hlp.uid())
            st.session_state[sk] = list(new_ids)
            ff.action_done(f"Saved **{n}** product(s) for this contractor.")
        except Exception as e:
            st.error(str(e))
    if a2.button("Discard changes", key="cl_prod_discard"):
        st.session_state[sk] = list(saved_ids)
        # Force multiselect reset on next run
        st.session_state.pop(f"cl_prod_ms_{cid}", None)
        for pid in list(saved_ids) + new_ids:
            st.session_state.pop(f"cl_rate_{cid}_{pid}", None)
        ff.action_done("Draft discarded — restored last saved products.")
    if a3.button("Clear all products", key="cl_prod_clear"):
        try:
            clear_contractor_products(cid, user_id=hlp.uid())
            st.session_state[sk] = []
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
                "Rate": float(p["rate"] if p.get("rate") is not None else default_rate),
            }
            for p in cur["products"]
        ]))


def _tab_month_preview():
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
        st.caption("Quantities come from **completed** production orders for the assigned products.")
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
