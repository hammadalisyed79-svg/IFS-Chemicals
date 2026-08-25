"""Sales invoice pages — extracted from app.py."""

from datetime import date

import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff
from erp_ui import transaction_list as txn


def customer_options(active_only=True):
    rows = db.get_customers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def item_options(active_only=True):
    rows = sorted(
        db.get_items(active_only=active_only),
        key=lambda r: hlp.natural_code_sort_key(r.get("code")),
    )
    return {f"{r['code']} - {r['name']} ({r['stock_qty']} {r['unit']})": r for r in rows}


def _seed_sal_edit(sale, cust_opts, *, cust=None, inv=None, sdate=None, notes=None, from_form=False):
    st.session_state["sal_edit_id"] = sale["id"]
    st.session_state["sal_edit_header"] = {
        "invoice_no": inv if from_form else sale["invoice_no"],
        "customer_id": cust_opts[cust] if from_form and cust else sale["customer_id"],
        "sale_date": str(sdate) if from_form else sale["sale_date"],
        "payment_mode": sale["payment_mode"],
        "paid_amount": sale["paid_amount"],
        "notes": notes if from_form else (sale.get("notes") or ""),
        "discount_pct": float(sale.get("discount_pct") or 0),
        "tax_rate_id": sale.get("tax_rate_id"),
        "tax_inclusive": bool(sale.get("tax_inclusive")),
        "weight_slip_id": sale.get("weight_slip_id"),
        "vehicle_no": sale.get("vehicle_no") or "",
        "driver_name": sale.get("driver_name") or "",
        "driver_contact": sale.get("driver_contact") or "",
        "dispatch_remarks": sale.get("dispatch_remarks") or "",
        "weighbridge_required": sale.get("weighbridge_required"),
        # Keep SO/quotation link on edit — otherwise save clears order_id and reopens the SO
        "order_id": sale.get("order_id"),
        "quotation_id": sale.get("quotation_id"),
    }
    st.session_state["sal_edit_lines"] = hlp._pad_line_rows([
        {"item_id": li["item_id"], "quantity": li["quantity"], "rate": li["rate"],
         "amount": li["amount"], "net_weight": li.get("net_weight", 0),
         "discount_pct": float(li.get("discount_pct") or 0),
         "line_discount": float(li.get("line_discount") or 0),
         "_disc_locked": True}
        for li in sale["items"]
    ])


def page_sales():
    from erp_ui.invoice_status_ui import (
        invoice_status_banner, invoice_action_bar, render_invoice_review, section_step,
    )
    from erp_ui.helpers import sticky_page_tabs

    _peek_tab = st.session_state.get("sal_inv_tab") or "Register"
    _sal_hdr_status = None
    _sal_status_kind = "invoice"
    if st.session_state.get("sal_edit_id"):
        _ed = db.get_sale(st.session_state["sal_edit_id"])
        if _ed:
            _sal_hdr_status = _ed.get("status")
    elif _peek_tab == "New":
        _sal_hdr_status = "draft"
    elif _peek_tab == "Register":
        _sal_hdr_status = "register"
        _sal_status_kind = "shell"
    elif _peek_tab == "Pending":
        _sal_hdr_status = "pending_approval"
    elif _peek_tab == "Drafts":
        _sal_hdr_status = "draft"

    hlp.std_page_header(
        "Sales Invoices",
        subtitle="Register · Drafts · Pending · New · Multi Dispatch · Edit",
        status=_sal_hdr_status,
        status_kind=_sal_status_kind,
    )
    _sal_tab = sticky_page_tabs(
        ["Register", "Drafts", "Pending", "New", "Multi Dispatch", "Edit"],
        "sal_inv_tab",
        open_alias_key="sal_open_tab",
    )

    if _sal_tab == "Register":
        def _sales_actions(row):
            invoice_status_banner("sale", row)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Print**")
                from erp_ui.document_print import document_print_toolbar
                ptype = st.selectbox("Format", ["Sales Invoice", "Sales Tax Invoice"], key="sal_print_type")
                document_print_toolbar(ptype, row["id"], key_prefix=f"sal_doc_{row['id']}")
            with c2:
                st.markdown("**Gate Pass**")
                from erp_ui.gatepass_pages import invoice_gate_pass_panel
                invoice_gate_pass_panel("sales", row["id"], key_prefix="sal_gp")

        txn.sales_register_list(action_panel=_sales_actions)

    elif _sal_tab == "Drafts":
        from erp_ui.invoice_status_ui import status_badge_html
        st.markdown(
            f'<div class="txn-status-strip">{status_badge_html("draft")}&nbsp;'
            f'{status_badge_html("rejected")}&nbsp;'
            f'<span class="txn-queue-label">Edit, submit, or delete</span></div>',
            unsafe_allow_html=True,
        )
        for status in ("draft", "rejected"):
            st.markdown(f"##### {status.replace('_', ' ').title()}")

            def _draft_actions(inv_id, _ea, s=status):
                inv = render_invoice_review(
                    "sale", inv_id, key_prefix=f"sal_dr_{s}_{inv_id}",
                )
                if inv:
                    invoice_action_bar(
                        "sale", inv_id, inv.get("status"),
                        key_prefix=f"sal_dr_{s}_{inv_id}", show_print=False,
                    )

            txn.invoice_workflow_tab(
                f"sal_page_draft_{status}", db.search_sales_invoices, status, "Customer",
                _draft_actions,
            )

    elif _sal_tab == "Pending":
        from erp_ui.invoice_status_ui import status_badge_html
        st.markdown(
            f'<div class="txn-status-strip">{status_badge_html("pending_approval")}&nbsp;'
            f'<span class="txn-queue-label">Waiting for approval</span></div>',
            unsafe_allow_html=True,
        )

        def _pending_actions(inv_id, _ea):
            inv = render_invoice_review(
                "sale", inv_id, key_prefix=f"sal_pg_pend_{inv_id}",
            )
            if inv:
                invoice_action_bar(
                    "sale", inv_id, "pending_approval",
                    key_prefix=f"sal_pg_pend_{inv_id}", show_print=False,
                )

        txn.invoice_workflow_tab(
            "sal_page_pending", db.search_sales_invoices, "pending_approval", "Customer",
            _pending_actions,
        )

    elif _sal_tab == "New":
        items_dict = item_options()
        if not items_dict:
            st.warning("Add items first.")
            return

        section_step("Party & options", 1)
        open_quotes = db.get_quotations_for_conversion()
        if open_quotes:
            st.markdown("**Create invoice from Quotation** (optional — skip sales order)")
            qt_opts = {
                f"{q['document_no']} — {q['customer_name']} — Rs. {float(q['total']):,.0f}": q["id"]
                for q in open_quotes
            }
            c_qt1, c_qt2, c_qt3, c_qt4 = st.columns([2.5, 1, 1, 0.9])
            qt_lbl = c_qt1.selectbox("Open Quotation", ["— Select —"] + list(qt_opts.keys()), key="sal_pick_qt")
            no_wb_qt = c_qt2.checkbox(
                "No weighbridge", key="sal_qt_no_wb",
                help="Corrugated, packing, services — invoice by qty; credit OK",
            )
            retail_qt = c_qt3.checkbox(
                "Retail cash", key="sal_qt_retail", help="Factory outlet — cash only",
            )
            if c_qt4.button("Load Quote", key="sal_load_qt") and qt_lbl != "— Select —":
                try:
                    quote = hlp.prime_sale_from_quotation(
                        qt_opts[qt_lbl], no_weighbridge=no_wb_qt, retail=retail_qt,
                    )
                    st.session_state.pop("sal_order_id", None)
                    ff.action_done(f"Loaded quotation **{quote['document_no']}**.")
                except Exception as e:
                    st.error(str(e))
            st.divider()

        open_orders = db.get_sales_orders_for_invoice()
        if open_orders:
            st.markdown("**Create invoice from Sales Order** (optional)")
            so_opts = {
                hlp.sales_order_picker_label(o): o["id"]
                for o in open_orders
            }
            c_so1, c_so2 = st.columns([3, 1])
            so_lbl = c_so1.selectbox("Open Sales Order", ["— Select —"] + list(so_opts.keys()), key="sal_pick_so")
            if c_so2.button("Load Order", key="sal_load_so") and so_lbl != "— Select —":
                try:
                    order = hlp.prime_sale_from_order(so_opts[so_lbl])
                    st.session_state.pop("sal_quotation_id", None)
                    ff.action_done(f"Loaded order **{order['document_no']}**.")
                except Exception as e:
                    st.error(str(e))
            st.divider()

        hdr = st.session_state.get("sal_header") or {}
        no_wb_sale = st.session_state.get("sal_no_wb")
        if no_wb_sale is None:
            no_wb_sale = hdr.get("weighbridge_required") == 0
        retail_sale = bool(st.session_state.get("sal_retail"))
        c_s1, c_s2 = st.columns(2)
        no_wb_sale = c_s1.checkbox(
            "Invoice without weighbridge (corrugated, packing, services, etc.)",
            value=bool(no_wb_sale),
            key="sal_no_wb_cb",
            help="Bill by quantity only — weight slip not required. Credit or cash allowed.",
        )
        if no_wb_sale:
            retail_sale = c_s2.checkbox(
                "Retail / factory outlet (cash sale only)",
                value=retail_sale,
                key="sal_retail_cb",
                help="Counter sale: payment mode must be cash and fully paid.",
            )
        else:
            retail_sale = False
            c_s2.caption("Retail cash applies only when weighbridge is off.")
        if retail_sale:
            no_wb_sale = True
        st.session_state["sal_no_wb"] = no_wb_sale
        st.session_state["sal_retail"] = retail_sale
        flow = hlp.sale_invoice_flow_flags(no_wb_sale, retail_sale)

        if st.session_state.get("sal_order_id"):
            order = db.get_sales_order(st.session_state["sal_order_id"])
            if order:
                st.info(f"Invoicing sales order **{order['document_no']}** for **{order['customer_name']}**.")
                cust_id = order["customer_id"]
            else:
                st.session_state.pop("sal_order_id", None)
                cust_id = None
        elif st.session_state.get("sal_quotation_id"):
            quote = db.get_quotation(st.session_state["sal_quotation_id"])
            if quote:
                st.info(f"Invoicing quotation **{quote['document_no']}** for **{quote['customer_name']}**.")
                cust_id = quote["customer_id"]
            else:
                st.session_state.pop("sal_quotation_id", None)
                cust_id = None
        else:
            cust_id = None

        if not cust_id:
            from_supplier = st.checkbox(
                "Party is a Supplier (sell to supplier)",
                value=bool(st.session_state.get("sal_from_supplier")),
                key="sal_from_supplier_cb",
                help="Search Suppliers instead of Customers. A matching Customer with the same code "
                     "is linked or created automatically so the sale posts correctly.",
            )
            st.session_state["sal_from_supplier"] = from_supplier
            try:
                cust_id = hlp.resolve_sale_party_id(from_supplier=from_supplier, key="sal_new_party")
            except Exception as e:
                st.error(str(e))
                return
            if not cust_id:
                st.info(
                    "Select a supplier, or load a quotation / sales order to continue."
                    if from_supplier
                    else "Select a customer, quotation, or sales order to continue."
                )
                return
        elif not st.session_state.get("sal_header"):
            if st.session_state.get("sal_order_id"):
                order = db.get_sales_order(st.session_state["sal_order_id"])
                ref_no = order["document_no"]
                note = f"From sales order {ref_no}"
            else:
                quote = db.get_quotation(st.session_state["sal_quotation_id"])
                ref_no = quote["document_no"]
                note = f"From quotation {ref_no}"
            st.session_state["sal_header"] = {
                "invoice_no": db.peek_invoice("SAL", "sales_invoices"),
                "customer_id": cust_id,
                "sale_date": str(date.today()),
                "payment_mode": flow["default_payment_mode"],
                "paid_amount": 0,
                "notes": note,
                "tax_rate_id": db.default_tax_rate_id(),
                "discount_pct": 0,
                "order_id": st.session_state.get("sal_order_id"),
                "quotation_id": st.session_state.get("sal_quotation_id"),
                "weighbridge_required": flow["weighbridge_required"],
            }
            if st.session_state.get("sal_order_id"):
                st.session_state["sal_lines"] = db.sales_order_invoice_lines(st.session_state["sal_order_id"])
            elif st.session_state.get("sal_quotation_id"):
                st.session_state["sal_lines"] = db.quotation_to_lines(st.session_state["sal_quotation_id"])[0]

        # Ensure lines session exists once party is known (no Preview Lines gate)
        if "sal_lines" not in st.session_state:
            st.session_state["sal_lines"] = [{"item_id": None, "quantity": 1.0, "rate": 0.0, "amount": 0.0}]
        if "sal_header" not in st.session_state:
            st.session_state["sal_header"] = {
                "invoice_no": db.peek_invoice("SAL", "sales_invoices"),
                "customer_id": cust_id,
                "sale_date": str(date.today()),
                "payment_mode": flow["default_payment_mode"],
                "paid_amount": 0,
                "notes": "",
                "tax_rate_id": db.default_tax_rate_id(),
                "discount_pct": 0,
                "weighbridge_required": flow["weighbridge_required"],
            }

        section_step("Header", 2)
        hdr0 = st.session_state.get("sal_header") or {}
        h1, h2, h3 = st.columns(3)
        inv = h1.text_input("Invoice No", value=hdr0.get("invoice_no") or db.peek_invoice("SAL", "sales"), key="sal_new_inv")
        sdate = h2.date_input(
            "Sale Date",
            value=date.fromisoformat(hdr0["sale_date"]) if hdr0.get("sale_date") else date.today(),
            key="sal_new_dt",
        )
        notes = h3.text_input("Notes", value=hdr0.get("notes") or "", key="sal_new_notes")
        flow = hlp.sale_invoice_flow_flags(no_wb_sale, retail_sale)
        st.session_state["sal_header"] = {
            **hdr0,
            "invoice_no": inv,
            "customer_id": cust_id,
            "sale_date": str(sdate),
            "notes": notes,
            "payment_mode": flow["default_payment_mode"] if retail_sale else hdr0.get("payment_mode", flow["default_payment_mode"]),
            "tax_rate_id": hdr0.get("tax_rate_id") or db.default_tax_rate_id(),
            "discount_pct": float(hdr0.get("discount_pct") or 0),
            "order_id": st.session_state.get("sal_order_id"),
            "quotation_id": st.session_state.get("sal_quotation_id"),
            "weighbridge_required": flow["weighbridge_required"],
        }

        section_step("Lines & tax", 3)
        header = st.session_state.get("sal_header", {})
        header["weighbridge_required"] = flow["weighbridge_required"]
        cust_row = next((c for c in db.get_customers() if c["id"] == cust_id), None)
        if cust_row:
            reg = "Registered" if (cust_row.get("ntn") or cust_row.get("strn")) else "Unregistered"
            st.caption(
                f"**{cust_row['name']}** — NTN: {cust_row.get('ntn') or '—'} · "
                f"STRN: {cust_row.get('strn') or '—'} · **{reg}** taxpayer"
            )
        if retail_sale:
            header["payment_mode"] = "cash"
        ws_id = None
        ws_primary = True
        if flow["show_weight"]:
            ws_id, ws_primary = hlp.weight_slip_select(
                "sal_new", party_type="customer", customer_id=cust_id, required=True,
            )
        else:
            st.caption(
                "Non-weighed invoice — enter qty and rate only. "
                "Use **credit** or tick **Retail** for cash counter sales."
            )
            header.update(hlp.sale_dispatch_fields_ui("sal_new", header))
        lines, subtotal = hlp.smart_line_item_editor(
            items_dict, "sal", show_weight=flow["show_weight"],
            party_id=header.get("customer_id") or cust_id,
            default_discount_pct=float(header.get("discount_pct") or 0),
        )
        tax_hdr, totals = hlp.invoice_tax_form(
            "sal", lines, header,
            party_id=header.get("customer_id") or cust_id, party_kind="sale",
        )
        header.update(tax_hdr)
        inv_wt = sum(float(l.get("net_weight") or 0) for l in lines)
        if ws_id:
            header["weight_slip_id"] = ws_id
            header["weight_slip_as_primary"] = ws_primary
            hlp.show_weight_variance(inv_wt, ws_id, as_primary=ws_primary)
        elif not flow["show_weight"]:
            header.pop("weight_slip_id", None)
            header.pop("weight_slip_as_primary", None)
        if flow["show_weight"]:
            st.caption(f"Total invoice item weight: **{inv_wt:,.3f} kg**")
        st.write(f"**Net Invoice:** {fmt_money(totals['total'])}")
        was_retail_new = st.session_state.get("sal_new_was_retail", False)
        if was_retail_new and not retail_sale:
            header["paid_amount"] = 0
            if (header.get("payment_mode") or "").lower() == "cash":
                header["payment_mode"] = "credit"
            st.session_state.pop("sal_new_paid", None)
        st.session_state["sal_new_was_retail"] = bool(retail_sale)
        pay_mode, paid = hlp.sale_payment_ui(
            "sal_new", totals["total"],
            payment_mode=header.get("payment_mode"),
            paid_amount=header.get("paid_amount"),
            retail_sale=retail_sale,
        )
        header["payment_mode"] = pay_mode
        header["paid_amount"] = paid
        st.session_state["sal_header"] = header

        from erp_ui.voucher_validation import (
            collect_sale_issues,
            render_validation_panel,
            render_stock_policy_banner,
        )
        if ws_id and flow["show_weight"]:
            header["weight_slip_id"] = ws_id
        render_stock_policy_banner()
        sal_vr = collect_sale_issues(header, lines, totals, flow=flow)
        render_validation_panel(sal_vr)

        st.markdown('<div class="erp-shell-action-bar-marker"></div>', unsafe_allow_html=True)
        with st.container(key="sal_new_act_bar"):
            c_save, c_tot = st.columns([1, 2])
            with c_tot:
                st.markdown(f"**Net total:** {fmt_money(totals['total'])} · Draft until submitted")
            with c_save:
                save_clicked = st.button("Save Draft Invoice", type="primary", key="save_sal", use_container_width=True)

        section_step("Save", 4)
        if save_clicked:
            sal_vr = collect_sale_issues(header, lines, totals, flow=flow)
            if not sal_vr.ok:
                render_validation_panel(sal_vr)
            elif not lines:
                st.error("Add at least one line item.")
            elif flow["show_weight"] and not ws_id:
                st.error("Complete weight on **Weight Scale**, then create invoice — weight slip is required.")
            else:
                try:
                    if not flow["show_weight"]:
                        header.pop("weight_slip_id", None)
                    elif ws_id:
                        header["weight_slip_id"] = ws_id
                    sid = ff.run_with_loading(
                        lambda: db.save_sale(header, lines, user_id=hlp.uid()),
                        "Saving draft…",
                    )
                    gp = db.get_gate_passes(sales_invoice_id=sid)
                    gp_no = gp[0]["document_no"] if gp else None
                    if flow["show_weight"]:
                        msg = "Draft saved — weight slip linked."
                        if gp_no:
                            msg += f" Gate pass **{gp_no}** auto-generated."
                    else:
                        msg = "Draft saved — non-weighed invoice."
                        if gp_no:
                            msg += f" Gate pass **{gp_no}** created with dispatch details."
                    msg += " Open **Drafts** to submit for approval."
                    ff.finish_new_entry(
                        "sal",
                        also=[
                            "sal_order_id", "sal_quotation_id",
                            "sal_no_wb", "sal_no_wb_cb", "sal_retail", "sal_retail_cb",
                            "sal_from_supplier", "sal_from_supplier_cb",
                        ],
                        message=msg,
                    )
                    try:
                        from erp_ui.user_prefs import track_recent_doc
                        sale = db.get_sale(sid)
                        if sale:
                            track_recent_doc(
                                sale.get("invoice_no") or "",
                                label=f"Sale {sale.get('invoice_no')}",
                                group="Sales",
                                screen="Sales Invoices",
                            )
                    except Exception:
                        pass
                except Exception as e:
                    st.error(str(e))

    elif _sal_tab == "Multi Dispatch":
        from erp_ui.multi_sale_pages import page_multi_dispatch_sale
        page_multi_dispatch_sale(items_dict=item_options(), embedded=True)

    elif _sal_tab == "Edit":
        party_opts = customer_options()
        sid, _ = txn.transaction_picker(
            "sal_edit",
            db.search_sales_invoices,
            lambda r: f"{r['invoice_no']} — {r['customer_name']} ({r['sale_date']}) [{r.get('status','draft')}]",
            "Customer",
            party_opts,
            "customer_id",
        )
        if not sid:
            return
        sale = db.get_sale(sid)
        status = (sale.get("status") or "draft").lower()
        cust_opts = customer_options()
        items_dict = item_options()

        if status == "pending_approval":
            render_invoice_review("sale", sid, key_prefix=f"sal_edit_rev_{sid}")
            invoice_action_bar("sale", sid, status, key_prefix=f"sal_edit_act_{sid}", show_print=False)
            return
        if status == "cancelled":
            render_invoice_review("sale", sid, key_prefix=f"sal_edit_rev_{sid}")
            return
        if status == "approved":
            render_invoice_review("sale", sid, key_prefix=f"sal_edit_rev_{sid}")
            invoice_action_bar("sale", sid, status, key_prefix=f"sal_edit_act_{sid}", show_print=False)
            return

        # draft / rejected — editable
        invoice_status_banner("sale", sale)
        cust_keys = list(cust_opts.keys())
        cur_cust_id = (st.session_state.get("sal_edit_header") or {}).get("customer_id") or sale["customer_id"]
        cust_idx = next((i for i, k in enumerate(cust_keys) if cust_opts[k] == cur_cust_id), 0)
        with st.form("edit_sale_hdr"):
            inv = st.text_input("Invoice No", value=sale["invoice_no"])
            cust = st.selectbox(
                "Customer",
                cust_keys,
                index=cust_idx,
                help="Change customer here, then click Load for Edit and Update Sale.",
            )
            sdate = st.date_input("Date", value=date.fromisoformat(sale["sale_date"]))
            notes = st.text_input("Notes", value=sale["notes"] or "")
            load = st.form_submit_button("Load for Edit")
        if ff.edit_panel_active("sal_edit", sid, load_clicked=load):
            if load:
                _seed_sal_edit(
                    sale, cust_opts, cust=cust, inv=inv, sdate=sdate, notes=notes, from_form=True,
                )
            elif ff.consume_edit_reload("sal_edit", sid):
                sale = db.get_sale(sid)
                _seed_sal_edit(sale, cust_opts)
            header = st.session_state.get("sal_edit_header", {})
            editable = True
            no_wb_edit = sale.get("weighbridge_required") == 0
            retail_edit = no_wb_edit and (sale.get("payment_mode") or "").lower() == "cash"
            ec1, ec2 = st.columns(2)
            no_wb_edit = ec1.checkbox(
                "Invoice without weighbridge",
                value=no_wb_edit,
                key="sal_edit_no_wb",
            )
            if no_wb_edit:
                retail_edit = ec2.checkbox(
                    "Retail / cash only", value=retail_edit, key="sal_edit_retail",
                )
            else:
                retail_edit = False
            flow_edit = hlp.sale_invoice_flow_flags(no_wb_edit, retail_edit)
            header["weighbridge_required"] = flow_edit["weighbridge_required"]
            if retail_edit:
                header["payment_mode"] = "cash"
            ws_id = None
            ws_primary = True
            edit_cust_id = header.get("customer_id") or sale.get("customer_id")
            if flow_edit["show_weight"]:
                ws_id, ws_primary = hlp.weight_slip_select(
                    "sal_edit", party_type="customer", current_slip_id=sale.get("weight_slip_id"),
                    customer_id=edit_cust_id, required=True, current_invoice_id=sid,
                )
                if ws_id:
                    header["weight_slip_id"] = ws_id
                    header["weight_slip_as_primary"] = ws_primary
            else:
                header.pop("weight_slip_id", None)
                header.pop("weight_slip_as_primary", None)
                st.caption("Non-weighed invoice — weight slip not required.")
                header.update(hlp.sale_dispatch_fields_ui("sal_edit", header))
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "sal_edit", st.session_state.get("sal_edit_lines", []),
                show_weight=flow_edit["show_weight"],
                party_id=edit_cust_id,
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "sal_edit", lines, header,
                party_id=edit_cust_id,
                party_kind="sale",
            )
            header.update(tax_hdr)
            inv_wt = sum(float(l.get("net_weight") or 0) for l in lines)
            if header.get("weight_slip_id"):
                hlp.show_weight_variance(
                    inv_wt, header["weight_slip_id"],
                    as_primary=header.get("weight_slip_as_primary", True),
                )
            st.write(f"**Net Invoice:** {fmt_money(totals['total'])}")
            was_retail = st.session_state.get("sal_edit_was_retail", False)
            if was_retail and not retail_edit:
                header["paid_amount"] = 0
                if (header.get("payment_mode") or "").lower() == "cash":
                    header["payment_mode"] = "bank"
                st.session_state.pop("sal_edit_paid", None)
            st.session_state["sal_edit_was_retail"] = bool(retail_edit)
            pay_mode, paid = hlp.sale_payment_ui(
                "sal_edit", totals["total"],
                payment_mode=header.get("payment_mode"),
                paid_amount=header.get("paid_amount"),
                retail_sale=bool(retail_edit),
            )
            header["payment_mode"] = pay_mode
            header["paid_amount"] = paid
            if sale.get("gate_pass_id"):
                gps = db.get_gate_passes(sales_invoice_id=sid)
                if gps:
                    st.caption(f"Linked gate pass: **{gps[0].get('document_no')}**")
                    pay_cap = hlp.gate_pass_payment_caption(gps[0])
                    if pay_cap:
                        st.markdown(pay_cap)
            c1, c2, c3 = st.columns(3)
            from erp_ui.voucher_validation import (
                collect_sale_issues,
                render_validation_panel,
                render_stock_policy_banner,
            )
            render_stock_policy_banner()
            sal_edit_vr = collect_sale_issues(header, lines, totals, flow=flow_edit)
            render_validation_panel(sal_edit_vr)
            if c1.button("Update Sale", key="upd_sal", type="primary"):
                sal_edit_vr = collect_sale_issues(header, lines, totals, flow=flow_edit)
                if not sal_edit_vr.ok:
                    render_validation_panel(sal_edit_vr)
                elif not lines:
                    st.error("Add at least one line item.")
                elif flow_edit["show_weight"] and not header.get("weight_slip_id"):
                    st.error("Weight slip is required for this sale.")
                else:
                    try:
                        ff.run_with_loading(
                            lambda: db.save_sale(header, lines, sale_id=sid, user_id=hlp.uid()),
                            "Updating sale…",
                        )
                        ff.finish_edit_refresh("sal_edit", sid, "sal_edit", "Sale updated.")
                    except Exception as e:
                        st.error(str(e))
            if c2.button("Submit for Approval", key="sub_sal"):
                sal_edit_vr = collect_sale_issues(
                    header, lines, totals, flow=flow_edit, stage="approve",
                )
                if not sal_edit_vr.ok:
                    render_validation_panel(sal_edit_vr)
                else:
                    try:
                        ff.run_with_loading(
                            lambda: (
                                db.save_sale(header, lines, sale_id=sid, user_id=hlp.uid()),
                                db.submit_sale_invoice(sid, hlp.uid()),
                            ),
                            "Submitting for approval…",
                        )
                        ff.finish_edit_refresh("sal_edit", sid, "sal_edit", "Submitted for approval.")
                    except Exception as e:
                        st.error(str(e))
            if c3.button("Delete Sale", key="del_sal"):
                db.delete_sale(sid)
                ff.finish_after_delete("sal_edit", "sal_edit", "Sale deleted.")

