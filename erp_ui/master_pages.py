"""Customer / Supplier / Item master pages — extracted from app.py."""

from datetime import date

import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff


def customer_options(active_only=True):
    rows = db.get_customers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def supplier_options(active_only=True):
    rows = db.get_suppliers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def page_customers():
    peek = st.session_state.get("cust_page_tab") or "List"
    hlp.std_page_header(
        "Customers",
        status="register" if peek == "List" else ("draft" if peek == "Add New" else None),
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab_list_lbl = hlp.sticky_page_tabs(
        ["List", "Add New", "Edit / Delete"],
        "cust_page_tab",
    )

    if tab_list_lbl == "List":
        gid = hlp.master_group_filter("customer", "cust")
        rows = db.get_customers(group_id=gid)
        if rows:
            hlp.master_list_search(
                "Customers", rows, "cust",
                ["code", "name", "group_name", "phone", "city", "province", "credit_limit", "balance", "is_active"],
                {"code": "Code", "name": "Name", "group_name": "Group", "phone": "Phone", "city": "City",
                 "province": "Province", "credit_limit": "Credit Limit", "balance": "Balance", "is_active": "Active"},
            )
        else:
            st.info("No customers yet. Add one in the Add New tab.")

    elif tab_list_lbl == "Add New":
        hlp.section_header("Location")
        fid = "cust_add"
        province, city = hlp.province_city_fields(
            fid, reset_token=ff.form_generation(fid),
        )
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_customer_{gen}"):
            code = st.text_input("Code", value=db.next_code("CUS", "customers"), key=wk("code"))
            name = st.text_input("Name *", key=wk("name"))
            contact = st.text_input("Contact Person", key=wk("contact"))
            phone = st.text_input("Phone", key=wk("phone"))
            email = st.text_input("Email", key=wk("email"))
            address = st.text_area("Address", key=wk("address"))
            ntn = st.text_input("NTN", key=wk("ntn"))
            strn = st.text_input("STRN", key=wk("strn"))
            credit = hlp.money_input(
                "Credit Limit", value=0.0, min_value=0.0, key=wk("credit"),
            )
            opening = hlp.money_input(
                "Opening Balance",
                value=0.0,
                key=wk("opening"),
                help="+ receivable (customer owes you). − credit/advance balance.",
            )
            group_id = hlp.master_group_select("customer", wk("grp"))
            if st.form_submit_button("Save Customer"):
                if not name:
                    st.error("Name is required.")
                else:
                    db.add_customer({"code": code, "name": name, "contact_person": contact, "phone": phone,
                                     "email": email, "address": address, "city": city, "province": province,
                                     "ntn": ntn, "strn": strn,
                                     "credit_limit": credit, "opening_balance": opening, "group_id": group_id}, hlp.uid())
                    ff.finish_new_entry(
                        form_id=fid,
                        message=f"Customer **{name}** saved successfully. Form cleared for the next entry.",
                    )

    elif tab_list_lbl == "Edit / Delete":
        rows = db.get_customers(active_only=False)
        if not rows:
            st.info("No customers to edit.")
            return
        _, cid, _ = hlp.smart_select(
            "Customer", rows, "cust_edit", "id",
            lambda r: f"{r['code']} - {r['name']}" + (f" | {r['city']}" if r.get('city') else "") + (f" | {r['phone']}" if r.get('phone') else ""),
            placeholder="Type customer code, name, phone, city, or NTN...",
        )
        if not cid:
            return
        c = db.get_customer(cid)
        hlp.section_header("Location")
        province, city = hlp.province_city_fields(
            "cust_edit",
            province=c.get("province") or "",
            city=c.get("city") or "",
            reset_token=cid,
        )
        with st.form("edit_customer"):
            code = st.text_input("Code", value=c["code"])
            name = st.text_input("Name", value=c["name"])
            contact = st.text_input("Contact Person", value=c["contact_person"] or "")
            phone = st.text_input("Phone", value=c["phone"] or "")
            email = st.text_input("Email", value=c["email"] or "")
            address = st.text_area("Address", value=c["address"] or "")
            ntn = st.text_input("NTN", value=c.get("ntn") or "")
            strn = st.text_input("STRN", value=c.get("strn") or "")
            st.markdown("**Portal / operations contacts** *(updated by distributor on portal Profile)*")
            pc1, pc2, pc3 = st.columns(3)
            dispatch_phone = pc1.text_input(
                "Dispatch phone", value=c.get("dispatch_phone") or "", key="cust_edit_dispatch",
            )
            accounts_phone = pc2.text_input(
                "Accounts phone", value=c.get("accounts_phone") or "", key="cust_edit_accounts",
            )
            owner_phone = pc3.text_input(
                "Owner phone", value=c.get("owner_phone") or "", key="cust_edit_owner",
            )
            credit = hlp.money_input("Credit Limit", value=float(c["credit_limit"]), min_value=0.0, key="cust_edit_credit")
            opening = hlp.money_input("Opening Balance", value=float(c["opening_balance"]), key="cust_edit_opening")
            st.caption("Signed: **positive = Dr**, **negative = Cr** (Finance Manager).")
            group_id = hlp.master_group_select("customer", "cust_edit", c.get("group_id"))
            active = st.checkbox("Active", value=bool(c["is_active"]))
            c1, c2 = st.columns(2)
            update = c1.form_submit_button("Update")
            delete = c2.form_submit_button("Delete", type="secondary")
            if update:
                db.update_customer(cid, {"code": code, "name": name, "contact_person": contact, "phone": phone,
                                         "email": email, "address": address, "city": city, "province": province,
                                         "ntn": ntn, "strn": strn,
                                         "dispatch_phone": dispatch_phone or None,
                                         "accounts_phone": accounts_phone or None,
                                         "owner_phone": owner_phone or None,
                                         "credit_limit": credit, "opening_balance": opening, "group_id": group_id,
                                         "is_active": int(active)})
                ff.action_done(f"Customer **{name}** updated successfully.")
            if delete:
                db.delete_customer(cid)
                ff.action_done(f"Customer **{code}** deleted successfully.")


def page_suppliers():
    peek = st.session_state.get("sup_page_tab") or "List"
    hlp.std_page_header(
        "Suppliers",
        status="register" if peek == "List" else ("draft" if peek == "Add New" else None),
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab = hlp.sticky_page_tabs(["List", "Add New", "Edit / Delete"], "sup_page_tab")

    if tab == "List":
        gid = hlp.master_group_filter("supplier", "sup")
        rows = db.get_suppliers(group_id=gid)
        if rows:
            hlp.master_list_search(
                "Suppliers", rows, "sup",
                ["code", "name", "group_name", "phone", "city", "balance", "is_active"],
                {"code": "Code", "name": "Name", "group_name": "Group", "phone": "Phone", "city": "City",
                 "balance": "Balance", "is_active": "Active"},
            )
        else:
            st.info("No suppliers yet.")

    elif tab == "Add New":
        fid = "sup_add"
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_supplier_{gen}"):
            code = st.text_input("Code", value=db.next_code("SUP", "suppliers"), key=wk("code"))
            name = st.text_input("Name *", key=wk("name"))
            contact = st.text_input("Contact Person", key=wk("contact"))
            phone = st.text_input("Phone", key=wk("phone"))
            email = st.text_input("Email", key=wk("email"))
            address = st.text_area("Address", key=wk("address"))
            city = st.text_input("City", key=wk("city"))
            opening = hlp.money_input(
                "Opening Balance",
                value=0.0,
                key=wk("opening"),
                help="+ payable (you owe supplier).",
            )
            group_id = hlp.master_group_select("supplier", wk("grp"))
            if st.form_submit_button("Save Supplier"):
                if not name:
                    st.error("Name is required.")
                else:
                    db.add_supplier({"code": code, "name": name, "contact_person": contact, "phone": phone,
                                     "email": email, "address": address, "city": city,
                                     "opening_balance": opening, "group_id": group_id})
                    ff.finish_new_entry(
                        form_id=fid,
                        message=f"Supplier **{name}** saved successfully. Form cleared for the next entry.",
                    )

    elif tab == "Edit / Delete":
        rows = db.get_suppliers(active_only=False)
        if not rows:
            st.info("No suppliers to edit.")
            return
        _, sid, _ = hlp.smart_select(
            "Supplier", rows, "sup_edit", "id",
            lambda r: f"{r['code']} - {r['name']}" + (f" | {r['city']}" if r.get('city') else "") + (f" | {r['phone']}" if r.get('phone') else ""),
            placeholder="Type supplier code, name, phone, or city...",
        )
        if not sid:
            return
        s = db.get_supplier(sid)
        with st.form("edit_supplier"):
            code = st.text_input("Code", value=s["code"])
            name = st.text_input("Name", value=s["name"])
            contact = st.text_input("Contact Person", value=s["contact_person"] or "")
            phone = st.text_input("Phone", value=s["phone"] or "")
            email = st.text_input("Email", value=s["email"] or "")
            address = st.text_area("Address", value=s["address"] or "")
            city = st.text_input("City", value=s["city"] or "")
            opening = hlp.money_input("Opening Balance", value=float(s["opening_balance"]), key="sup_edit_opening")
            st.caption("Signed: **positive = Dr**, **negative = Cr** (Finance Manager — suppliers can be either).")
            group_id = hlp.master_group_select("supplier", "sup_edit", s.get("group_id"))
            active = st.checkbox("Active", value=bool(s["is_active"]))
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Update"):
                db.update_supplier(sid, {"code": code, "name": name, "contact_person": contact, "phone": phone,
                                         "email": email, "address": address, "city": city,
                                         "opening_balance": opening, "group_id": group_id,
                                         "is_active": int(active)})
                ff.action_done(f"Supplier **{name}** updated successfully.")
            if c2.form_submit_button("Delete"):
                db.delete_supplier(sid)
                ff.action_done(f"Supplier **{code}** deleted successfully.")


def page_items():
    peek = st.session_state.get("prod_page_tab") or "List"
    hlp.std_page_header(
        "Products",
        status="register" if peek == "List" else ("draft" if peek == "Add New" else None),
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab = hlp.sticky_page_tabs(
        ["List", "Add New", "Edit / Delete", "Import Weights"],
        "prod_page_tab",
    )

    cats = db.get_product_categories()
    cat_opts = {f"{r['code']} - {r['name']}": r["id"] for r in cats}
    units = db.get_units_of_measure()
    unit_opts = {f"{r['symbol']} - {r['name']}": r["id"] for r in units}
    tax_rates = db.get_tax_rates()
    tax_opts = {f"{t['code']} - {t['name']}": t["id"] for t in tax_rates}
    item_types = ["raw", "finished", "packaging", "trading", "service"]
    weight_units = ["kg", "gram", "liter", "ml", "ton", "piece", "carton", "bag", "drum"]

    if tab == "List":
        gid = hlp.master_group_filter("product", "prod")
        rows = db.get_items(group_id=gid)
        if rows:
            hlp.master_list_search(
                "Products", rows, "prod",
                [
                    "code", "name", "group_name", "category", "unit", "item_type",
                    "standard_weight", "weight_unit", "packing_size",
                    "purchase_price", "sale_price", "stock_qty", "reorder_level",
                ],
                {
                    "code": "Code", "name": "Name", "group_name": "Group", "category": "Category", "unit": "Unit",
                    "item_type": "Type", "standard_weight": "Std Weight", "weight_unit": "Wt Unit",
                    "packing_size": "Packing",
                    "purchase_price": "Purchase Price", "sale_price": "Sale Price",
                    "stock_qty": "Stock", "reorder_level": "Reorder Level",
                },
                extra_fields=["packing_size", "standard_weight", "weight_unit"],
            )
        else:
            st.info("No items yet.")

    elif tab == "Add New":
        fid = "item_add"
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_item_{gen}"):
            code = st.text_input("Code", value=db.next_code("ITM", "items"), key=wk("code"))
            name = st.text_input("Name *", key=wk("name"))
            category = st.selectbox("Category", list(cat_opts.keys()), key=wk("cat"))
            cat_id = cat_opts[category]
            unit_lbl = st.selectbox("Unit", list(unit_opts.keys()), key=wk("unit"))
            unit_id = unit_opts[unit_lbl]
            item_type = st.selectbox("Type", item_types, key=wk("type"))
            weight_unit = st.selectbox("Weight Unit", weight_units, key=wk("wunit"))
            standard_weight = st.number_input(
                "Standard Weight per Unit", min_value=0.0, value=0.0, key=wk("stdw"),
            )
            packing_size = st.text_input("Packing Size", key=wk("pack"))
            tax_lbl = st.selectbox("Tax Category", ["—"] + list(tax_opts.keys()), key=wk("tax"))
            tax_id = tax_opts.get(tax_lbl) if tax_lbl != "—" else None
            pp = hlp.money_input("Purchase Price", value=0.0, min_value=0.0, key=wk("pp"))
            sp = hlp.money_input("Sale Price", value=0.0, min_value=0.0, key=wk("sp"))
            reorder = st.number_input("Reorder Level", min_value=0.0, value=0.0, key=wk("reorder"))
            min_stock = st.number_input("Minimum Stock", min_value=0.0, value=0.0, key=wk("min"))
            stock = st.number_input("Opening Stock", min_value=0.0, value=0.0, key=wk("stock"))
            group_id = hlp.master_group_select("product", wk("grp"))
            if st.form_submit_button("Save Item"):
                if not name:
                    st.error("Name is required.")
                else:
                    db.add_item({"code": code, "name": name, "category_id": cat_id, "unit_id": unit_id,
                                 "item_type": item_type, "weight_unit": weight_unit, "standard_weight": standard_weight,
                                 "packing_size": packing_size, "tax_rate_id": tax_id,
                                 "purchase_price": pp, "sale_price": sp,
                                 "reorder_level": reorder, "min_stock": min_stock, "stock_qty": stock,
                                 "group_id": group_id}, hlp.uid())
                    ff.finish_new_entry(
                        form_id=fid,
                        message=f"Item **{name}** saved successfully. Form cleared for the next entry.",
                    )

    elif tab == "Import Weights":
        from import_product_weights import (
            DEFAULT_ACCDB,
            apply_weights,
            load_pairs,
            load_weights_from_sales_inventory,
            write_weight_template_csv,
        )

        st.markdown("**Sync missing sale / purchase rates (old database)**")
        st.caption(
            "Fills **Sale Price** and **Purchase Price** on products that are zero, using: "
            "last ERP invoice rate → FMYE ItemInformation / last invoice → Sales & Inventory .accdb."
        )
        if st.button("Sync rates from old data", type="primary", key="rate_legacy_sync"):
            try:
                from product_rates_legacy import sync_missing_product_rates, clear_rate_cache
                clear_rate_cache()
                stats = sync_missing_product_rates(user_id=hlp.uid(), dry_run=False)
                ff.action_done(
                    f"Updated sale price on **{stats['sale_updated']}** products, "
                    f"purchase price on **{stats['purchase_updated']}**. "
                    f"Already had rates: **{stats['skipped']}**."
                )
            except Exception as e:
                st.error(str(e))

        st.divider()
        st.markdown("**Import standard weight from Sales & Inventory (Access)**")
        st.caption(
            "Reads **ProductID** + **Weight** from `tblProduct`. "
            "Updates ERP **Std Weight** only where the product **code** already exists and weight > 0."
        )
        acc_path = st.text_input("Access file", value=str(DEFAULT_ACCDB), key="wt_import_path")
        if st.button("Import weights now", type="primary", key="wt_accdb_run"):
            try:
                pairs, ex = load_weights_from_sales_inventory(Path(acc_path.strip()))
                stats = apply_weights(pairs, dry_run=False, user_id=hlp.uid())
                detail = (
                    f"Access products: **{ex['access_rows']}** | "
                    f"No weight: **{ex['skipped_no_weight']}** | "
                    f"Code not in ERP: **{stats['skipped_no_product']}**"
                )
                ff.action_done(
                    f"Updated **{stats['updated']}** products "
                    f"({len(pairs)} rows with code + weight in Access). {detail}"
                )
            except Exception as e:
                st.error(str(e))

        with st.expander("CSV template or other file"):
            tpl = Path(__file__).parent / "import" / "product_weights_template.csv"
            n_tpl = write_weight_template_csv(tpl)
            st.download_button(
                f"Download CSV template ({n_tpl} products)",
                data=tpl.read_bytes(),
                file_name="product_weights_template.csv",
                mime="text/csv",
                key="wt_tpl_save",
            )
            up = st.file_uploader("Upload CSV", type=["csv"], key="wt_csv_up")
            if up and st.button("Import from CSV", key="wt_csv_run"):
                try:
                    import tempfile

                    tmp = Path(tempfile.gettempdir()) / "product_weights_upload.csv"
                    tmp.write_bytes(up.getvalue())
                    _, _, _, pairs, _ex = load_pairs(
                        accdb=None, csv_path=tmp, table=None, code_col=None, weight_col=None
                    )
                    stats = apply_weights(pairs, dry_run=False, user_id=hlp.uid())
                    ff.action_done(f"Updated **{stats['updated']}** products.")
                except Exception as e:
                    st.error(str(e))

    elif tab == "Edit / Delete":
        items = db.get_items()
        if not items:
            st.info("No items to edit.")
            return
        _, iid, _ = hlp.smart_select(
            "Product", items, "item_edit", "id",
            lambda r: f"{r['code']} - {r['name']} ({r.get('stock_qty', 0)} {r.get('unit', '')})",
            placeholder="Type product code or name (e.g. SF0017 or BRILLO)...",
        )
        if not iid:
            return
        it = db.get_item(iid)
        cat_labels = list(cat_opts.keys()) or [it.get("category") or "—"]
        default_cat = next((k for k, v in cat_opts.items() if v == it.get("category_id")), cat_labels[0])
        unit_labels = list(unit_opts.keys()) or [it.get("unit") or "—"]
        default_unit = next((k for k, v in unit_opts.items() if v == it.get("unit_id")), unit_labels[0])
        wu = (it.get("weight_unit") or "kg").lower()
        tax_labels = ["—"] + list(tax_opts.keys())
        default_tax = next((k for k, v in tax_opts.items() if v == it.get("tax_rate_id")), "—")

        with st.form("edit_item"):
            code = st.text_input("Code", value=it["code"])
            name = st.text_input("Name", value=it["name"])
            category = st.selectbox(
                "Category", cat_labels,
                index=cat_labels.index(default_cat) if default_cat in cat_labels else 0,
            )
            cat_id = cat_opts.get(category)
            unit_lbl = st.selectbox(
                "Unit", unit_labels,
                index=unit_labels.index(default_unit) if default_unit in unit_labels else 0,
            )
            unit_id = unit_opts.get(unit_lbl)
            item_type = st.selectbox(
                "Type", item_types,
                index=item_types.index(it["item_type"]) if it.get("item_type") in item_types else 0,
            )
            c1, c2 = st.columns(2)
            weight_unit = c1.selectbox(
                "Weight Unit", weight_units,
                index=weight_units.index(wu) if wu in weight_units else 0,
            )
            standard_weight = c2.number_input(
                "Standard Weight per Unit", min_value=0.0,
                value=float(it.get("standard_weight") or 0),
            )
            packing_size = st.text_input("Packing Size", value=it.get("packing_size") or "")
            tax_lbl = st.selectbox(
                "Tax Category", tax_labels,
                index=tax_labels.index(default_tax) if default_tax in tax_labels else 0,
            )
            tax_id = tax_opts.get(tax_lbl) if tax_lbl != "—" else None
            group_id = hlp.master_group_select("product", "item_edit", it.get("group_id"))
            c3, c4 = st.columns(2)
            with c3:
                pp = hlp.money_input("Purchase Price", value=float(it["purchase_price"]), min_value=0.0, key="item_edit_pp")
            with c4:
                sp = hlp.money_input("Sale Price", value=float(it["sale_price"]), min_value=0.0, key="item_edit_sp")
            c5, c6 = st.columns(2)
            reorder = c5.number_input("Reorder Level", min_value=0.0, value=float(it["reorder_level"]))
            min_stock = c6.number_input("Minimum Stock", min_value=0.0, value=float(it.get("min_stock") or 0))
            active = st.checkbox("Active", value=bool(it["is_active"]))
            st.info(f"Current Stock: {it['stock_qty']} {it['unit']} (adjust via Inventory module)")
            blockers = db.get_product_delete_blockers(iid)
            if blockers:
                st.warning(
                    "This product is used in: **"
                    + "**, **".join(blockers)
                    + "**. It cannot be permanently deleted — use **Deactivate** instead."
                )
            c7, c8, c9 = st.columns(3)
            if c7.form_submit_button("Update"):
                db.update_item(iid, {
                    "code": code, "name": name, "category_id": cat_id, "unit_id": unit_id,
                    "item_type": item_type, "weight_unit": weight_unit, "standard_weight": standard_weight,
                    "packing_size": packing_size, "tax_rate_id": tax_id,
                    "purchase_price": pp, "sale_price": sp,
                    "reorder_level": reorder, "min_stock": min_stock, "group_id": group_id,
                    "is_active": int(active),
                }, hlp.uid())
                ff.action_done(f"Item **{name}** updated successfully.")
            if c8.form_submit_button("Delete Permanently", disabled=bool(blockers)):
                try:
                    db.delete_item(iid, hlp.uid())
                    ff.action_done(
                        f"Item **{code}** deleted successfully.",
                        prefixes=("item_edit",),
                        also=("item_edit_srch", "item_edit_sel", "srch_item_edit", "sel_item_edit"),
                    )
                except ValueError as e:
                    st.error(str(e))
            if c9.form_submit_button("Deactivate"):
                db.deactivate_item(iid, hlp.uid())
                ff.action_done(f"Item **{name}** deactivated — hidden from new transactions.")

