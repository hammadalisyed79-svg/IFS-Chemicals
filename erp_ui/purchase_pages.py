"""Purchase invoice pages — extracted from app.py."""

from datetime import date

import streamlit as st
from application import data_gateway as db
from erp_ui import helpers as hlp
from erp_ui import form_flow as ff
from erp_ui import transaction_list as txn


def supplier_options(active_only=True):
    rows = db.get_suppliers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def item_options(active_only=True):
    rows = sorted(
        db.get_items(active_only=active_only),
        key=lambda r: hlp.natural_code_sort_key(r.get("code")),
    )
    return {f"{r['code']} - {r['name']} ({r['stock_qty']} {r['unit']})": r for r in rows}


def _seed_pur_edit(purchase, sup_opts, *, sup=None, inv=None, pdate=None, pay_mode=None, paid=None, notes=None, from_form=False):
    st.session_state["pur_edit_id"] = purchase["id"]
    st.session_state["pur_edit_header"] = {
        "invoice_no": inv if from_form else purchase["invoice_no"],
        "supplier_id": sup_opts[sup] if from_form and sup else purchase["supplier_id"],
        "purchase_date": str(pdate) if from_form else purchase["purchase_date"],
        "payment_mode": pay_mode if from_form else purchase["payment_mode"],
        "paid_amount": paid if from_form else purchase["paid_amount"],
        "notes": notes if from_form else (purchase.get("notes") or ""),
        "discount_pct": float(purchase.get("discount_pct") or 0),
        "tax_rate_id": purchase.get("tax_rate_id"),
        "tax_inclusive": bool(purchase.get("tax_inclusive")),
        "weight_slip_id": purchase.get("weight_slip_id"),
        # Keep PO link on edit — otherwise save clears order_id and reopens the PO
        "order_id": purchase.get("order_id"),
    }
    st.session_state["pur_edit_lines"] = hlp._pad_line_rows([
        {"item_id": li["item_id"], "quantity": li["quantity"], "rate": li["rate"],
         "amount": li["amount"], "net_weight": li.get("net_weight", 0),
         "discount_pct": float(li.get("discount_pct") or 0),
         "line_discount": float(li.get("line_discount") or 0),
         "_disc_locked": True}
        for li in purchase["items"]
    ])

def page_purchases():
    from erp_ui.invoice_status_ui import (
        invoice_status_banner, invoice_action_bar, render_invoice_review, section_step,
    )
    from erp_ui.helpers import sticky_page_tabs

    _peek_tab = st.session_state.get("pur_inv_tab") or "Register"
    _pur_hdr_status = None
    _pur_status_kind = "invoice"
    if st.session_state.get("pur_edit_id"):
        _ed = db.get_purchase(st.session_state["pur_edit_id"])
        if _ed:
            _pur_hdr_status = _ed.get("status")
    elif _peek_tab == "New":
        _pur_hdr_status = "draft"
    elif _peek_tab == "Register":
        _pur_hdr_status = "register"
        _pur_status_kind = "shell"
    elif _peek_tab == "Pending":
        _pur_hdr_status = "pending_approval"
    elif _peek_tab == "Drafts":
        _pur_hdr_status = "draft"

    hlp.std_page_header(
        "Purchase Invoices",
        subtitle="Register · Drafts · Pending · New · Edit",
        status=_pur_hdr_status,
        status_kind=_pur_status_kind,
    )
    _pur_tab = sticky_page_tabs(
        ["Register", "Drafts", "Pending", "New", "Edit"],
        "pur_inv_tab",
        open_alias_key="pur_open_tab",
    )

    if _pur_tab == "Register":
        def _pur_actions(row):
            invoice_status_banner("purchase", row)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Print**")
                from erp_ui.document_print import document_print_toolbar
                document_print_toolbar("Purchase Invoice", row["id"], key_prefix=f"pur_doc_{row['id']}")
            with c2:
                st.markdown("**Gate Pass**")
                from erp_ui.gatepass_pages import invoice_gate_pass_panel
                invoice_gate_pass_panel("purchase", row["id"], key_prefix="pur_gp")

        txn.purchase_register_list(action_panel=_pur_actions)

    elif _pur_tab == "Drafts":
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
                    "purchase", inv_id, key_prefix=f"pur_dr_{s}_{inv_id}",
                )
                if inv:
                    invoice_action_bar(
                        "purchase", inv_id, inv.get("status"),
                        key_prefix=f"pur_dr_{s}_{inv_id}", show_print=False,
                    )

            txn.invoice_workflow_tab(
                f"pur_page_draft_{status}", db.search_purchases, status, "Supplier",
                _draft_actions,
            )

    elif _pur_tab == "Pending":
        from erp_ui.invoice_status_ui import status_badge_html
        st.markdown(
            f'<div class="txn-status-strip">{status_badge_html("pending_approval")}&nbsp;'
            f'<span class="txn-queue-label">Waiting for approval</span></div>',
            unsafe_allow_html=True,
        )

        def _pending_actions(inv_id, _ea):
            inv = render_invoice_review(
                "purchase", inv_id, key_prefix=f"pur_pg_pend_{inv_id}",
            )
            if inv:
                invoice_action_bar(
                    "purchase", inv_id, "pending_approval",
                    key_prefix=f"pur_pg_pend_{inv_id}", show_print=False,
                )

        txn.invoice_workflow_tab(
            "pur_page_pending", db.search_purchases, "pending_approval", "Supplier",
            _pending_actions,
        )

    elif _pur_tab == "New":
        items_dict = item_options()
        if not items_dict:
            st.warning("Add items first.")
            return

        section_step("Party & options", 1)
        open_pos = db.get_purchase_orders_for_invoice()
        if open_pos:
            st.markdown("**Create invoice from Purchase Order** (optional)")
            po_opts = {
                f"{o['document_no']} — {o['supplier_name']} — Rs. {float(o['total']):,.0f} ({o['status']})": o["id"]
                for o in open_pos
            }
            c_po1, c_po2 = st.columns([3, 1])
            po_lbl = c_po1.selectbox("Open Purchase Order", ["— Select —"] + list(po_opts.keys()), key="pur_pick_po")
            if c_po2.button("Load Order", key="pur_load_po") and po_lbl != "— Select —":
                try:
                    order = hlp.prime_purchase_from_order(po_opts[po_lbl])
                    ff.action_done(f"Loaded order **{order['document_no']}**.")
                except Exception as e:
                    st.error(str(e))
            st.divider()

        direct_pur = st.session_state.get("pur_direct") or st.session_state.get("pur_header", {}).get("weighbridge_required") == 0
        direct_pur = st.checkbox(
            "Direct / counter purchase (no weighbridge required)",
            value=bool(direct_pur),
            key="pur_direct_cb",
            help="Corrugated, packing, services, etc. — invoice by qty; credit or cash.",
        )
        st.session_state["pur_direct"] = direct_pur

        if st.session_state.get("pur_order_id"):
            order = db.get_purchase_order(st.session_state["pur_order_id"])
            if order:
                st.info(f"Invoicing purchase order **{order['document_no']}** for **{order['supplier_name']}**.")
                sup_id = order["supplier_id"]
            else:
                st.session_state.pop("pur_order_id", None)
                sup_id = None
        else:
            sup_id = None

        if not sup_id:
            from_customer = st.checkbox(
                "Party is a Customer (buy from customer)",
                value=bool(st.session_state.get("pur_from_customer")),
                key="pur_from_customer_cb",
                help="Search Customers instead of Suppliers. A matching Supplier with the same code "
                     "is linked or created automatically so the purchase posts correctly.",
            )
            st.session_state["pur_from_customer"] = from_customer
            try:
                sup_id = hlp.resolve_purchase_party_id(from_customer=from_customer, key="pur_new_party")
            except Exception as e:
                st.error(str(e))
                return
            if not sup_id:
                st.info(
                    "Select a customer or supplier, or load a purchase order to continue."
                    if from_customer
                    else "Select a supplier or load a purchase order to continue."
                )
                return
        elif not st.session_state.get("pur_header"):
            order = db.get_purchase_order(st.session_state["pur_order_id"])
            st.session_state["pur_header"] = {
                "invoice_no": db.peek_invoice("PUR", "purchase_invoices"),
                "supplier_id": sup_id,
                "purchase_date": str(date.today()),
                "payment_mode": "credit",
                "paid_amount": 0,
                "notes": f"From purchase order {order['document_no']}",
                "tax_rate_id": db.default_tax_rate_id(),
                "discount_pct": 0,
                "order_id": st.session_state.get("pur_order_id"),
                "weighbridge_required": 0 if direct_pur else 1,
            }
            st.session_state["pur_lines"] = db.purchase_order_invoice_lines(st.session_state["pur_order_id"])

        if "pur_lines" not in st.session_state:
            st.session_state["pur_lines"] = [{"item_id": None, "quantity": 1.0, "rate": 0.0, "amount": 0.0}]
        if "pur_header" not in st.session_state:
            st.session_state["pur_header"] = {
                "invoice_no": db.peek_invoice("PUR", "purchase_invoices"),
                "supplier_id": sup_id,
                "purchase_date": str(date.today()),
                "payment_mode": "credit",
                "paid_amount": 0,
                "notes": "",
                "tax_rate_id": db.default_tax_rate_id(),
                "discount_pct": 0,
                "weighbridge_required": 0 if direct_pur else 1,
            }

        section_step("Header", 2)
        hdr0 = st.session_state.get("pur_header") or {}
        h1, h2 = st.columns(2)
        inv = h1.text_input(
            "Invoice No",
            value=hdr0.get("invoice_no") or db.peek_invoice("PUR", "purchase_invoices"),
            key="pur_new_inv",
        )
        pdate = h2.date_input(
            "Purchase Date",
            value=date.fromisoformat(hdr0["purchase_date"]) if hdr0.get("purchase_date") else date.today(),
            key="pur_new_dt",
        )
        h3, h4, h5 = st.columns(3)
        pay_modes = ["credit", "cash", "bank"]
        pay_idx = pay_modes.index(hdr0["payment_mode"]) if hdr0.get("payment_mode") in pay_modes else 0
        pay_mode = h3.selectbox("Payment Mode", pay_modes, index=pay_idx, key="pur_new_pay")
        with h4:
            paid = hlp.money_input(
                "Paid Amount", value=float(hdr0.get("paid_amount") or 0), min_value=0.0, key="pur_new_paid",
            )
        notes = h5.text_input("Notes", value=hdr0.get("notes") or "", key="pur_new_notes")
        st.session_state["pur_header"] = {
            **hdr0,
            "invoice_no": inv,
            "supplier_id": sup_id,
            "purchase_date": str(pdate),
            "payment_mode": pay_mode,
            "paid_amount": paid,
            "notes": notes,
            "tax_rate_id": hdr0.get("tax_rate_id") or db.default_tax_rate_id(),
            "discount_pct": float(hdr0.get("discount_pct") or 0),
            "order_id": st.session_state.get("pur_order_id"),
            "weighbridge_required": 0 if direct_pur else 1,
        }

        section_step("Lines & tax", 3)
        header = st.session_state.get("pur_header", {})
        header["weighbridge_required"] = 0 if direct_pur else 1
        ws_id = None
        ws_primary = True
        if not direct_pur:
            ws_id, ws_primary = hlp.weight_slip_select(
                "pur_new", party_type="supplier", supplier_id=sup_id, required=True,
            )
        else:
            st.caption("Direct purchase — weight slip not required.")
        lines, subtotal = hlp.smart_line_item_editor(
            items_dict, "pur", show_weight=not direct_pur, party_id=header.get("supplier_id") or sup_id,
            default_discount_pct=float(header.get("discount_pct") or 0),
        )
        tax_hdr, totals = hlp.invoice_tax_form(
            "pur", lines, header,
            party_id=header.get("supplier_id") or sup_id, party_kind="purchase",
        )
        header.update(tax_hdr)
        inv_wt = sum(float(l.get("net_weight") or 0) for l in lines)
        if ws_id:
            header["weight_slip_id"] = ws_id
            header["weight_slip_as_primary"] = ws_primary
            hlp.show_weight_variance(inv_wt, ws_id, as_primary=ws_primary)
        elif not direct_pur:
            header.pop("weight_slip_id", None)
            header.pop("weight_slip_as_primary", None)
        if not direct_pur:
            st.caption(f"Total invoice item weight: **{inv_wt:,.3f} kg**")
        st.write(f"**Net Invoice:** {fmt_money(totals['total'])}")
        st.session_state["pur_header"] = header

        from erp_ui.voucher_validation import (
            collect_purchase_issues,
            render_validation_panel,
            render_stock_policy_banner,
        )
        if ws_id and not direct_pur:
            header["weight_slip_id"] = ws_id
        render_stock_policy_banner()
        pur_vr = collect_purchase_issues(
            header, lines, totals, direct_purchase=direct_pur,
        )
        render_validation_panel(pur_vr)

        st.markdown('<div class="erp-shell-action-bar-marker"></div>', unsafe_allow_html=True)
        with st.container(key="pur_new_act_bar"):
            c_save, c_tot = st.columns([1, 2])
            with c_tot:
                st.markdown(f"**Net total:** {fmt_money(totals['total'])} · Draft until submitted")
            with c_save:
                save_clicked = st.button("Save Draft Invoice", type="primary", key="save_pur", use_container_width=True)

        section_step("Save", 4)
        if save_clicked:
            pur_vr = collect_purchase_issues(
                header, lines, totals, direct_purchase=direct_pur,
            )
            if not pur_vr.ok:
                render_validation_panel(pur_vr)
            elif not lines:
                st.error("Add at least one line item.")
            elif not direct_pur and not ws_id:
                st.error("Complete weight on **Weight Scale**, then create invoice — weight slip is required.")
            else:
                try:
                    if direct_pur:
                        header.pop("weight_slip_id", None)
                    elif ws_id:
                        header["weight_slip_id"] = ws_id
                    pid = ff.run_with_loading(
                        lambda: db.save_purchase(header, lines, user_id=hlp.uid()),
                        "Saving draft…",
                    )
                    gp = db.get_gate_passes(purchase_invoice_id=pid)
                    gp_no = gp[0]["document_no"] if gp else None
                    msg = "Draft saved."
                    if not direct_pur:
                        msg = "Draft saved — weight slip linked."
                    if gp_no:
                        msg += f" Inward gate pass **{gp_no}** auto-generated."
                    msg += " Open **Drafts** to submit for approval."
                    ff.finish_new_entry(
                        "pur",
                        also=[
                            "pur_order_id", "pur_direct", "pur_direct_cb",
                            "pur_from_customer", "pur_from_customer_cb",
                        ],
                        message=msg,
                    )
                    try:
                        from erp_ui.user_prefs import track_recent_doc
                        purchase = db.get_purchase(pid)
                        if purchase:
                            track_recent_doc(
                                purchase.get("invoice_no") or "",
                                label=f"Purchase {purchase.get('invoice_no')}",
                                group="Purchases",
                                screen="Purchase Invoices",
                            )
                    except Exception:
                        pass
                except Exception as e:
                    st.error(str(e))

    elif _pur_tab == "Edit":
        party_opts = supplier_options()
        pid, _ = txn.transaction_picker(
            "pur_edit",
            db.search_purchases,
            lambda r: f"{r['invoice_no']} — {r['supplier_name']} ({r['purchase_date']}) [{r.get('status','draft')}]",
            "Supplier",
            party_opts,
            "supplier_id",
        )
        if not pid:
            return
        purchase = db.get_purchase(pid)
        status = (purchase.get("status") or "draft").lower()
        sup_opts = supplier_options()
        items_dict = item_options()

        if status == "pending_approval":
            render_invoice_review("purchase", pid, key_prefix=f"pur_edit_rev_{pid}")
            invoice_action_bar("purchase", pid, status, key_prefix=f"pur_edit_act_{pid}", show_print=False)
            return
        if status == "cancelled":
            render_invoice_review("purchase", pid, key_prefix=f"pur_edit_rev_{pid}")
            return
        if status == "approved":
            render_invoice_review("purchase", pid, key_prefix=f"pur_edit_rev_{pid}")
            invoice_action_bar("purchase", pid, status, key_prefix=f"pur_edit_act_{pid}", show_print=False)
            return

        # draft / rejected
        invoice_status_banner("purchase", purchase)
        sup_keys = list(sup_opts.keys())
        cur_sup_id = (st.session_state.get("pur_edit_header") or {}).get("supplier_id") or purchase["supplier_id"]
        sup_idx = next((i for i, k in enumerate(sup_keys) if sup_opts[k] == cur_sup_id), 0)
        with st.form("edit_purchase_hdr"):
            inv = st.text_input("Invoice No", value=purchase["invoice_no"])
            sup = st.selectbox(
                "Supplier",
                sup_keys,
                index=sup_idx,
                help="Change supplier here, then click Load for Edit and Update Purchase.",
            )
            pdate = st.date_input("Date", value=date.fromisoformat(purchase["purchase_date"]))
            pay_mode = st.selectbox("Payment Mode", ["credit", "cash", "bank"],
                                    index=["credit", "cash", "bank"].index(purchase["payment_mode"]))
            paid = hlp.money_input(
                "Paid Amount", value=float(purchase["paid_amount"]), min_value=0.0, key="pur_edit_paid",
            )
            notes = st.text_input("Notes", value=purchase["notes"] or "")
            load = st.form_submit_button("Load for Edit")
        if ff.edit_panel_active("pur_edit", pid, load_clicked=load):
            if load:
                _seed_pur_edit(
                    purchase, sup_opts, sup=sup, inv=inv, pdate=pdate,
                    pay_mode=pay_mode, paid=paid, notes=notes, from_form=True,
                )
            elif ff.consume_edit_reload("pur_edit", pid):
                purchase = db.get_purchase(pid)
                _seed_pur_edit(purchase, sup_opts)
            header = st.session_state.get("pur_edit_header", {})
            direct_edit = purchase.get("weighbridge_required") == 0
            direct_edit = st.checkbox(
                "Direct / no weighbridge", value=direct_edit, key="pur_edit_direct",
            )
            header["weighbridge_required"] = 0 if direct_edit else 1
            ws_id = None
            ws_primary = True
            edit_sup_id = header.get("supplier_id") or purchase.get("supplier_id")
            if not direct_edit:
                ws_id, ws_primary = hlp.weight_slip_select(
                    "pur_edit", party_type="supplier", current_slip_id=purchase.get("weight_slip_id"),
                    supplier_id=edit_sup_id, required=True, current_invoice_id=pid,
                )
                if ws_id:
                    header["weight_slip_id"] = ws_id
                    header["weight_slip_as_primary"] = ws_primary
            else:
                header.pop("weight_slip_id", None)
                header.pop("weight_slip_as_primary", None)
                st.caption("Direct purchase — weight slip not required.")
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "pur_edit", st.session_state.get("pur_edit_lines", []),
                show_weight=not direct_edit, party_id=edit_sup_id,
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "pur_edit", lines, header,
                party_id=edit_sup_id,
                party_kind="purchase",
            )
            header.update(tax_hdr)
            inv_wt = sum(float(l.get("net_weight") or 0) for l in lines)
            if header.get("weight_slip_id"):
                hlp.show_weight_variance(
                    inv_wt, header["weight_slip_id"],
                    as_primary=header.get("weight_slip_as_primary", True),
                )
            st.write(f"**Net Invoice:** {fmt_money(totals['total'])}")
            if purchase.get("gate_pass_id"):
                gps = db.get_gate_passes(purchase_invoice_id=pid)
                if gps:
                    st.caption(f"Linked inward gate pass: **{gps[0].get('document_no')}**")
            c1, c2, c3 = st.columns(3)
            from erp_ui.voucher_validation import (
                collect_purchase_issues,
                render_validation_panel,
                render_stock_policy_banner,
            )
            render_stock_policy_banner()
            pur_edit_vr = collect_purchase_issues(
                header, lines, totals, direct_purchase=direct_edit,
            )
            render_validation_panel(pur_edit_vr)
            if c1.button("Update Purchase", key="upd_pur", type="primary"):
                pur_edit_vr = collect_purchase_issues(
                    header, lines, totals, direct_purchase=direct_edit,
                )
                if not pur_edit_vr.ok:
                    render_validation_panel(pur_edit_vr)
                elif not lines:
                    st.error("Add at least one line item.")
                elif not direct_edit and not header.get("weight_slip_id"):
                    st.error("Weight slip is required for this purchase.")
                else:
                    try:
                        ff.run_with_loading(
                            lambda: db.save_purchase(header, lines, purchase_id=pid, user_id=hlp.uid()),
                            "Updating purchase…",
                        )
                        ff.finish_edit_refresh("pur_edit", pid, "pur_edit", "Purchase updated.")
                    except Exception as e:
                        st.error(str(e))
            if c2.button("Submit for Approval", key="sub_pur"):
                pur_edit_vr = collect_purchase_issues(
                    header, lines, totals, direct_purchase=direct_edit, stage="approve",
                )
                if not pur_edit_vr.ok:
                    render_validation_panel(pur_edit_vr)
                else:
                    try:
                        ff.run_with_loading(
                            lambda: (
                                db.save_purchase(header, lines, purchase_id=pid, user_id=hlp.uid()),
                                db.submit_purchase_invoice(pid, hlp.uid()),
                            ),
                            "Submitting for approval…",
                        )
                        ff.finish_edit_refresh("pur_edit", pid, "pur_edit", "Submitted for approval.")
                    except Exception as e:
                        st.error(str(e))
            if c3.button("Delete Purchase", key="del_pur"):
                db.delete_purchase(pid)
                ff.finish_after_delete("pur_edit", "pur_edit", "Purchase deleted.")

