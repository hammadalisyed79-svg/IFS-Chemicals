"""Sale / Purchase return pages — extracted from app.py."""

from datetime import date

import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff
from erp_ui import transaction_list as txn


def customer_options(active_only=True):
    rows = db.get_customers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def supplier_options(active_only=True):
    rows = db.get_suppliers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def item_options(active_only=True):
    rows = sorted(
        db.get_items(active_only=active_only),
        key=lambda r: hlp.natural_code_sort_key(r.get("code")),
    )
    return {f"{r['code']} - {r['name']} ({r['stock_qty']} {r['unit']})": r for r in rows}


def _seed_pr_edit(ret, sup_opts, *, sup=None, ret_no=None, rdate=None, notes=None, from_form=False):
    st.session_state["pr_edit_id"] = ret["id"]
    st.session_state["pr_edit_header"] = {
        "return_no": ret_no if from_form else ret["return_no"],
        "supplier_id": sup_opts[sup] if from_form and sup else ret["supplier_id"],
        "purchase_id": ret.get("purchase_id"),
        "return_date": str(rdate) if from_form else ret["return_date"],
        "notes": notes if from_form else (ret.get("notes") or ""),
    }
    st.session_state["pr_edit_lines"] = hlp._pad_line_rows([
        {"item_id": li["item_id"], "quantity": li["quantity"], "rate": li["rate"],
         "amount": li["amount"], "net_weight": li.get("net_weight", 0)}
        for li in ret["items"]
    ])


def _seed_sr_edit(ret, cust_opts, *, cust=None, ret_no=None, rdate=None, notes=None, from_form=False):
    st.session_state["sr_edit_id"] = ret["id"]
    st.session_state["sr_edit_header"] = {
        "return_no": ret_no if from_form else ret["return_no"],
        "customer_id": cust_opts[cust] if from_form and cust else ret["customer_id"],
        "sale_id": ret.get("sale_id"),
        "return_date": str(rdate) if from_form else ret["return_date"],
        "notes": notes if from_form else (ret.get("notes") or ""),
    }
    st.session_state["sr_edit_lines"] = hlp._pad_line_rows([
        {"item_id": li["item_id"], "quantity": li["quantity"], "rate": li["rate"],
         "amount": li["amount"], "net_weight": li.get("net_weight", 0)}
        for li in ret["items"]
    ])




def page_purchase_return():
    from erp_ui.helpers import sticky_page_tabs
    from erp_ui.document_print import document_print_toolbar
    from erp_ui.gatepass_pages import invoice_gate_pass_panel

    peek = st.session_state.get("pr_page_tab") or "Register"
    hlp.std_page_header(
        "Purchase Returns",
        subtitle="Register · Open · New · Edit — print, linked invoice & gate pass",
        status="register" if peek == "Register" else ("draft" if peek == "New" else None),
        status_kind="shell" if peek == "Register" else "invoice",
    )
    _pr_tab = sticky_page_tabs(
        ["Register", "Open", "New", "Edit"],
        "pr_page_tab",
        open_alias_key="pr_open_tab",
    )

    if _pr_tab == "Register":
        def _pr_actions(row):
            inv_id = row.get("purchase_id")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Print return**")
                document_print_toolbar("Purchase Return", row["id"], key_prefix=f"pr_doc_{row['id']}")
                if inv_id:
                    st.markdown("**Print linked invoice**")
                    st.caption(f"Invoice: {row.get('invoice_no') or inv_id}")
                    document_print_toolbar(
                        "Purchase Invoice", inv_id, key_prefix=f"pr_inv_{row['id']}",
                    )
                else:
                    st.caption("No purchase invoice linked to this return.")
            with c2:
                st.markdown("**Gate pass (via linked invoice)**")
                if inv_id:
                    invoice_gate_pass_panel("purchase", inv_id, key_prefix=f"pr_gp_{row['id']}")
                else:
                    st.caption("Link a purchase invoice on the return to manage gate pass here.")

        txn.purchase_return_register_list(action_panel=_pr_actions)

    elif _pr_tab == "Open":
        from erp_ui.document_hub import render_document_hub
        render_document_hub("purchase_return", "pr_hub")

    elif _pr_tab == "New":
        sup_opts = supplier_options()
        items_dict = item_options()
        if not sup_opts or not items_dict:
            st.warning("Add suppliers and items first.")
            return
        with st.form("new_pur_ret"):
            default_ret = (st.session_state.get("pr_header") or {}).get("return_no") or db.peek_invoice("PR", "purchase_returns", "return_no")
            ret_no = st.text_input("Return No", value=default_ret)
            sup_labels, blank = hlp.options_with_blank(sup_opts.keys())
            sup_lbl = st.selectbox("Supplier", sup_labels)
            submitted_hdr = st.form_submit_button("Continue")
        if submitted_hdr:
            if not hlp.require_selected("supplier", sup_lbl, blank):
                return
            sup_id = sup_opts[sup_lbl]
            st.session_state["pr_header"] = {
                "return_no": ret_no, "supplier_id": sup_id,
                "return_date": str(date.today()), "notes": "",
            }
            st.session_state["pr_lines"] = [{"item_id": None, "quantity": 1.0, "rate": 0.0, "amount": 0.0}]
        if "pr_lines" in st.session_state:
            header = st.session_state.get("pr_header", {})
            rdate = st.date_input("Return Date", value=date.fromisoformat(header.get("return_date", str(date.today()))), key="pr_new_dt")
            notes = st.text_input("Notes", value=header.get("notes") or "", key="pr_new_notes")
            header["return_date"] = str(rdate)
            header["notes"] = notes
            purchase_id = txn.linked_invoice_picker(
                "pr_new", db.search_purchases, header["supplier_id"], "supplier_id",
                lambda r: f"{r['invoice_no']} - {r['supplier_name']}",
            )
            header["purchase_id"] = purchase_id
            if purchase_id and st.button("Load lines from purchase invoice", key="pr_load_inv"):
                try:
                    lines, inv = hlp.return_lines_from_invoice(purchase_id, "purchase")
                    st.session_state["pr_lines"] = lines
                    ff.action_done(f"Loaded {len(lines)} line(s) from **{inv['invoice_no']}**.")
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "pr", show_weight=True, party_id=header.get("supplier_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "pr_tax", lines, header,
                party_id=header.get("supplier_id"), party_kind="purchase",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {hlp.fmt_money(totals['total'])}")
            if st.button("Save Purchase Return", key="save_pr"):
                if not lines:
                    st.error("Add at least one line item.")
                else:
                    try:
                        db.save_purchase_return(header, lines)
                        ff.finish_new_entry("pr", message="Purchase return saved.")
                    except Exception as e:
                        st.error(str(e))

    elif _pr_tab == "Edit":
        party_opts = supplier_options()
        rid, _ = txn.document_picker(
            "pr_edit", db.search_purchase_returns,
            lambda r: f"{r['return_no']} — {r['supplier_name']} ({r['return_date']})",
            "Supplier", party_opts, "supplier_id",
        )
        if not rid:
            return
        ret = db.get_purchase_return(rid)
        st.markdown("##### Print / Gate Pass")
        c1, c2 = st.columns(2)
        with c1:
            document_print_toolbar("Purchase Return", rid, key_prefix=f"pr_edit_doc_{rid}")
            if ret.get("purchase_id"):
                document_print_toolbar(
                    "Purchase Invoice", ret["purchase_id"], key_prefix=f"pr_edit_inv_{rid}",
                )
        with c2:
            if ret.get("purchase_id"):
                invoice_gate_pass_panel("purchase", ret["purchase_id"], key_prefix=f"pr_edit_gp_{rid}")
            else:
                st.caption("No linked purchase invoice for gate pass.")
        st.divider()
        sup_opts = supplier_options()
        items_dict = item_options()
        sup_lbl = next((k for k, v in sup_opts.items() if v == ret["supplier_id"]), list(sup_opts.keys())[0])
        with st.form("edit_pr_hdr"):
            ret_no = st.text_input("Return No", value=ret["return_no"])
            sup = st.selectbox("Supplier", list(sup_opts.keys()), index=list(sup_opts.keys()).index(sup_lbl) if sup_lbl in sup_opts else 0)
            rdate = st.date_input("Date", value=date.fromisoformat(ret["return_date"]))
            notes = st.text_input("Notes", value=ret["notes"] or "")
            load = st.form_submit_button("Load for Edit")
        if ff.edit_panel_active("pr_edit", rid, load_clicked=load):
            if load:
                _seed_pr_edit(ret, sup_opts, sup=sup, ret_no=ret_no, rdate=rdate, notes=notes, from_form=True)
            elif ff.consume_edit_reload("pr_edit", rid):
                ret = db.get_purchase_return(rid)
                _seed_pr_edit(ret, sup_opts)
            header = st.session_state.get("pr_edit_header", {})
            header["purchase_id"] = txn.linked_invoice_picker(
                "pr_edit_lnk", db.search_purchases, header.get("supplier_id"), "supplier_id",
                lambda r: f"{r['invoice_no']} - {r['supplier_name']}",
            )
            if header.get("purchase_id") and st.button("Reload lines from invoice", key="pr_edit_load"):
                try:
                    lines, _ = hlp.return_lines_from_invoice(header["purchase_id"], "purchase")
                    st.session_state["pr_edit_lines"] = hlp._pad_line_rows(lines)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "pr_edit", st.session_state.get("pr_edit_lines", []),
                show_weight=True, party_id=header.get("supplier_id") or ret.get("supplier_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "pr_edit_tax", lines, header,
                party_id=header.get("supplier_id") or ret.get("supplier_id"),
                party_kind="purchase",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {hlp.fmt_money(totals['total'])}")
            c1, c2 = st.columns(2)
            if c1.button("Update Return", key="upd_pr"):
                if lines:
                    try:
                        db.save_purchase_return(header, lines, return_id=rid)
                        ff.finish_edit_refresh("pr_edit", rid, "pr_edit", "Updated.")
                    except Exception as e:
                        st.error(str(e))
            if c2.button("Delete Return", key="del_pr"):
                db.delete_purchase_return(rid)
                ff.finish_after_delete("pr_edit", "pr_edit")


def page_sale_return():
    from erp_ui.helpers import sticky_page_tabs
    from erp_ui.document_print import document_print_toolbar
    from erp_ui.gatepass_pages import invoice_gate_pass_panel

    peek = st.session_state.get("sr_page_tab") or "Register"
    hlp.std_page_header(
        "Sales Returns",
        subtitle="Register · Open · New · Edit — print, linked invoice & gate pass",
        status="register" if peek == "Register" else ("draft" if peek == "New" else None),
        status_kind="shell" if peek == "Register" else "invoice",
    )
    _sr_tab = sticky_page_tabs(
        ["Register", "Open", "New", "Edit"],
        "sr_page_tab",
        open_alias_key="sr_open_tab",
    )

    if _sr_tab == "Register":
        def _sr_actions(row):
            inv_id = row.get("sale_id")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Print return**")
                document_print_toolbar("Sale Return", row["id"], key_prefix=f"sr_doc_{row['id']}")
                if inv_id:
                    st.markdown("**Print linked invoice**")
                    st.caption(f"Invoice: {row.get('invoice_no') or inv_id}")
                    ptype = st.selectbox(
                        "Invoice format", ["Sales Invoice", "Sales Tax Invoice"],
                        key=f"sr_inv_print_type_{row['id']}",
                    )
                    document_print_toolbar(ptype, inv_id, key_prefix=f"sr_inv_{row['id']}")
                else:
                    st.caption("No sales invoice linked to this return.")
            with c2:
                st.markdown("**Gate pass (via linked invoice)**")
                if inv_id:
                    invoice_gate_pass_panel("sales", inv_id, key_prefix=f"sr_gp_{row['id']}")
                else:
                    st.caption("Link a sales invoice on the return to manage gate pass here.")

        txn.sale_return_register_list(action_panel=_sr_actions)

    elif _sr_tab == "Open":
        from erp_ui.document_hub import render_document_hub
        render_document_hub("sales_return", "sr_hub")

    elif _sr_tab == "New":
        cust_opts = customer_options()
        items_dict = item_options()
        if not cust_opts or not items_dict:
            st.warning("Add customers and items first.")
            return
        with st.form("new_sal_ret"):
            default_ret = (st.session_state.get("sr_header") or {}).get("return_no") or db.peek_invoice("SR", "sales_returns", "return_no")
            ret_no = st.text_input("Return No", value=default_ret)
            cust_labels, blank = hlp.options_with_blank(cust_opts.keys())
            cust_lbl = st.selectbox("Customer", cust_labels)
            submitted_hdr = st.form_submit_button("Continue")
        if submitted_hdr:
            if not hlp.require_selected("customer", cust_lbl, blank):
                return
            cust_id = cust_opts[cust_lbl]
            st.session_state["sr_header"] = {
                "return_no": ret_no, "customer_id": cust_id,
                "return_date": str(date.today()), "notes": "",
            }
            st.session_state["sr_lines"] = [{"item_id": None, "quantity": 1.0, "rate": 0.0, "amount": 0.0}]
        if "sr_lines" in st.session_state:
            header = st.session_state.get("sr_header", {})
            cust_id = header.get("customer_id")
            rdate = st.date_input("Return Date", value=date.fromisoformat(header.get("return_date", str(date.today()))), key="sr_new_dt")
            notes = st.text_input("Notes", value=header.get("notes") or "", key="sr_new_notes")
            header["return_date"] = str(rdate)
            header["notes"] = notes
            sale_id = txn.linked_invoice_picker(
                "sr_new", db.search_sales_invoices, header["customer_id"], "customer_id",
                lambda r: f"{r['invoice_no']} - {r['customer_name']}",
                label="Linked sale (optional)",
            )
            header["sale_id"] = sale_id
            if sale_id and st.button("Load lines from sales invoice", key="sr_load_inv"):
                try:
                    lines, inv = hlp.return_lines_from_invoice(sale_id, "sale")
                    st.session_state["sr_lines"] = lines
                    ff.action_done(f"Loaded {len(lines)} line(s) from **{inv['invoice_no']}**.")
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "sr", show_weight=True, party_id=header.get("customer_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "sr_tax", lines, header,
                party_id=header.get("customer_id"), party_kind="sale",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {hlp.fmt_money(totals['total'])}")
            if st.button("Save Sale Return", key="save_sr"):
                if not lines:
                    st.error("Add at least one line item.")
                else:
                    try:
                        db.save_sale_return(header, lines)
                        ff.finish_new_entry("sr", message="Sale return saved.")
                    except Exception as e:
                        st.error(str(e))

    elif _sr_tab == "Edit":
        party_opts = customer_options()
        rid, _ = txn.document_picker(
            "sr_edit", db.search_sale_returns,
            lambda r: f"{r['return_no']} — {r['customer_name']} ({r['return_date']})",
            "Customer", party_opts, "customer_id",
        )
        if not rid:
            return
        ret = db.get_sale_return(rid)
        st.markdown("##### Print / Gate Pass")
        c1, c2 = st.columns(2)
        with c1:
            document_print_toolbar("Sale Return", rid, key_prefix=f"sr_edit_doc_{rid}")
            if ret.get("sale_id"):
                ptype = st.selectbox(
                    "Invoice format", ["Sales Invoice", "Sales Tax Invoice"],
                    key=f"sr_edit_inv_type_{rid}",
                )
                document_print_toolbar(ptype, ret["sale_id"], key_prefix=f"sr_edit_inv_{rid}")
        with c2:
            if ret.get("sale_id"):
                invoice_gate_pass_panel("sales", ret["sale_id"], key_prefix=f"sr_edit_gp_{rid}")
            else:
                st.caption("No linked sales invoice for gate pass.")
        st.divider()
        cust_opts = customer_options()
        items_dict = item_options()
        cust_lbl = next((k for k, v in cust_opts.items() if v == ret["customer_id"]), list(cust_opts.keys())[0])
        with st.form("edit_sr_hdr"):
            ret_no = st.text_input("Return No", value=ret["return_no"])
            cust = st.selectbox("Customer", list(cust_opts.keys()), index=list(cust_opts.keys()).index(cust_lbl) if cust_lbl in cust_opts else 0)
            rdate = st.date_input("Date", value=date.fromisoformat(ret["return_date"]))
            notes = st.text_input("Notes", value=ret["notes"] or "")
            load = st.form_submit_button("Load for Edit")
        if ff.edit_panel_active("sr_edit", rid, load_clicked=load):
            if load:
                _seed_sr_edit(ret, cust_opts, cust=cust, ret_no=ret_no, rdate=rdate, notes=notes, from_form=True)
            elif ff.consume_edit_reload("sr_edit", rid):
                ret = db.get_sale_return(rid)
                _seed_sr_edit(ret, cust_opts)
            header = st.session_state.get("sr_edit_header", {})
            header["sale_id"] = txn.linked_invoice_picker(
                "sr_edit_lnk", db.search_sales_invoices, header.get("customer_id"), "customer_id",
                lambda r: f"{r['invoice_no']} - {r['customer_name']}",
                label="Linked sale (optional)",
            )
            if header.get("sale_id") and st.button("Reload lines from invoice", key="sr_edit_load"):
                try:
                    lines, _ = hlp.return_lines_from_invoice(header["sale_id"], "sale")
                    st.session_state["sr_edit_lines"] = hlp._pad_line_rows(lines)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "sr_edit", st.session_state.get("sr_edit_lines", []),
                show_weight=True, party_id=header.get("customer_id") or ret.get("customer_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "sr_edit_tax", lines, header,
                party_id=header.get("customer_id") or ret.get("customer_id"),
                party_kind="sale",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {hlp.fmt_money(totals['total'])}")
            c1, c2 = st.columns(2)
            if c1.button("Update Return", key="upd_sr"):
                if lines:
                    try:
                        db.save_sale_return(header, lines, return_id=rid)
                        ff.finish_edit_refresh("sr_edit", rid, "sr_edit", "Updated.")
                    except Exception as e:
                        st.error(str(e))
            if c2.button("Delete Return", key="del_sr"):
                db.delete_sale_return(rid)
                ff.finish_after_delete("sr_edit", "sr_edit")

