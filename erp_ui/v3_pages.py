"""V3 module pages — IFS Chemicals ERP."""

from datetime import date
import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import transaction_list as txn
from erp_ui import form_flow as ff


def uid():
    u = st.session_state.get("user")
    return u["id"] if u else None


def fmt(v):
    return f"Rs. {float(v or 0):,.2f}"


def export_df(df, name, title=None):
    if df is not None and not df.empty:
        from erp_ui.report_print import report_toolbar
        report_toolbar(df, title or name.replace("_", " ").title(), name, key_prefix=f"v3_{name}")


def line_doc_page(title, list_fn, save_fn, delete_fn, doc_type, party_label, party_opts_fn, show_weight=True, register_fn=None):
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    hlp.std_page_header(title, status="register", status_kind="shell")
    from erp_core.document_workflow import DOC_SHORT_TO_KEY
    from erp_ui.document_hub import render_document_hub

    hub_key = DOC_SHORT_TO_KEY.get(doc_type)
    tabs = ["List", "Open Existing", "New", "Edit / Delete"] if hub_key else ["List", "New", "Edit / Delete"]
    tab = sticky_page_tabs(tabs, f"v3_{doc_type}_tab")

    if tab == "List":
        if register_fn:
            register_fn()
        else:
            rows = list_fn()
            if rows:
                render_dataframe_html_table(pd.DataFrame(rows))
                export_df(pd.DataFrame(rows), title.replace(" ", "_"))
            else:
                st.info("No records.")
    elif hub_key and tab == "Open Existing":
        render_document_hub(hub_key, f"v3_{doc_type}")
    elif tab == "New":
        items = {f"{r['code']} - {r['name']} ({r.get('stock_qty',0)})": r for r in db.get_items(active_only=True)}
        default_tax = db.default_tax_rate_id()
        if not party_opts_fn() or not items:
            st.warning("Add master data first.")
            return
        with st.form(f"new_{doc_type}"):
            doc_no = st.text_input("Document No", db.peek_document(doc_type))
            party = st.selectbox(party_label, list(party_opts_fn().keys()))
            doc_date = st.date_input("Date", value=date.today())
            notes = st.text_input("Notes")
            go = st.form_submit_button("Continue to Lines")
        if go:
            st.session_state[f"{doc_type}_hdr"] = {
                "document_no": doc_no, "party_id": party_opts_fn()[party],
                "date": str(doc_date), "notes": notes,
                "discount_pct": 0, "tax_rate_id": default_tax,
            }
            st.session_state[f"{doc_type}_lines"] = [{"product_id": None, "quantity": 1, "rate": 0, "amount": 0}]
        if f"{doc_type}_hdr" in st.session_state:
            hdr = st.session_state[f"{doc_type}_hdr"]
            raw_lines, _ = _line_editor(items, doc_type, show_weight)
            tax_lines = [
                {"item_id": l["product_id"], "quantity": l["quantity"], "rate": l["rate"], "amount": l["amount"]}
                for l in raw_lines
            ]
            tax_hdr, _totals = hlp.invoice_tax_form(f"{doc_type}_tax", tax_lines, hdr)
            hdr.update({k: tax_hdr[k] for k in ("discount_pct", "tax_rate_id", "tax_inclusive") if k in tax_hdr})
            if st.button(f"Save {title}", key=f"save_{doc_type}"):
                if raw_lines:
                    try:
                        save_fn(hdr, raw_lines, None, uid())
                        ff.finish_new_entry(doc_type, form_id=f"v3_{doc_type}", message="Saved.")
                    except Exception as e:
                        st.error(str(e))
    elif tab == "Edit / Delete":
        if register_fn:
            _edit_picker(doc_type, party_opts_fn, delete_fn)
            return
        rows = list_fn()
        if rows and delete_fn:
            sel = st.selectbox("Select", [f"{r.get('document_no', r.get('invoice_no', r.get('return_no','')))}" for r in rows])
            rid = next(r["id"] for r in rows if r.get("document_no", r.get("invoice_no")) == sel or r.get("return_no") == sel)
            if st.button("Delete"):
                delete_fn(rid, uid()); ff.action_done("Deleted")


def _edit_picker(doc_type, party_opts_fn, delete_fn):
    from erp_core.document_workflow import DOC_SHORT_TO_KEY
    from erp_ui.document_hub import render_document_hub

    key = DOC_SHORT_TO_KEY.get(doc_type)
    if key:
        render_document_hub(key, f"v3_{doc_type}")
        return
    search_map = {
        "PO": (db.search_purchase_orders, lambda r: f"{r['document_no']} — {r['supplier_name']}", "Supplier", "supplier_id"),
        "PRQ": (db.search_purchase_requisitions, lambda r: f"{r['document_no']} ({r['req_date']})", None, None),
        "SO": (db.search_sales_orders, lambda r: f"{r['document_no']} — {r.get('customer_name','')}", "Customer", "customer_id"),
        "QT": (db.search_quotations, lambda r: f"{r['document_no']} — {r.get('customer_name','')}", "Customer", "customer_id"),
        "DN": (db.search_delivery_notes, lambda r: f"{r['document_no']} — {r.get('customer_name','')}", "Customer", "customer_id"),
        "GRN": (db.search_grns, lambda r: f"{r['document_no']} — {r.get('supplier_name','')}", "Supplier", "supplier_id"),
    }
    if doc_type not in search_map:
        return
    sfn, lbl_fn, plbl, pkw = search_map[doc_type]
    party_opts = party_opts_fn() if party_opts_fn and plbl else None
    rid, _ = txn.document_picker(f"{doc_type}_edit", sfn, lbl_fn, plbl, party_opts, pkw)
    if rid and delete_fn and st.button("Delete", key=f"del_{doc_type}"):
        delete_fn(rid, uid())
        ff.action_done("Deleted")
    elif not rid:
        st.info("Search and select a record.")


def _line_editor(items, prefix, show_weight):
    """Quotations, sales orders, purchase orders — shared tabular line grid."""
    return hlp.line_items_editor(items, prefix, show_weight=show_weight)


# --- Master pages ---
def page_product_categories():
    _crud("Product Categories", db.get_product_categories, None,
          lambda d, u: _ins("product_categories", d, u),
          lambda i, d, u: _upd("product_categories", i, d, u),
          lambda i, u: _del("product_categories", i), "CAT", [("name", "Name")])


def page_units():
    _crud("Units of Measure", db.get_units_of_measure, None,
          lambda d, u: _ins_uom(d, u), lambda i, d, u: _upd_uom(i, d, u),
          lambda i, u: _del("units_of_measure", i), "U", [("name", "Name"), ("symbol", "Symbol")])


def page_warehouses():
    _crud("Warehouses", db.get_warehouses, None,
          lambda d, u: _ins_wh(d, u), lambda i, d, u: _upd_wh(i, d, u),
          lambda i, u: _del("warehouses", i), "WH", [("name", "Name"), ("address", "Address"), ("city", "City")])


def page_employees():
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    hlp.std_page_header("Employees", status="register", status_kind="shell")
    rows = db.get_employees()
    tab = sticky_page_tabs(["List", "Add"], "v3_emp_tab")
    if tab == "List":
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
    elif tab == "Add":
        with st.form("add_emp"):
            code = st.text_input("Code", db.next_code("EMP", "employees"))
            name = st.text_input("Full Name")
            dept = st.text_input("Department")
            if st.form_submit_button("Save") and name:
                with db.get_connection() as conn:
                    conn.execute("INSERT INTO employees(code,full_name,department,created_by) VALUES(?,?,?,?)",
                                 (code, name, dept, uid()))
                st.rerun()


def page_departments():
    _crud("Departments", db.get_departments, db.get_department,
          db.add_department, db.update_department, db.delete_department, "DEP", [("name", "Name")])


def page_tax_rates():
    _tax_page()


def page_payment_terms():
    _crud("Payment Terms", db.get_payment_terms, None,
          db.add_payment_term, db.update_payment_term, db.delete_payment_term, "PT",
          [("name", "Name"), ("days", "Days", "n")])


def page_vehicles():
    _crud("Vehicles", db.get_vehicles, None,
          db.add_vehicle, db.update_vehicle, db.delete_vehicle, "VH",
          [("registration_no", "Registration"), ("driver_name", "Driver"), ("vehicle_type", "Type")])


def page_machines():
    _crud("Machines", db.get_machines, None,
          db.add_machine, db.update_machine, db.delete_machine, "MC",
          [("name", "Name"), ("production_line", "Line"), ("capacity", "Capacity", "n")])


def _ins(table, d, u):
    with db.get_connection() as conn:
        conn.execute(f"INSERT INTO {table}(code,name,created_by) VALUES(?,?,?)", (d["code"], d["name"], u))

def _upd(table, i, d, u):
    with db.get_connection() as conn:
        conn.execute(f"UPDATE {table} SET code=?,name=?,is_active=?,modified_at=datetime('now','localtime') WHERE id=?",
                     (d["code"], d["name"], d.get("is_active", 1), i))

def _del(table, i):
    with db.get_connection() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (i,))

def _ins_uom(d, u):
    with db.get_connection() as conn:
        conn.execute("INSERT INTO units_of_measure(code,name,symbol,created_by) VALUES(?,?,?,?)",
                     (d["code"], d["name"], d["symbol"], u))

def _upd_uom(i, d, u):
    with db.get_connection() as conn:
        conn.execute("UPDATE units_of_measure SET code=?,name=?,symbol=?,is_active=? WHERE id=?",
                     (d["code"], d["name"], d["symbol"], d.get("is_active", 1), i))

def _ins_wh(d, u):
    with db.get_connection() as conn:
        conn.execute("INSERT INTO warehouses(code,name,address,city,created_by) VALUES(?,?,?,?,?)",
                     (d["code"], d["name"], d.get("address"), d.get("city"), u))

def _upd_wh(i, d, u):
    with db.get_connection() as conn:
        conn.execute("UPDATE warehouses SET code=?,name=?,address=?,city=?,is_active=? WHERE id=?",
                     (d["code"], d["name"], d.get("address"), d.get("city"), d.get("is_active", 1), i))


def _crud(title, list_fn, get_fn, add_fn, update_fn, delete_fn, prefix, fields):
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    peek = st.session_state.get(f"v3_crud_{title}_tab") or "List"
    hlp.std_page_header(
        title,
        status="register" if peek == "List" else None,
        status_kind="shell" if peek == "List" else "invoice",
    )
    search = st.text_input("Search")
    tab = sticky_page_tabs(["List", "Add", "Edit / Delete"], f"v3_crud_{title}_tab")
    rows = list_fn(search or None) if search else list_fn()
    if tab == "List":
        if rows:
            active_n = sum(1 for r in rows if r.get("is_active", 1))
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Records</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            if "is_active" in (rows[0] if rows else {}):
                k2.markdown(
                    f"<div class='txn-kpi-card'><p class='txn-kpi'>Active</p>"
                    f"<p class='txn-kpi-val'>{active_n:,}</p></div>",
                    unsafe_allow_html=True,
                )
            render_dataframe_html_table(pd.DataFrame(rows))
            export_df(pd.DataFrame(rows), title.replace(" ", "_"))
    elif tab == "Add":
        with st.form(f"add_{title}"):
            data = {"code": st.text_input("Code", db.next_code(prefix, {
                "Product Categories": "product_categories", "Units of Measure": "units_of_measure",
                "Warehouses": "warehouses", "Departments": "departments",
                "Payment Terms": "payment_terms", "Vehicles": "vehicles", "Machines": "machines",
            }.get(title, title.lower().replace(" ", "_"))))}
            for f in fields:
                if len(f) == 3 and f[2] == "n":
                    data[f[0]] = st.number_input(f[1], value=0.0)
                else:
                    data[f[0]] = st.text_input(f[1])
            if st.form_submit_button("Save"):
                add_fn(data, uid()); ff.action_done("Saved")
    elif tab == "Edit / Delete":
        if not rows:
            return
        sel = st.selectbox("Select", [f"{r['code']} - {r.get('name', r.get('registration_no',''))}" for r in rows])
        if not sel:
            return
        rid = next((r["id"] for r in rows if str(sel).startswith(str(r["code"]))), None)
        if rid is None:
            st.warning("Could not resolve selection.")
            return
        rec = get_fn(rid) if get_fn else next(r for r in rows if r["id"] == rid)
        with st.form(f"edit_{title}"):
            data = {"code": st.text_input("Code", rec["code"])}
            for f in fields:
                if len(f) == 3 and f[2] == "n":
                    data[f[0]] = st.number_input(f[1], value=float(rec.get(f[0]) or 0))
                else:
                    data[f[0]] = st.text_input(f[1], str(rec.get(f[0]) or ""))
            data["is_active"] = st.checkbox("Active", bool(rec.get("is_active", 1)))
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Update"):
                update_fn(rid, data, uid()); st.rerun()
            if c2.form_submit_button("Delete"):
                delete_fn(rid, uid() if delete_fn.__code__.co_argcount > 1 else None); st.rerun()


def _tax_page():
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    hlp.std_page_header("Tax Rates", status="register", status_kind="shell")
    rows = db.get_tax_rates()
    tab = sticky_page_tabs(["List", "Add", "Edit"], "v3_tax_tab")
    if tab == "List":
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
    elif tab == "Add":
        with st.form("tx"):
            d = {"code": st.text_input("Code", db.next_code("TAX", "tax_rates")), "name": st.text_input("Name"),
                 "sales_tax_pct": st.number_input("Sales Tax %", 18.0), "further_tax_pct": 0.0,
                 "extra_tax_pct": 0.0, "wht_pct": 0.0, "is_exempt": 0}
            if st.form_submit_button("Save"):
                db.add_tax_rate(d, uid()); st.rerun()
    elif tab == "Edit":
        if not rows: return
        sel = st.selectbox("Select", [f"{r['code']} - {r['name']}" for r in rows])
        rid = next(r["id"] for r in rows if sel.startswith(r["code"]))
        r = next(x for x in rows if x["id"] == rid)
        with st.form("etx"):
            if st.form_submit_button("Delete"):
                db.delete_tax_rate(rid, uid()); st.rerun()


# --- Sales workflow ---
def page_quotations():
    peek = st.session_state.get("qt_page_tab") or "List"
    hlp.std_page_header(
        "Quotations",
        subtitle="List · New · Edit · Create SO · Create Invoice",
        status="register" if peek == "List" else None,
        status_kind="shell",
    )
    _qt_tab = hlp.sticky_page_tabs(
        ["List", "New", "Edit / Delete", "Create Sales Order", "Create Invoice"],
        "qt_page_tab",
    )

    items = {f"{r['code']} - {r['name']} ({r.get('stock_qty',0)})": r for r in db.get_items(active_only=True)}
    tax_rates = db.get_tax_rates()
    default_tax = db.default_tax_rate_id()
    cust_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}

    if _qt_tab == "List":
        txn.quotation_register_list()

    elif _qt_tab == "New":
        if not cust_opts or not items:
            st.warning("Add customers and products first.")
        else:
            with st.form("new_QT"):
                doc_no = st.text_input("Document No", db.peek_document("QT"))
                cust_labels, blank = hlp.options_with_blank(cust_opts.keys())
                party = st.selectbox("Customer", cust_labels)
                doc_date = st.date_input("Date", value=date.today())
                valid = st.date_input("Valid Until", value=date.today())
                notes = st.text_input("Notes")
                go = st.form_submit_button("Continue to Lines")
            if go:
                if not hlp.require_selected("customer", party, blank):
                    pass
                else:
                    st.session_state["QT_hdr"] = {
                        "document_no": doc_no, "party_id": cust_opts[party],
                        "date": str(doc_date), "valid_until": str(valid), "notes": notes,
                        "discount_pct": 0, "tax_rate_id": default_tax,
                    }
                    st.session_state["QT_lines"] = [{"product_id": None, "quantity": 1, "rate": 0, "amount": 0}]
            if "QT_hdr" in st.session_state:
                hdr = st.session_state["QT_hdr"]
                raw_lines, _ = _line_editor(items, "QT", True)
                tax_lines = [
                    {"item_id": l["product_id"], "quantity": l["quantity"], "rate": l["rate"], "amount": l["amount"]}
                    for l in raw_lines
                ]
                tax_hdr, _ = hlp.invoice_tax_form("QT_tax", tax_lines, hdr)
                hdr.update({k: tax_hdr[k] for k in ("discount_pct", "tax_rate_id", "tax_inclusive") if k in tax_hdr})
                data = {
                    "document_no": hdr["document_no"], "quote_date": hdr["date"], "customer_id": hdr["party_id"],
                    "valid_until": hdr.get("valid_until"), "discount_pct": hdr.get("discount_pct", 0),
                    "tax_rate_id": hdr.get("tax_rate_id"), "tax_inclusive": hdr.get("tax_inclusive", 0),
                    "notes": hdr.get("notes"),
                }
                if st.button("Save Quotation", key="save_QT"):
                    if raw_lines:
                        try:
                            db.save_quotation(data, raw_lines, None, uid())
                            del st.session_state["QT_hdr"]
                            del st.session_state["QT_lines"]
                            ff.action_done("Quotation saved.")
                        except Exception as e:
                            st.error(str(e))
                    else:
                        st.error("Add at least one line item.")

    elif _qt_tab == "Edit / Delete":
        rid, _ = txn.document_picker(
            "qt_edit", db.search_quotations,
            lambda r: f"{r['document_no']} — {r['customer_name']}",
            "Customer", cust_opts, "customer_id",
        )
        if rid and st.button("Delete selected quotation", key="qt_del"):
            db.delete_quotation(rid, uid())
            ff.action_done("Deleted")
        elif not rid:
            st.info("Search and select a quotation to delete.")

    elif _qt_tab == "Create Sales Order":
        quotes = db.get_quotations_for_conversion()
        if not quotes:
            st.info("No open quotations.")
        else:
            qt_opts = {f"{q['document_no']} — {q['customer_name']}": q["id"] for q in quotes}
            sel = st.selectbox("Quotation", list(qt_opts.keys()), key="qt_to_so")
            if st.button("Load into Sales Order", type="primary", key="qt_so_btn"):
                try:
                    hlp.prime_sales_order_from_quotation(qt_opts[sel])
                    ff.action_done("Quotation loaded. Go to **Sales Orders → New** to review and save.")
                except Exception as e:
                    st.error(str(e))

    elif _qt_tab == "Create Invoice":
        quotes = db.get_quotations_for_conversion()
        if not quotes:
            st.info("No open quotations.")
        else:
            qt_opts = {f"{q['document_no']} — {q['customer_name']}": q["id"] for q in quotes}
            sel = st.selectbox("Quotation", list(qt_opts.keys()), key="qt_to_inv")
            no_wb = st.checkbox("No weighbridge", key="qt_inv_no_wb")
            retail = st.checkbox("Retail cash", key="qt_inv_retail")
            if st.button("Load into Sales Invoice", type="primary", key="qt_inv_btn"):
                try:
                    hlp.prime_sale_from_quotation(qt_opts[sel], no_weighbridge=no_wb, retail=retail)
                    ff.action_done("Quotation loaded. Go to **Sales Invoices → New Sale** to save.")
                except Exception as e:
                    st.error(str(e))


def page_sales_orders():
    def save(data, lines, _id, u):
        return db.save_sales_order(data, lines, None, u)

    peek = st.session_state.get("so_page_tab") or "List"
    hlp.std_page_header(
        "Sales Orders",
        subtitle="List · New · Edit · Create Invoice",
        status="register" if peek == "List" else None,
        status_kind="shell",
    )

    def _open_so_from_list(row):
        txn.reselect_transaction_picker("so_edit", int(row["id"]))
        st.session_state["so_open_tab"] = "edit"
        st.session_state.pop("SO_edit_loaded", None)

    _so_tab = hlp.sticky_page_tabs(
        ["List", "New", "Edit / Delete", "Create Invoice"],
        "so_page_tab",
        open_alias_key="so_open_tab",
    )

    items = {f"{r['code']} - {r['name']} ({r.get('stock_qty',0)})": r for r in db.get_items(active_only=True)}
    tax_rates = db.get_tax_rates()
    default_tax = db.default_tax_rate_id()
    cust_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}

    if _so_tab == "List":
        txn.sales_order_register_list(open_handler=_open_so_from_list)

    elif _so_tab == "New":
        if not cust_opts or not items:
            st.warning("Add master data first.")
        else:
            open_qt = db.get_quotations_for_conversion()
            if open_qt:
                st.markdown("**Optional — load from Quotation**")
                qt_opts = {f"{q['document_no']} — {q['customer_name']}": q["id"] for q in open_qt}
                c1, c2 = st.columns([3, 1])
                qt_lbl = c1.selectbox("Quotation", ["— None —"] + list(qt_opts.keys()), key="so_from_qt")
                if c2.button("Load Quote", key="so_load_qt") and qt_lbl != "— None —":
                    try:
                        hlp.prime_sales_order_from_quotation(qt_opts[qt_lbl])
                        ff.action_done("Quotation lines loaded.")
                    except Exception as e:
                        st.error(str(e))
                st.divider()
            with st.form("new_SO"):
                doc_no = st.text_input("Document No", db.peek_document("SO"))
                cust_labels, blank = hlp.options_with_blank(cust_opts.keys())
                party = st.selectbox("Customer", cust_labels)
                doc_date = st.date_input("Date", value=date.today())
                dispatch_town = st.text_input(
                    "Dispatch town / destination",
                    placeholder="e.g. BADIN — shown on dispatch planning",
                )
                notes = st.text_input("Notes")
                go = st.form_submit_button("Continue to Lines")
            if go:
                if not hlp.require_selected("customer", party, blank):
                    pass
                else:
                    st.session_state["SO_hdr"] = {
                        "document_no": doc_no, "party_id": cust_opts[party],
                        "date": str(doc_date), "notes": notes,
                        "dispatch_town": (dispatch_town or "").strip() or None,
                        "discount_pct": 0, "tax_rate_id": default_tax,
                        "quotation_id": st.session_state.get("SO_quotation_id"),
                    }
                    if "SO_lines" not in st.session_state:
                        st.session_state["SO_lines"] = [{"product_id": None, "quantity": 1, "rate": 0, "amount": 0}]
            if "SO_hdr" in st.session_state:
                hdr = st.session_state["SO_hdr"]
                if st.session_state.get("SO_quotation_id"):
                    st.info(f"From quotation ID {st.session_state['SO_quotation_id']}")
                if hdr.get("dispatch_town"):
                    st.caption(f"Dispatch town: **{hdr['dispatch_town']}**")
                raw_lines, _ = _line_editor(items, "SO", True)
                tax_lines = [
                    {"item_id": l["product_id"], "quantity": l["quantity"], "rate": l["rate"], "amount": l["amount"]}
                    for l in raw_lines
                ]
                tax_hdr, _totals = hlp.invoice_tax_form("SO_tax", tax_lines, hdr)
                hdr.update({k: tax_hdr[k] for k in ("discount_pct", "tax_rate_id", "tax_inclusive") if k in tax_hdr})
                data = {
                    "document_no": hdr["document_no"], "order_date": hdr["date"], "customer_id": hdr["party_id"],
                    "discount_pct": hdr.get("discount_pct", 0), "tax_rate_id": hdr.get("tax_rate_id"),
                    "tax_inclusive": hdr.get("tax_inclusive", 0), "notes": hdr.get("notes"),
                    "dispatch_town": hdr.get("dispatch_town"),
                    "quotation_id": hdr.get("quotation_id") or st.session_state.get("SO_quotation_id"),
                }
                if st.button("Save Sales Order", key="save_SO"):
                    if raw_lines:
                        try:
                            save(data, raw_lines, None, uid())
                            for k in ["SO_hdr", "SO_lines", "SO_quotation_id"]:
                                st.session_state.pop(k, None)
                            ff.action_done("Sales order saved.")
                        except Exception as e:
                            st.error(str(e))
                    else:
                        st.error("Add at least one line item.")

    elif _so_tab == "Edit / Delete":
        so_id, _ = txn.document_picker(
            "so_edit", db.search_sales_orders,
            lambda r: hlp.sales_order_picker_label(r, show_total=False),
            "Customer", cust_opts, "customer_id",
        )
        if not so_id:
            st.info("Search and select a sales order to edit — or use **Open** on the List.")
        else:
            order = db.get_sales_order(so_id)
            if not order:
                st.warning("Sales order not found.")
            elif not cust_opts:
                st.warning("Add customers first.")
            else:
                # Seed edit session when a different order is selected
                if st.session_state.get("SO_edit_loaded") != so_id:
                    ff.clear_session_prefix("SO_edit")
                    st.session_state["SO_edit_loaded"] = so_id
                    st.session_state["SO_edit_lines"] = [
                        {
                            "product_id": it["product_id"],
                            "item_id": it["product_id"],
                            "quantity": float(it.get("quantity") or 0),
                            "rate": float(it.get("rate") or 0),
                            "discount_pct": float(it.get("discount_pct") or 0),
                            "amount": float(it.get("amount") or 0),
                            "delivered_qty": float(it.get("delivered_qty") or 0),
                            "_disc_locked": True,
                        }
                        for it in (order.get("items") or [])
                    ] or [{"product_id": None, "quantity": 1, "rate": 0, "discount_pct": 0, "amount": 0, "delivered_qty": 0}]

                st.markdown(
                    f"**Order:** {order.get('document_no') or '—'} · "
                    f"**Date:** {order.get('order_date') or '—'} · "
                    f"**Status:** {order.get('status') or 'open'}"
                )
                # Portal-linked: allow reject + notify distributor from Sales Orders
                portal_oid = order.get("portal_order_id")
                if not portal_oid and order.get("source_channel") == "portal":
                    try:
                        from database import get_connection
                        with get_connection() as conn:
                            prow = conn.execute(
                                "SELECT id FROM portal_orders WHERE sales_order_id=? LIMIT 1",
                                (so_id,),
                            ).fetchone()
                            portal_oid = prow[0] if prow else None
                    except Exception:
                        portal_oid = None
                if portal_oid:
                    st.info(
                        f"Linked distributor portal order #{portal_oid}. "
                        "Rejecting here notifies the customer and cancels this SO."
                    )
                    rej = st.text_area(
                        "Rejection reason (notify distributor)",
                        key=f"so_portal_rej_{so_id}",
                        height=70,
                        placeholder="Required to reject…",
                    )
                    if st.button("Reject portal order & notify", key=f"so_portal_rej_btn_{so_id}"):
                        try:
                            from erp_core import portal_service as ps
                            ps.reject_portal_order(int(portal_oid), rej, user_id=uid())
                            st.session_state.pop("SO_edit_loaded", None)
                            ff.clear_session_prefix("SO_edit")
                            ff.action_done("Order rejected — distributor notified.")
                        except Exception as e:
                            st.error(str(e))

                from erp_ui.document_print import document_print_toolbar
                document_print_toolbar("Sales Order", so_id, key_prefix=f"so_print_{so_id}")

                cust_labels = list(cust_opts.keys())
                cur_cid = int(order.get("customer_id") or 0)
                default_lbl = next(
                    (k for k, v in cust_opts.items() if int(v) == cur_cid),
                    cust_labels[0],
                )
                # Keyed by order id so switching orders resets the customer picker
                party_lbl = st.selectbox(
                    "Customer",
                    cust_labels,
                    index=cust_labels.index(default_lbl) if default_lbl in cust_labels else 0,
                    key=f"so_edit_cust_{so_id}",
                )
                new_customer_id = cust_opts[party_lbl]
                if int(new_customer_id) != cur_cid:
                    st.info(
                        f"Customer will change from **{order.get('customer_name') or '—'}** "
                        f"to **{party_lbl.split(' - ', 1)[-1]}** when you save."
                    )

                c1, c2 = st.columns(2)
                try:
                    od = date.fromisoformat(str(order.get("order_date") or "")[:10])
                except Exception:
                    od = date.today()
                new_date = c1.date_input("Order Date", value=od, key=f"so_edit_date_{so_id}")
                new_town = c2.text_input(
                    "Dispatch town",
                    value=order.get("dispatch_town") or "",
                    key=f"so_edit_town_{so_id}",
                )
                new_notes = st.text_input(
                    "Notes", value=order.get("notes") or "", key=f"so_edit_notes_{so_id}",
                )
                status_opts = ["open", "partial", "closed", "cancelled"]
                cur_status = (order.get("status") or "open").lower()
                if cur_status not in status_opts:
                    status_opts = [cur_status] + status_opts
                new_status = st.selectbox(
                    "Status",
                    status_opts,
                    index=status_opts.index(cur_status) if cur_status in status_opts else 0,
                    key=f"so_edit_status_{so_id}",
                )

                raw_lines, _ = hlp.line_items_editor(
                    items, "SO_edit", show_weight=True, party_id=new_customer_id,
                )
                # Preserve delivered_qty by product from original order
                delivered_by_pid = {
                    int(it["product_id"]): float(it.get("delivered_qty") or 0)
                    for it in (order.get("items") or [])
                }
                save_lines = []
                for ln in raw_lines:
                    pid = ln.get("product_id") or ln.get("item_id")
                    row = dict(ln)
                    row["delivered_qty"] = delivered_by_pid.get(int(pid), float(ln.get("delivered_qty") or 0))
                    save_lines.append(row)

                b1, b2, b3, b4 = st.columns(4)
                if b1.button("Update Sales Order", type="primary", key="so_edit_save"):
                    if not save_lines:
                        st.error("Add at least one line item.")
                    else:
                        try:
                            data = {
                                "document_no": order["document_no"],
                                "customer_id": new_customer_id,
                                "order_date": str(new_date),
                                "notes": new_notes,
                                "dispatch_town": (new_town or "").strip() or None,
                                "status": new_status,
                                "discount_pct": float(order.get("discount") or order.get("discount_pct") or 0),
                                "tax_rate_id": order.get("tax_rate_id"),
                                "warehouse_id": order.get("warehouse_id"),
                                "quotation_id": order.get("quotation_id"),
                            }
                            db.save_sales_order(data, save_lines, so_id, uid())
                            st.session_state.pop("SO_edit_loaded", None)
                            ff.clear_session_prefix("SO_edit")
                            ff.action_done(
                                f"Sales order **{order['document_no']}** updated"
                                + (
                                    f" — customer set to **{party_lbl.split(' - ', 1)[-1]}**"
                                    if int(new_customer_id) != cur_cid else ""
                                )
                                + "."
                            )
                        except Exception as e:
                            st.error(str(e))
                if b2.button("Delete Sales Order", key="so_edit_del"):
                    try:
                        db.delete_sales_order(so_id, uid())
                        st.session_state.pop("SO_edit_loaded", None)
                        ff.clear_session_prefix("SO_edit")
                        ff.action_done(f"Sales order **{order['document_no']}** deleted.")
                    except Exception as e:
                        st.error(str(e))
                if b3.button("Reload from database", key="so_edit_reload"):
                    st.session_state.pop("SO_edit_loaded", None)
                    ff.clear_session_prefix("SO_edit")
                    st.rerun()
                pending_so = sum(
                    max(float(it.get("quantity") or 0) - float(it.get("delivered_qty") or 0), 0)
                    for it in (order.get("items") or [])
                )
                can_abandon = pending_so > 0.0001 and cur_status in ("open", "partial")
                if b4.button(
                    "Abandon remaining qty",
                    key="so_edit_abandon",
                    disabled=not can_abandon,
                    help="Mark closed — remaining will not be invoiced",
                ):
                    try:
                        db.abandon_sales_order_remaining(so_id, "", uid())
                        st.session_state.pop("SO_edit_loaded", None)
                        ff.clear_session_prefix("SO_edit")
                        ff.action_done(
                            f"Sales order **{order['document_no']}** closed — remaining qty abandoned."
                        )
                    except Exception as e:
                        st.error(str(e))

    elif _so_tab == "Create Invoice":
        open_orders = db.get_sales_orders_for_invoice()
        if not open_orders:
            st.info("No open sales orders with pending quantity.")
        else:
            st.markdown("Select an order to start a sales invoice (lines pre-filled).")
            so_opts = {
                hlp.sales_order_picker_label(o, show_pending=True, show_total=False): o["id"]
                for o in open_orders
            }
            so_lbl = st.selectbox("Sales Order", list(so_opts.keys()), key="so_inv_pick")
            if st.button("Load into Sales Invoice", type="primary", key="so_to_inv"):
                try:
                    hlp.prime_sale_from_order(so_opts[so_lbl])
                    ff.action_done("Order loaded. Go to **Sales Invoices → New Sale** to link weight slip and save.")
                except Exception as e:
                    st.error(str(e))


def page_delivery_notes():
    hlp.std_page_header("Delivery Notes", status="register", status_kind="shell")

    def _dn_actions(row):
        linked = [gp for gp in db.get_gate_passes() if gp.get("delivery_note_id") == row["id"]]
        if linked:
            st.caption("Linked gate passes")
            render_dataframe_html_table(
                pd.DataFrame(linked)[["document_no", "pass_date", "sales_invoice_no", "status"]].rename(
                    columns={
                        "document_no": "Gate Pass",
                        "pass_date": "Date",
                        "sales_invoice_no": "Sales Invoice",
                        "status": "Status",
                    },
                ),
            )
        if row.get("status") != "posted" and st.button("Post Delivery Note", key=f"dn_post_{row['id']}"):
            try:
                db.post_delivery_note(row["id"], uid())
                ff.action_done("Posted")
            except Exception as e:
                st.error(str(e))

    txn.delivery_note_register_list(action_panel=_dn_actions)


def page_purchase_requisition():
    line_doc_page(
        "Purchase Requisition", db.get_purchase_requisitions,
        lambda h, l, i, u: db.save_purchase_requisition(
            {"document_no": h["document_no"], "req_date": h["date"], "notes": h.get("notes")}, l, None, u),
        None, "PRQ", "Department",
        lambda: {f"{r['code']} - {r['name']}": r["id"] for r in db.get_departments()},
        register_fn=txn.purchase_requisition_register_list,
    )


def page_purchase_orders():
    def save(data, lines, _id, u):
        return db.save_purchase_order(data, lines, None, u)

    peek = st.session_state.get("po_page_tab") or "List"
    hlp.std_page_header(
        "Purchase Orders",
        subtitle="List · New · Edit · Create Invoice",
        status="register" if peek == "List" else None,
        status_kind="shell",
    )
    _po_tab = hlp.sticky_page_tabs(
        ["List", "New", "Edit / Delete", "Create Invoice"],
        "po_page_tab",
    )

    items = {f"{r['code']} - {r['name']} ({r.get('stock_qty',0)})": r for r in db.get_items(active_only=True)}
    sup_opts = {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}

    if _po_tab == "List":
        txn.purchase_order_register_list()

    elif _po_tab == "New":
        if not sup_opts or not items:
            st.warning("Add master data first.")
        else:
            open_req = db.get_purchase_requisitions_for_conversion()
            if open_req:
                st.markdown("**Optional — load from Purchase Requisition**")
                rq_opts = {f"{r['document_no']} — Rs. {float(r.get('subtotal',0)):,.0f}": r["id"] for r in open_req}
                c1, c2 = st.columns([3, 1])
                rq_lbl = c1.selectbox("Requisition", ["— None —"] + list(rq_opts.keys()), key="po_from_rq")
                if c2.button("Load Requisition", key="po_load_rq") and rq_lbl != "— None —":
                    try:
                        hlp.prime_purchase_order_from_requisition(rq_opts[rq_lbl])
                        ff.action_done("Requisition lines loaded.")
                    except Exception as e:
                        st.error(str(e))
                st.divider()
            with st.form("new_PO"):
                doc_no = st.text_input("Document No", db.peek_document("PO"))
                sup_labels, blank = hlp.options_with_blank(sup_opts.keys())
                party = st.selectbox("Supplier", sup_labels)
                doc_date = st.date_input("Date", value=date.today())
                notes = st.text_input("Notes")
                go = st.form_submit_button("Continue to Lines")
            if go:
                if not hlp.require_selected("supplier", party, blank):
                    pass
                else:
                    st.session_state["PO_hdr"] = {
                        "document_no": doc_no, "party_id": sup_opts[party],
                        "date": str(doc_date), "notes": notes,
                        "discount_pct": 0, "tax_rate_id": db.get_tax_rates()[0]["id"] if db.get_tax_rates() else None,
                        "requisition_id": st.session_state.get("PO_requisition_id"),
                    }
                    if "PO_lines" not in st.session_state:
                        st.session_state["PO_lines"] = [{"product_id": None, "quantity": 1, "rate": 0, "amount": 0}]
            if "PO_hdr" in st.session_state:
                hdr = st.session_state["PO_hdr"]
                if st.session_state.get("PO_requisition_id"):
                    st.info(f"From requisition ID {st.session_state['PO_requisition_id']}")
                if not hdr.get("party_id") and sup_opts:
                    st.warning("**Supplier required** — requisition lines are loaded; select a supplier before saving.")
                    sup_labels, blank = hlp.options_with_blank(sup_opts.keys())
                    sup_pick = st.selectbox("Supplier *", sup_labels, key="PO_rq_sup")
                    if st.button("Apply Supplier", key="PO_apply_sup"):
                        if hlp.require_selected("supplier", sup_pick, blank):
                            st.session_state["PO_hdr"]["party_id"] = sup_opts[sup_pick]
                            st.rerun()
                elif hdr.get("party_id"):
                    sup_name = next((k for k, v in sup_opts.items() if v == hdr["party_id"]), "—")
                    st.caption(f"Supplier: **{sup_name}**")
                raw_lines, _ = _line_editor(items, "PO", True)
                tax_lines = [
                    {"item_id": l["product_id"], "quantity": l["quantity"], "rate": l["rate"], "amount": l["amount"]}
                    for l in raw_lines
                ]
                tax_hdr, _totals = hlp.invoice_tax_form("PO_tax", tax_lines, hdr)
                hdr.update({k: tax_hdr[k] for k in ("discount_pct", "tax_rate_id", "tax_inclusive") if k in tax_hdr})
                data = {
                    "document_no": hdr["document_no"], "order_date": hdr["date"], "supplier_id": hdr["party_id"],
                    "discount_pct": hdr.get("discount_pct", 0), "tax_rate_id": hdr.get("tax_rate_id"),
                    "tax_inclusive": hdr.get("tax_inclusive", 0), "notes": hdr.get("notes"),
                    "requisition_id": hdr.get("requisition_id") or st.session_state.get("PO_requisition_id"),
                }
                if st.button("Save Purchase Order", key="save_PO"):
                    if not hdr.get("party_id"):
                        st.error("Select a supplier before saving the purchase order.")
                    elif raw_lines:
                        try:
                            save(data, raw_lines, None, uid())
                            for k in ["PO_hdr", "PO_lines", "PO_requisition_id"]:
                                st.session_state.pop(k, None)
                            ff.action_done("Purchase order saved.")
                        except Exception as e:
                            st.error(str(e))
                    else:
                        st.error("Add at least one line item.")

    elif _po_tab == "Edit / Delete":
        _edit_picker("PO", lambda: sup_opts, None)

    elif _po_tab == "Create Invoice":
        open_pos = db.get_purchase_orders_for_invoice()
        if not open_pos:
            st.info("No open purchase orders with pending quantity.")
        else:
            po_opts = {
                f"{o['document_no']} — {o['supplier_name']} — pending {float(o['pending_qty']):,.0f} units": o["id"]
                for o in open_pos
            }
            po_lbl = st.selectbox("Purchase Order", list(po_opts.keys()), key="po_inv_pick")
            if st.button("Load into Purchase Invoice", type="primary", key="po_to_inv"):
                try:
                    hlp.prime_purchase_from_order(po_opts[po_lbl])
                    ff.action_done("Order loaded. Go to **Purchase Invoices → New Purchase** to link weight slip and save.")
                except Exception as e:
                    st.error(str(e))


def page_grn():
    hlp.std_page_header("GRN", title="Goods Receipt Notes", status="register", status_kind="shell")

    def _grn_actions(row):
        linked = [gp for gp in db.get_gate_passes() if gp.get("grn_id") == row["id"]]
        if linked:
            st.caption("Linked gate passes")
            from erp_ui.helpers import render_dataframe_html_table
            render_dataframe_html_table(
                pd.DataFrame(linked)[["document_no", "pass_date", "purchase_invoice_no", "status"]].rename(
                    columns={
                        "document_no": "Gate Pass",
                        "pass_date": "Date",
                        "purchase_invoice_no": "Purchase Invoice",
                        "status": "Status",
                    },
                ),
            )
        if row.get("status") != "posted" and st.button("Post GRN", key=f"grn_post_{row['id']}"):
            try:
                db.post_grn(row["id"], uid())
                ff.action_done("GRN posted — stock updated")
            except Exception as e:
                st.error(str(e))

    txn.grn_register_list(action_panel=_grn_actions)


def page_weight_slips():
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    hlp.std_page_header("Weight Slips", status="register", status_kind="shell")
    tab = sticky_page_tabs(["List", "New"], "ws_page_tab")
    if tab == "List":
        rows = db.get_weight_slips()
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
        else:
            st.info("No weight slips yet.")
    elif tab == "New":
        with st.form("ws"):
            vopts = {r["registration_no"]: r["id"] for r in db.get_vehicles()}
            ws_no = st.text_input("Slip No", value=db.peek_document("WS"))
            d = {"document_no": ws_no, "slip_date": str(st.date_input("Date", value=date.today())),
                 "vehicle_id": vopts.get(st.selectbox("Vehicle", list(vopts.keys()))) if vopts else None,
                 "driver_name": st.text_input("Driver"),
                 "first_weight": st.number_input("First Weight", 0.0),
                 "second_weight": st.number_input("Second Weight", 0.0),
                 "tare_weight": st.number_input("Tare Weight", 0.0),
                 "gross_weight": st.number_input("Gross Weight", 0.0),
                 "remarks": st.text_input("Remarks")}
            if st.form_submit_button("Save"):
                db.save_weight_slip(d, None, uid())
                ff.action_done("Saved")


def page_batch_stock():
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header("Batch Stock", status="register", status_kind="shell")
    rows = db.get_batch_stock()
    if rows:
        df = pd.DataFrame(rows)
        render_dataframe_html_table(df)
        export_df(df, "batch_stock")
    else:
        st.info("No batch stock.")


def page_bom():
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    hlp.std_page_header("BOM", title="BOM / Formula", status="register", status_kind="shell")
    tab = sticky_page_tabs(["List", "New BOM", "View / Approve"], "v3_bom_tab")
    items = {f"{r['code']} - {r['name']}": r for r in db.get_items()}
    if tab == "List":
        rows = db.get_bom_list()
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
        else:
            st.info("No BOMs yet.")
    elif tab == "New BOM":
        with st.form("bom_h"):
            fp = st.selectbox("Finished Product", list(items.keys()))
            ver = st.text_input("Version", "1.0")
            out_qty = st.number_input("Standard Output Qty", 1.0)
            if st.form_submit_button("Next"):
                st.session_state["bom_hdr"] = {"finished_product_id": items[fp]["id"], "version_no": ver,
                                               "standard_output_qty": out_qty}
                st.session_state["bom_lines"] = [{"raw_product_id": None, "quantity": 1, "standard_cost": 0}]
        if "bom_hdr" in st.session_state:
            lines, _ = _line_editor({k: v for k, v in items.items()}, "boml", False)
            raw_lines = [{"raw_product_id": l["product_id"], "quantity": l["quantity"],
                          "standard_cost": l["rate"], "line_cost": l["amount"]} for l in lines]
            if st.button("Save BOM") and raw_lines:
                db.save_bom(st.session_state["bom_hdr"], raw_lines, None, uid())
                ff.action_done("BOM saved")
    elif tab == "View / Approve":
        rows = db.get_bom_list()
        if not rows:
            st.info("No BOMs yet.")
            return
        sel = st.selectbox("BOM", [f"{r['document_no']} - {r['finished_product_name']}" for r in rows])
        bid = next(r["id"] for r in rows if r["document_no"] in sel)
        b = db.get_bom(bid)
        if b:
            st.write(f"Status: **{b['status']}** | Cost: **{fmt(b['standard_cost'])}**")
            render_dataframe_html_table(pd.DataFrame(b["lines"]))
            if b["status"] != "approved" and st.button("Approve BOM"):
                db.approve_bom(bid, uid()); st.rerun()
            if st.button("Copy to New Version"):
                db.copy_bom(bid, str(float(b["version_no"]) + 0.1), uid()); st.rerun()


def page_production():
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    hlp.std_page_header("Production Orders", status="register", status_kind="shell")
    tab = sticky_page_tabs(["List", "New Order", "Process"], "v3_prod_tab")
    boms = {f"{b['document_no']} - {b['finished_product_name']}": b for b in db.get_bom_list() if b["status"] == "approved"}
    if tab == "List":
        rows = db.get_production_orders()
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
        else:
            st.info("No production orders yet.")
    elif tab == "New Order":
        if not boms:
            st.warning("Approve a BOM first.")
        else:
            with st.form("prod"):
                bl = st.selectbox("BOM", list(boms.keys()))
                b = boms[bl]
                pq = st.number_input("Planned Qty", 1.0)
                od = st.date_input("Date", value=date.today())
                if st.form_submit_button("Create"):
                    db.save_production_order({"order_date": str(od), "bom_id": b["id"],
                                              "finished_product_id": b["finished_product_id"],
                                              "planned_qty": pq}, uid())
                    st.rerun()
    elif tab == "Process":
        rows = db.get_production_orders()
        if not rows:
            st.info("No production orders yet.")
            return
        sel = st.selectbox("Order", [f"{r['document_no']} - {r['status']}" for r in rows])
        po = next(r for r in rows if r["document_no"] in sel)
        reqs = db.calc_bom_requirements(po["bom_id"], po["planned_qty"])
        if reqs:
            st.subheader("Material Requirements")
            render_dataframe_html_table(pd.DataFrame(reqs))
        if po["status"] == "draft":
            shortages = db.production_material_shortages(po["id"])
            allow_neg = db.get_setting("allow_negative_stock") == "1"
            confirm_key = f"prod_issue_confirm_v3_{po['id']}"
            if shortages:
                st.warning("Insufficient stock — confirm below to issue anyway.")
                render_dataframe_html_table(pd.DataFrame(shortages))
            if shortages and not allow_neg:
                if st.session_state.get(confirm_key):
                    if st.button("Confirm issue (short stock)", type="primary", key="prod_v3_issue_yes"):
                        try:
                            db.issue_production_materials(po["id"], uid(), allow_insufficient=True)
                            st.session_state.pop(confirm_key, None)
                            ff.action_done("Issued")
                        except Exception as e:
                            st.error(str(e))
                    if st.button("Cancel", key="prod_v3_issue_no"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                elif st.button("Issue Materials", key="prod_v3_issue"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            elif st.button("Issue Materials", key="prod_v3_issue_go"):
                try:
                    db.issue_production_materials(po["id"], uid()); ff.action_done("Issued")
                except Exception as e:
                    st.error(str(e))
        if po["status"] == "issued":
            aq = st.number_input("Actual Qty", value=float(po["planned_qty"]))
            wq = st.number_input("Wastage", 0.0)
            qc = st.selectbox("QC", ["Pending", "Passed", "Failed"])
            if st.button("Complete Production"):
                db.complete_production(po["id"], aq, wq, qc, uid()); ff.action_done("Completed")
        if po["status"] == "completed":
            st.success(f"Completed — QC **{po.get('qc_status')}**, output **{float(po.get('actual_qty') or 0):,.4f}**")
            rb_reason = st.text_input("Rollback reason *", key=f"prod_v3_rb_{po['id']}")
            rb_force = st.checkbox("Confirm rollback (allow negative stock)", key=f"prod_v3_rb_force_{po['id']}")
            if st.button("Rollback QC / Reopen", key=f"prod_v3_rb_btn_{po['id']}"):
                try:
                    db.rollback_production_completion(po["id"], uid(), rb_reason, allow_force=rb_force)
                    ff.action_done("Reopened for correction.")
                except Exception as e:
                    st.error(str(e))


def page_journal():
    from erp_ui.document_print import document_print_toolbar
    from erp_ui.finance_attachments import slip_attachment_workspace, preset_from_voucher
    from erp_ui.helpers import sticky_page_tabs, render_dataframe_html_table

    peek = st.session_state.get("jv_page_tab") or "List"
    hlp.std_page_header(
        "Journal Voucher",
        subtitle="List · New · Edit · Print · Slips",
        status="register" if peek == "List" else None,
        status_kind="shell",
    )
    st.caption(
        "Manual GL journals — transfer or adjust **Chart of Accounts** balances "
        "(Dr one account, Cr another). Debits must equal credits. "
        "For customer/supplier balance moves use **Party Transfer**. "
        "For cash/bank use Cash Book / Receipt / Payment screens."
    )
    jv_tab = sticky_page_tabs(["List", "New / Post", "Edit / Delete", "Print Voucher", "Slips"], "jv_page_tab")

    if jv_tab == "List":
        c1, c2, c3 = st.columns([3, 1, 1])
        q = c1.text_input(
            "Search",
            key="jv_list_q",
            placeholder="Voucher no or description…",
        )
        page_size = c2.selectbox("Rows", [25, 50, 100], index=0, key="jv_list_ps")
        page = c3.number_input("Page", min_value=1, value=1, step=1, key="jv_list_pg")
        result = db.search_journal_vouchers(
            q=(q or "").strip() or None, page=int(page), page_size=int(page_size),
        )
        rows = result.get("items") or []
        total = int(result.get("total") or 0)
        if rows:
            list_df = pd.DataFrame([{
                "Document": r.get("document_no"),
                "Date / Time": hlp.fmt_datetime_from_record(r, "voucher_date"),
                "Description": (r.get("description") or "")[:80],
                "Debit": r.get("total_debit"),
                "Credit": r.get("total_credit"),
                "Status": r.get("status") or "",
            } for r in rows])
            posted_n = sum(1 for r in rows if str(r.get("status") or "").lower() == "posted")
            draft_n = len(rows) - posted_n
            k1, k2, k3, k4 = st.columns(4, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Vouchers</p>"
                f"<p class='txn-kpi-val'>{total:,}</p></div>",
                unsafe_allow_html=True,
            )
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>On page</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            k3.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Posted</p>"
                f"<p class='txn-kpi-val'>{posted_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            k4.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Draft</p>"
                f"<p class='txn-kpi-val'>{draft_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            render_dataframe_html_table(list_df)
            st.caption(f"Showing **{len(rows)}** of **{total:,}** journal voucher(s)")
        else:
            st.info("No journal vouchers match this search." if q else "No journal vouchers yet.")

    elif jv_tab == "New / Post":
        _jv_new_post_tab()

    elif jv_tab == "Edit / Delete":
        _jv_edit_delete_tab()

    elif jv_tab == "Print Voucher":
        pq = st.text_input("Find voucher to print", key="jv_print_q", placeholder="Voucher no…")
        pres = db.search_journal_vouchers(
            q=(pq or "").strip() or None, page=1, page_size=40,
        )
        prows = pres.get("items") or []
        if prows:
            labels = {
                str(r["id"]): (
                    f"{r.get('document_no','')} — {r.get('voucher_date','')} — "
                    f"{(r.get('description') or '')[:50]}"
                )
                for r in prows
            }
            sel = st.selectbox(
                "Select voucher",
                list(labels.keys()),
                format_func=lambda k: labels[k],
                key="jv_print_sel",
            )
            if sel:
                document_print_toolbar("Journal Voucher", int(sel), key_prefix="jv_print")
            if (pres.get("total") or 0) > len(prows):
                st.caption(f"Showing latest {len(prows)} of {pres['total']:,} — refine search to find older vouchers.")
        else:
            st.info("No journal vouchers to print.")

    elif jv_tab == "Slips":
        preset = st.session_state.get("jv_slip_preset")
        slip_attachment_workspace(["journal_voucher"], "jv_slips", preset=preset, title="Journal voucher slips")


def _jv_line_editor(lines, acct_records, key_prefix):
    """Shared Dr/Cr line editor for new and edit JV flows. Mutates ``lines`` in place."""
    st.markdown(
        "**Lines** — **Dr** = receiving account, **Cr** = giving account. "
        "Search by account code/name on each line. "
        "Entering **Dr** clears **Cr** on that line (and vice versa)."
    )
    with hlp.form_compact(f"{key_prefix}_jv"):
        for i, ln in enumerate(list(lines)):
            with hlp.form_line(f"{key_prefix}_jv_ln{i}"):
                st.markdown(f"**Line {i + 1}**")
                cur_id = ln.get("account_id")
                preferred = [a for a in acct_records if a.get("id") == cur_id] if cur_id else []
                pool = preferred + [a for a in acct_records if a.get("id") != cur_id]

                c_acct, c_dr, c_cr, c_x = st.columns([4.2, 1.05, 1.05, 0.4])
                with c_acct:
                    _, aid, _ = hlp.smart_select(
                        "Account",
                        pool,
                        key=f"{key_prefix}_acct_{i}",
                        placeholder="Code or name…",
                        max_results=80,
                        default_id=cur_id,
                        layout="row",
                    )
                if aid:
                    lines[i]["account_id"] = aid

                dr_key = f"{key_prefix}_dr_{i}"
                cr_key = f"{key_prefix}_cr_{i}"
                side_key = f"{dr_key}__{cr_key}__last_side"

                def _on_dr(dk=dr_key, ck=cr_key, sk=side_key):
                    v = hlp.parse_money(st.session_state.get(dk), 0.0)
                    st.session_state[sk] = "dr"
                    if v > 0.0005:
                        hlp.set_money_widget_value(ck, 0.0)

                def _on_cr(dk=dr_key, ck=cr_key, sk=side_key):
                    v = hlp.parse_money(st.session_state.get(ck), 0.0)
                    st.session_state[sk] = "cr"
                    if v > 0.0005:
                        hlp.set_money_widget_value(dk, 0.0)

                with c_dr:
                    lines[i]["debit"] = hlp.money_input(
                        "Dr",
                        value=float(ln.get("debit", 0) or 0),
                        min_value=0.0,
                        key=dr_key,
                        help="Debit — Credit on this line clears to 0",
                        on_change=_on_dr,
                    )
                with c_cr:
                    lines[i]["credit"] = hlp.money_input(
                        "Cr",
                        value=float(ln.get("credit", 0) or 0),
                        min_value=0.0,
                        key=cr_key,
                        help="Credit — Debit on this line clears to 0",
                        on_change=_on_cr,
                    )

                dr_v = float(lines[i].get("debit") or 0)
                cr_v = float(lines[i].get("credit") or 0)
                if dr_v > 0.0005 and cr_v > 0.0005:
                    if st.session_state.get(side_key) == "cr":
                        hlp.set_money_widget_value(dr_key, 0.0)
                        lines[i]["debit"] = 0.0
                    else:
                        hlp.set_money_widget_value(cr_key, 0.0)
                        lines[i]["credit"] = 0.0

                if c_x.button("✕", key=f"{key_prefix}_x_{i}", help="Remove line") and len(lines) > 2:
                    lines.pop(i)
                    st.rerun()

                c_narr, _ = st.columns([5.3, 1.4])
                with c_narr:
                    lines[i]["description"] = st.text_input(
                        "Narration",
                        value=ln.get("description") or "",
                        key=f"{key_prefix}_narr_{i}",
                        placeholder="Optional — blank uses voucher Description on print / post",
                    )

        tot_dr = sum(float(l.get("debit") or 0) for l in lines)
        tot_cr = sum(float(l.get("credit") or 0) for l in lines)
        bal = abs(tot_dr - tot_cr) < 0.01 and tot_dr > 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Dr", hlp.fmt_money(tot_dr))
        m2.metric("Total Cr", hlp.fmt_money(tot_cr))
        m3.metric("Difference", hlp.fmt_money(tot_dr - tot_cr))
    return bal, tot_dr, tot_cr


def _jv_new_post_tab():
    from erp_ui.document_print import document_print_toolbar
    from erp_ui.finance_attachments import preset_from_voucher

    acct_records = db.get_accounts(active_only=True) if hasattr(db, "get_accounts") else db.get_accounts()
    if not acct_records:
        st.warning("Add accounts in Chart of Accounts first.")
        return
    with hlp.form_compact("jv_hdr"):
        with st.form("jv_hdr_form"):
            c1, c2 = st.columns([1.2, 3.2])
            vdate = c1.date_input("Date", value=date.today())
            desc = c2.text_input(
                "Description",
                placeholder="e.g. Transfer from ledger A to ledger B",
            )
            if st.form_submit_button("Start voucher (2 lines)"):
                st.session_state["jv_draft"] = {
                    "voucher_date": str(vdate),
                    "description": desc,
                    "lines": [
                        {"account_id": acct_records[0]["id"], "debit": 0.0, "credit": 0.0},
                        {
                            "account_id": acct_records[1]["id"] if len(acct_records) > 1 else acct_records[0]["id"],
                            "debit": 0.0,
                            "credit": 0.0,
                        },
                    ],
                }
    if "jv_draft" in st.session_state:
        lines = st.session_state["jv_draft"]["lines"]
        bal, _, _ = _jv_line_editor(lines, acct_records, "jv_new")
        b1, b2, b3 = st.columns(3)
        if b1.button("Add line", key="jv_add_line"):
            lines.append({"account_id": acct_records[0]["id"], "debit": 0.0, "credit": 0.0})
            st.rerun()
        if b2.button("Clear draft", key="jv_clear"):
            del st.session_state["jv_draft"]
            st.rerun()
        if b3.button("Save & Post JV", type="primary", key="jv_save", disabled=not bal):
            try:
                vid = db.save_journal_voucher(st.session_state["jv_draft"], lines, None, uid())
                db.post_journal_voucher(vid, uid())
                del st.session_state["jv_draft"]
                st.session_state["last_jv_print"] = vid
                st.session_state["jv_slip_preset"] = preset_from_voucher("journal_voucher", vid)
                ff.action_done("Posted")
            except Exception as e:
                st.error(str(e))
        if not bal:
            st.caption("Enter matching Dr and Cr amounts before posting (difference must be 0).")
    if st.session_state.get("last_jv_print"):
        vid = st.session_state.pop("last_jv_print")
        document_print_toolbar("Journal Voucher", vid, key_prefix="jv_new_print")
        st.caption("Attach supporting documents in **Slips** tab.")


def _jv_edit_delete_tab():
    from erp_ui.document_print import document_print_toolbar

    # Include inactive so saved JV accounts still appear when editing
    acct_records = db.get_accounts() if hasattr(db, "get_accounts") else []
    if not acct_records:
        st.warning("Add accounts in Chart of Accounts first.")
        return

    st.caption("Edit or delete any journal voucher (draft or posted). Posted vouchers are unposted, updated, then re-posted.")
    cq = st.text_input("Find voucher", key="jv_edit_q", placeholder="Voucher no or description…")
    cres = db.search_journal_vouchers(q=(cq or "").strip() or None, page=1, page_size=50)
    crows = cres.get("items") or []
    if not crows:
        st.info("No journal vouchers found.")
        return

    labels = {
        int(r["id"]): (
            f"{r.get('document_no','')} — {r.get('voucher_date','')} — "
            f"{(r.get('description') or '')[:40]} — {(r.get('status') or '').title()} — "
            f"{hlp.fmt_money(r.get('total_debit'))}"
        )
        for r in crows
    }
    sel_id = st.selectbox(
        "Select voucher to edit",
        list(labels.keys()),
        format_func=lambda i: labels.get(i, str(i)),
        key="jv_edit_sel",
    )
    if not sel_id:
        return

    # Load into session when selection changes
    edit_key = "jv_edit_draft"
    if st.session_state.get("jv_edit_loaded_id") != sel_id:
        jv = db.get_journal_voucher(sel_id)
        if not jv:
            st.error("Voucher not found.")
            return
        # Clear stale account/search widgets so saved accounts show (not CASH default)
        for k in list(st.session_state.keys()):
            if (
                (
                    k.startswith("jv_edit_acct_")
                    and (k.endswith("_sel") or k.endswith("_srch"))
                )
                or k.startswith("sel_jv_edit_acct_")
                or k.startswith("srch_jv_edit_acct_")
                or k.startswith("jv_edit_dr_")
                or k.startswith("jv_edit_cr_")
                or k.startswith("jv_edit_date")
                or k.startswith("jv_edit_desc")
                or k.startswith("jv_edit_narr_")
            ):
                del st.session_state[k]
        st.session_state[edit_key] = {
            "id": sel_id,
            "document_no": jv.get("document_no"),
            "voucher_date": jv.get("voucher_date"),
            "description": jv.get("description") or "",
            "status": jv.get("status") or "draft",
            "lines": [
                {
                    "account_id": ln.get("account_id"),
                    "debit": float(ln.get("debit") or 0),
                    "credit": float(ln.get("credit") or 0),
                    "description": (ln.get("description") or "").strip()
                    or (jv.get("description") or "").strip(),
                }
                for ln in (jv.get("lines") or [])
            ] or [
                {"account_id": acct_records[0]["id"], "debit": 0.0, "credit": 0.0},
                {"account_id": acct_records[-1]["id"], "debit": 0.0, "credit": 0.0},
            ],
        }
        st.session_state["jv_edit_loaded_id"] = sel_id
        st.rerun()

    draft = st.session_state.get(edit_key)
    if not draft:
        return

    st.info(
        f"**{draft.get('document_no')}** · Status: **{(draft.get('status') or 'draft').replace('_', ' ').title()}**"
    )
    try:
        default_date = date.fromisoformat(str(draft.get("voucher_date") or date.today())[:10])
    except ValueError:
        default_date = date.today()
    with hlp.form_compact("jv_edit_hdr"):
        c1, c2 = st.columns([1.2, 3.2])
        vdate = c1.date_input("Date", value=default_date, key="jv_edit_date")
        desc = c2.text_input("Description", value=draft.get("description") or "", key="jv_edit_desc")
    draft["voucher_date"] = str(vdate)
    draft["description"] = desc

    lines = draft["lines"]
    bal, _, _ = _jv_line_editor(lines, acct_records, "jv_edit")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Add line", key="jv_edit_add"):
        lines.append({"account_id": acct_records[0]["id"], "debit": 0.0, "credit": 0.0})
        st.rerun()
    if b2.button("Save & Repost", type="primary", key="jv_edit_save", disabled=not bal):
        try:
            db.update_journal_voucher(
                draft["id"],
                {
                    "document_no": draft.get("document_no"),
                    "voucher_date": draft["voucher_date"],
                    "description": draft.get("description"),
                    "status": "draft",
                },
                lines,
                uid(),
                repost=True,
            )
            st.session_state.pop(edit_key, None)
            st.session_state.pop("jv_edit_loaded_id", None)
            st.session_state["last_jv_edit_print"] = draft["id"]
            ff.action_done(f"Updated and re-posted **{draft.get('document_no')}**.")
        except Exception as e:
            st.error(str(e))
    if b3.button("Unpost only (keep draft)", key="jv_edit_unpost"):
        try:
            db.reverse_journal_voucher(draft["id"], uid(), reason="manual unpost")
            st.session_state.pop(edit_key, None)
            st.session_state.pop("jv_edit_loaded_id", None)
            ff.action_done(f"Unposted **{draft.get('document_no')}** — now draft.")
        except Exception as e:
            st.error(str(e))
    if b4.button("Delete voucher", key="jv_edit_del"):
        try:
            db.delete_journal_voucher(draft["id"], uid(), reason="user delete")
            st.session_state.pop(edit_key, None)
            st.session_state.pop("jv_edit_loaded_id", None)
            ff.action_done(f"Deleted **{draft.get('document_no')}**.")
        except Exception as e:
            st.error(str(e))
    if not bal:
        st.caption("Dr and Cr must balance before Save & Repost.")

    if st.session_state.get("last_jv_edit_print"):
        vid = st.session_state.pop("last_jv_edit_print")
        document_print_toolbar("Journal Voucher", vid, key_prefix="jv_edit_print")


def page_general_ledger():
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header("General Ledger", status="register", status_kind="shell")
    st.caption(
        "All GL lines for the period. For Opening / Debit / Credit / Closing on **one** account, "
        "use **Finance → Account Ledger** (or Reports → Account Ledger)."
    )
    from erp_ui.report_grouping import finance_group_filters
    account_group_id, _ = finance_group_filters("gl")
    accts = db.get_accounts()
    sel = st.selectbox("Account (All)", ["All"] + [f"{a['code']} - {a['name']}" for a in accts])
    c1, c2 = st.columns(2)
    fd, td = c1.date_input("From", value=None), c2.date_input("To", value=None)
    if not sel or sel == "All":
        aid = None
    else:
        aid = next((a["id"] for a in accts if str(sel).startswith(str(a["code"]))), None)
    rows = db.get_general_ledger(
        aid, str(fd) if fd else None, str(td) if td else None, account_group_id=account_group_id,
    )
    if rows:
        df = pd.DataFrame(rows)
        total_deb = float(pd.to_numeric(df["debit"], errors="coerce").fillna(0).sum()) if "debit" in df.columns else 0.0
        total_cred = float(pd.to_numeric(df["credit"], errors="coerce").fillna(0).sum()) if "credit" in df.columns else 0.0
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>GL Lines</p>"
            f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Debit</p>"
            f"<p class='txn-kpi-val'>{fmt(total_deb)}</p></div>",
            unsafe_allow_html=True,
        )
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Credit</p>"
            f"<p class='txn-kpi-val'>{fmt(total_cred)}</p></div>",
            unsafe_allow_html=True,
        )
        render_dataframe_html_table(df)
        export_df(df, "general_ledger")
    else:
        st.info("No GL entries for the selected filters.")


def page_trial_balance():
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header("Trial Balance", status="register", status_kind="shell")
    from erp_ui.report_grouping import finance_group_filters
    c1, c2 = st.columns(2)
    fd = c1.date_input("From", value=None, key="tb_fd")
    td = c2.date_input("To", value=None, key="tb_td")
    account_group_id, view_mode = finance_group_filters("tb")
    rows = db.get_trial_balance(
        str(fd) if fd else None, str(td) if td else None,
        account_group_id=account_group_id, view_mode=view_mode,
    )
    if rows:
        df = pd.DataFrame(rows)
        total_deb = total_cred = 0.0
        for col in df.columns:
            cl = str(col).lower()
            if "debit" in cl:
                total_deb = float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
            if "credit" in cl:
                total_cred = float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Accounts</p>"
            f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Debit</p>"
            f"<p class='txn-kpi-val'>{fmt(total_deb)}</p></div>",
            unsafe_allow_html=True,
        )
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Credit</p>"
            f"<p class='txn-kpi-val'>{fmt(total_cred)}</p></div>",
            unsafe_allow_html=True,
        )
        render_dataframe_html_table(df)
        export_df(df, "trial_balance")


def page_balance_sheet():
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header("Balance Sheet", status="register", status_kind="shell")
    from erp_ui.report_grouping import finance_group_filters
    as_of = st.date_input("As at", value=date.today(), key="bs_asof")
    account_group_id, view_mode = finance_group_filters("bs")
    bs = db.get_balance_sheet(str(as_of), account_group_id=account_group_id, view_mode=view_mode)
    c1, c2, c3 = st.columns(3)
    c1.metric("Assets", fmt(bs["total_assets"]))
    c2.metric("Liabilities", fmt(bs["total_liabilities"]))
    c3.metric("Equity", fmt(bs["total_equity"]))
    render_dataframe_html_table(pd.DataFrame(bs["rows"]))


def page_tax_report():
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header("Tax Report", status="register", status_kind="shell")
    c1, c2 = st.columns(2)
    fd, td = c1.date_input("From", date(date.today().year, 1, 1)), c2.date_input("To", date.today())
    rows = db.get_tax_report(str(fd), str(td))
    if rows:
        df = pd.DataFrame(rows)
        render_dataframe_html_table(df)
        export_df(df, "tax_report")
    else:
        st.info("No tax data.")


def page_customer_outstanding():
    from erp_ui.helpers import render_dataframe_html_table

    hlp.std_page_header("Customer Outstanding", status="register", status_kind="shell")
    from erp_ui.report_grouping import party_group_filter, party_view_mode
    c1, c2 = st.columns(2)
    with c1:
        gid = party_group_filter("customer", "co")
    with c2:
        vm = party_view_mode("co")
    rows = db.get_customer_outstanding(customer_group_id=gid, view_mode=vm)
    if rows:
        df = pd.DataFrame(rows)
        tot = float(df["outstanding"].sum())
        k1, k2 = st.columns(2, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Customers</p>"
            f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Outstanding</p>"
            f"<p class='txn-kpi-val'>{fmt(tot)}</p></div>",
            unsafe_allow_html=True,
        )
        render_dataframe_html_table(df)


def page_customer_due_aging():
    hlp.std_page_header("Customer Due Aging", status="register", status_kind="shell")
    st.caption(
        "Net balance due by invoice age: 0-15, 16-30, 31-45, 46-60, 61-90, and Over 90 days. "
        "Dual-role parties (customer + supplier same code) are netted like Customer Outstanding. "
        "As-of date controls how old each unpaid amount is."
    )
    import db_reports as rpt_db
    from erp_ui.report_grouping import party_group_filter
    from erp_ui.report_print import prettify_columns
    from erp_ui.report_profiles import prepare_report_dataframe

    c1, c2, c3 = st.columns(3)
    with c1:
        as_of = st.date_input("As of date", value=date.today(), key="cda_as_of")
    with c2:
        gid = party_group_filter("customer", "cda")
    with c3:
        opts = {"All customers": None}
        opts.update(hlp.customer_opts(active_only=True))
        cust_sel = st.selectbox("Customer", list(opts.keys()), key="cda_cust")
        cid = opts.get(cust_sel)

    rows = rpt_db.get_customer_due_aging(
        str(as_of),
        customer_id=cid,
        customer_group_id=gid,
    )
    if not rows:
        st.info("No customer balances due for the selected filters.")
        return
    df = prepare_report_dataframe(pd.DataFrame(rows), "Customer Due Aging")
    view = prettify_columns(df)
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Customers</p>"
        f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Due</p>"
        f"<p class='txn-kpi-val'>{fmt(df['total_due'].sum())}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Over 90 Days</p>"
        f"<p class='txn-kpi-val'>{fmt(df['over_90'].sum())}</p></div>",
        unsafe_allow_html=True,
    )
    from erp_ui.helpers import render_dataframe_html_table
    render_dataframe_html_table(view)
    export_df(df, "customer_due_aging", "Customer Due Aging")


def page_supplier_outstanding():
    from erp_ui.helpers import render_dataframe_html_table
    from erp_ui.report_print import prettify_columns
    from erp_ui.report_profiles import prepare_report_dataframe

    hlp.std_page_header("Supplier Outstanding", status="register", status_kind="shell")
    st.caption(
        "Party-wise payables — balance due to each supplier. "
        "Dual-role parties (customer + supplier same code) are netted like the dashboard Payables total."
    )
    from erp_ui.report_grouping import party_group_filter, party_view_mode
    c1, c2 = st.columns(2)
    with c1:
        gid = party_group_filter("supplier", "so")
    with c2:
        vm = party_view_mode("so")
    rows = db.get_supplier_outstanding(supplier_group_id=gid, view_mode=vm)
    if not rows:
        st.info("No supplier payables for the selected filters.")
        return
    df = prepare_report_dataframe(pd.DataFrame(rows), "Supplier Outstanding")
    tot = float(df["outstanding"].sum())
    k1, k2 = st.columns(2, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Suppliers</p>"
        f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Outstanding</p>"
        f"<p class='txn-kpi-val'>{fmt(tot)}</p></div>",
        unsafe_allow_html=True,
    )
    render_dataframe_html_table(prettify_columns(df))
    export_df(df, "supplier_outstanding", "Supplier Outstanding")


def page_roles():
    hlp.std_page_header("Roles & Permissions", status="register", status_kind="shell")
    roles = db.get_roles()
    if not roles:
        st.info("No roles.")
        return
    sel = st.selectbox("Role", [f"{r['code']} - {r['name']}" for r in roles])
    if not sel:
        st.info("Select a role.")
        return
    rid = next((r["id"] for r in roles if str(sel).startswith(str(r["code"]))), None)
    if rid is None:
        st.warning("Could not resolve role.")
        return
    modules = ["Dashboard", "Masters", "Sales", "Purchase", "Inventory", "Production", "Finance", "HR", "Reports", "Admin"]
    perms = []
    for m in modules:
        st.markdown(f"**{m}**")
        c = st.columns(6)
        perms.append({"module": m, "view": c[0].checkbox("View", True, key=f"v{rid}{m}"),
                      "add": c[1].checkbox("Add", key=f"a{rid}{m}"), "edit": c[2].checkbox("Edit", key=f"e{rid}{m}"),
                      "delete": c[3].checkbox("Delete", key=f"d{rid}{m}"), "post": c[4].checkbox("Post", key=f"p{rid}{m}"),
                      "approve": c[5].checkbox("Approve", key=f"ap{rid}{m}")})
    if st.button("Save Permissions"):
        db.save_role_permissions(rid, perms, uid()); st.success("Saved")


def page_settings():
    hlp.std_page_header("System Settings", status="register", status_kind="shell")
    try:
        _cur_idle = int(db.get_setting("session_idle_minutes", "30") or 30)
    except (TypeError, ValueError):
        _cur_idle = 30
    _cur_idle = max(1, min(_cur_idle, 480))

    with st.form("set"):
        company = st.text_input("Company Name", db.get_setting("company_name", "IFS Chemicals"))
        neg = st.checkbox("Allow Negative Stock", db.get_setting("allow_negative_stock") == "1")

        st.markdown("**Session timeout**")
        st.caption(
            "Users (including distributor portal) are signed out after this many minutes "
            "with no activity. Default is 30 minutes — change it here anytime."
        )
        idle_mins = st.number_input(
            "Session idle timeout (minutes)",
            min_value=1,
            max_value=480,
            step=1,
            value=_cur_idle,
            help="1–480 minutes. Applies to all ERP and portal logins.",
        )

        st.markdown("**Weight Variance Limits (%)**")
        minor_pct = st.number_input(
            "Minor variance threshold (matched if below)",
            min_value=0.0, max_value=100.0, step=0.1,
            value=float(db.get_setting("weight_variance_minor_pct", "1") or 1),
        )
        limit_pct = st.number_input(
            "Maximum variance without admin override",
            min_value=0.0, max_value=100.0, step=0.1,
            value=float(db.get_setting("weight_variance_limit_pct", "5") or 5),
        )
        if st.form_submit_button("Save"):
            db.set_setting("company_name", company)
            db.set_setting("allow_negative_stock", "1" if neg else "0")
            db.set_setting("session_idle_minutes", str(int(idle_mins)))
            db.set_setting("weight_variance_minor_pct", str(minor_pct))
            db.set_setting("weight_variance_limit_pct", str(limit_pct))
            st.success(f"Settings saved — session idle timeout is now {int(idle_mins)} minutes.")
