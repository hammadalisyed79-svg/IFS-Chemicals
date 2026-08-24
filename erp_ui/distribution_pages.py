"""Sales → Distribution — per-customer portal catalogues from invoices."""

from __future__ import annotations

from datetime import date

import streamlit as st
import pandas as pd

from application import data_gateway as db
from application.data_gateway import user_can
from erp_core import distributor_catalog as dcat
from erp_ui import form_flow as ff
from erp_ui import helpers as hlp


def page_distribution():
    user = st.session_state.get("user") or {}
    if (
        not user_can(user, "Portal", "view")
        and not user_can(user, "Sales", "view")
        and not user_can(user, "PriceLists", "view")
        and user.get("role") != "admin"
    ):
        st.error("Access denied.")
        return

    hlp.std_page_header("Distribution", status="register", status_kind="shell")
    st.caption(
        "Auto-build each distributor’s product list from approved invoices "
        f"(default from {dcat.DEFAULT_CUTOFF}). Admin can add products and change prices."
    )

    dcat.ensure_schema()
    customers = dcat.list_distributor_customers(active_only=True)
    if not customers:
        st.info("No distributor / portal-enabled customers yet. Enable portal under Distributor Orders.")
        return

    cmap = {f"{c['code']} — {c['name']} ({c.get('catalog_count') or 0} items)": c for c in customers}
    cust_labels, blank = hlp.options_with_blank(cmap.keys())
    label = st.selectbox("Distributor customer", cust_labels, key="dist_cat_cust")
    if not hlp.require_selected("distributor customer", label, blank, soft=True):
        return
    cust = cmap[label]
    cid = int(cust["id"])

    tab = hlp.sticky_page_tabs(
        ["Product List", "Rebuild from invoices", "Add / edit product"],
        f"dist_cat_tab_{cid}",
    )

    if tab == "Rebuild from invoices":
        st.subheader("Rebuild from approved invoices")
        st.caption(
            "Takes the latest approved invoice line per product on/after the cutoff. "
            "Rows marked Changed by Admin are not overwritten."
        )
        cutoff = st.date_input(
            "Invoice cutoff (from date)",
            value=date.fromisoformat(dcat.DEFAULT_CUTOFF),
            key="dist_cat_cutoff",
        )
        c1, c2 = st.columns(2)
        if c1.button("Rebuild this customer", type="primary", key="dist_cat_rb1"):
            res = dcat.rebuild_catalog_from_invoices(
                cid, cutoff=str(cutoff), created_by=user.get("id"),
            )
            st.success(
                f"Done: {res['inserted']} new, {res['updated']} updated, "
                f"{res['skipped_admin']} admin-locked kept ({res['products']} invoice products)."
            )
            ff.action_done("Product list rebuilt")
        if c2.button("Rebuild ALL distributors", key="dist_cat_rb_all"):
            results = dcat.rebuild_all_distributors(
                cutoff=str(cutoff), created_by=user.get("id"),
            )
            total_ins = sum(r["inserted"] for r in results)
            total_upd = sum(r["updated"] for r in results)
            st.success(
                f"Rebuilt {len(results)} customers — {total_ins} new, {total_upd} updated lines."
            )
            ff.action_done("All product lists rebuilt")

    elif tab == "Add / edit product":
        st.subheader("Add or change product list item")
        products = db.get_items(active_only=True) or []
        if not products:
            st.warning("No products in master.")
        else:
            pmap = {f"{p['code']} — {p['name']}": p for p in products}
            plabel = st.selectbox("Product", list(pmap.keys()), key="dist_cat_prod")
            prod = pmap[plabel]
            existing = next(
                (r for r in dcat.list_catalog(cid, include_inactive=True) if r["product_id"] == prod["id"]),
                None,
            )
            rate = st.number_input(
                "Rate",
                min_value=0.0,
                value=float(existing["rate"]) if existing else float(prod.get("sale_price") or 0),
                key="dist_cat_rate",
            )
            disc = st.number_input(
                "Discount %",
                min_value=0.0,
                max_value=100.0,
                value=float(existing["discount_pct"]) if existing else 0.0,
                key="dist_cat_disc",
            )
            min_qty = st.number_input(
                "Min qty",
                min_value=0.01,
                value=float(existing["min_qty"]) if existing else 1.0,
                key="dist_cat_minq",
            )
            eff_default = date.today()
            if existing and existing.get("effective_from"):
                try:
                    eff_default = date.fromisoformat(str(existing["effective_from"])[:10])
                except ValueError:
                    pass
            eff = st.date_input("Effective from", value=eff_default, key="dist_cat_eff")
            note = st.text_input("Admin note (optional)", value=(existing or {}).get("admin_note") or "", key="dist_cat_note")
            active = st.checkbox("Active in portal", value=True if not existing else bool(existing.get("is_active")), key="dist_cat_act")
            if st.button("Save to product list (notify distributor)", type="primary", key="dist_cat_save"):
                dcat.upsert_catalog_item(
                    cid,
                    int(prod["id"]),
                    rate=rate,
                    discount_pct=disc,
                    min_qty=min_qty,
                    effective_from=str(eff),
                    admin_note=note,
                    is_active=active,
                    created_by=user.get("id"),
                    notify=True,
                )
                st.success("Saved. Distributor notified. Portal will show Changed by Admin.")
                ff.action_done("Product list item saved")

    elif tab == "Product List":
        rows = dcat.list_catalog(cid, include_inactive=True)
        if not rows:
            st.info("No product list items yet. Run Rebuild from invoices or Add product.")
            return

        st.subheader("Product list — edit prices manually")
        st.caption(
            "Change **Rate**, **Discount %**, **Min qty**, **Active**, or **Note** in the table, "
            "then click **Save price changes**. Saved rows are marked Changed by Admin and the distributor is notified."
        )

        edit_src = []
        for r in rows:
            edit_src.append({
                "product_id": int(r["product_id"]),
                "Code": r.get("product_code") or "",
                "Product": r.get("product_name") or "",
                "Rate": float(r.get("rate") or 0),
                "Discount %": float(r.get("discount_pct") or 0),
                "Min qty": float(r.get("min_qty") or 1),
                "Active": bool(r.get("is_active")),
                "Note": r.get("admin_note") or "",
                "Source": r.get("source") or "",
                "Admin locked": bool(r.get("admin_changed")),
                "Last invoice": (str(r.get("last_invoice_date") or "")[:10] or ""),
                "Effective": (str(r.get("effective_from") or "")[:10] or ""),
            })
        base_df = pd.DataFrame(edit_src)
        edited = st.data_editor(
            base_df,
            hide_index=True,
            use_container_width=True,
            key=f"dist_cat_price_editor_{cid}",
            disabled=["product_id", "Code", "Product", "Source", "Admin locked", "Last invoice", "Effective"],
            column_config={
                "product_id": None,
                "Rate": st.column_config.NumberColumn("Rate", min_value=0.0, step=0.01, format="%.2f"),
                "Discount %": st.column_config.NumberColumn("Discount %", min_value=0.0, max_value=100.0, step=0.01, format="%.2f"),
                "Min qty": st.column_config.NumberColumn("Min qty", min_value=0.01, step=0.01, format="%.2f"),
                "Active": st.column_config.CheckboxColumn("Active"),
                "Note": st.column_config.TextColumn("Note", max_chars=200),
            },
            num_rows="fixed",
        )

        c_save, c_hint = st.columns([1, 2])
        notify_on_save = c_hint.checkbox(
            "Notify distributor on save",
            value=True,
            key=f"dist_cat_notify_{cid}",
        )
        if c_save.button("Save price changes", type="primary", key=f"dist_cat_save_prices_{cid}"):
            # Compare against original rows
            orig_by_pid = {int(r["product_id"]): r for r in rows}
            changed = 0
            errors = []
            for _, erow in edited.iterrows():
                pid = int(erow["product_id"])
                orig = orig_by_pid.get(pid)
                if not orig:
                    continue
                new_rate = float(erow["Rate"] or 0)
                new_disc = float(erow["Discount %"] or 0)
                new_min = float(erow["Min qty"] or 1)
                new_active = bool(erow["Active"])
                new_note = str(erow.get("Note") or "").strip()
                old_rate = float(orig.get("rate") or 0)
                old_disc = float(orig.get("discount_pct") or 0)
                old_min = float(orig.get("min_qty") or 1)
                old_active = bool(orig.get("is_active"))
                old_note = str(orig.get("admin_note") or "").strip()
                if (
                    abs(new_rate - old_rate) < 0.0001
                    and abs(new_disc - old_disc) < 0.0001
                    and abs(new_min - old_min) < 0.0001
                    and new_active == old_active
                    and new_note == old_note
                ):
                    continue
                try:
                    eff = str(orig.get("effective_from") or date.today())[:10]
                    dcat.upsert_catalog_item(
                        cid,
                        pid,
                        rate=new_rate,
                        discount_pct=new_disc,
                        min_qty=max(0.01, new_min),
                        effective_from=eff,
                        admin_note=new_note,
                        is_active=new_active,
                        created_by=user.get("id"),
                        notify=False,
                    )
                    changed += 1
                except Exception as e:
                    errors.append(f"{erow.get('Code')}: {e}")
            if changed and notify_on_save:
                try:
                    from erp_core import notifications as ntf
                    ntf.notify_distributor(
                        cid,
                        "catalog_price",
                        "Product list prices updated",
                        f"Admin updated {changed} price(s) on your product list. Open Product List to review.",
                        ref_type="distributor_catalog",
                        ref_id=cid,
                    )
                except Exception:
                    pass
            if errors:
                st.error("Some rows failed:\n" + "\n".join(errors[:8]))
            if changed:
                ff.action_done(
                    f"Saved **{changed}** price change(s)"
                    + (" — distributor notified." if notify_on_save else ".")
                )
            elif not errors:
                st.info("No price changes detected.")

        with st.expander("Quick edit one line (optional)"):
            edit_labels = [f"{r['product_code']} — {r['product_name']}" for r in rows]
            sel = st.selectbox("Product", ["—"] + edit_labels, key="dist_cat_quick")
            if sel != "—":
                row = rows[edit_labels.index(sel)]
                with st.form("dist_cat_quick_form"):
                    st.caption(f"Editing {row['product_code']}")
                    q_rate = st.number_input("Rate", value=float(row["rate"] or 0), min_value=0.0)
                    q_disc = st.number_input("Discount %", value=float(row["discount_pct"] or 0), min_value=0.0, max_value=100.0)
                    try:
                        q_eff_def = date.fromisoformat(str(row.get("effective_from") or date.today())[:10])
                    except ValueError:
                        q_eff_def = date.today()
                    q_eff = st.date_input("Effective from", value=q_eff_def)
                    q_active = st.checkbox("Active", value=bool(row.get("is_active")))
                    q_note = st.text_input("Note", value=row.get("admin_note") or "")
                    if st.form_submit_button("Update & notify", type="primary"):
                        dcat.upsert_catalog_item(
                            cid,
                            int(row["product_id"]),
                            rate=q_rate,
                            discount_pct=q_disc,
                            min_qty=float(row.get("min_qty") or 1),
                            effective_from=str(q_eff),
                            admin_note=q_note,
                            is_active=q_active,
                            created_by=user.get("id"),
                            notify=True,
                        )
                        ff.action_done("Updated")
