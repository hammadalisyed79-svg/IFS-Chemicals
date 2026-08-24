"""Gate Pass — material in/out linked to purchase/sales invoices."""

from datetime import date, datetime
import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui.helpers import uid, smart_select, std_page_header, invoice_bill_material_select, gate_pass_payment_caption, fmt_money, fmt_datetime_from_record, render_dataframe_html_table
from erp_ui import form_flow as ff


def _apply_prefill(defaults):
    for k, v in defaults.items():
        if v is not None and k not in st.session_state.get("gp_skip_prefill", set()):
            st.session_state[f"gp_{k}"] = v


def _sales_invoice_rows():
    return [
        {"id": r["id"], "code": r["invoice_no"], "name": r["customer_name"],
         "label": f"{r['invoice_no']} — {r['customer_name']} ({r['sale_date']})"}
        for r in db.get_sales()
    ]


def _purchase_invoice_rows():
    return [
        {"id": r["id"], "code": r["invoice_no"], "name": r["supplier_name"],
         "label": f"{r['invoice_no']} — {r['supplier_name']} ({r['purchase_date']})"}
        for r in db.get_purchases()
    ]


def _delivery_note_rows():
    return [
        {"id": r["id"], "code": r["document_no"], "name": r.get("customer_name", ""),
         "label": f"{r['document_no']} — {r.get('customer_name', '')} ({r.get('dn_date', '')})"}
        for r in db.get_delivery_notes()
    ]


def _grn_rows():
    return [
        {"id": r["id"], "code": r["document_no"], "name": r.get("supplier_name", ""),
         "label": f"{r['document_no']} — {r.get('supplier_name', '')} ({r.get('grn_date', '')})"}
        for r in db.get_grns()
    ]


def gate_pass_print_panel(rows, key_prefix="gp_print"):
    """Print preview / PDF for one selected gate pass (original + duplicate on this page)."""
    if not rows:
        return
    opts = {
        f"{r['document_no']} — {r.get('party_name', '')} ({fmt_datetime_from_record(r, 'pass_date', time_field='pass_time')})": r["id"]
        for r in rows
    }
    st.subheader("Print Gate Pass")
    sel = st.selectbox("Select Gate Pass", list(opts.keys()), key=f"{key_prefix}_sel")
    st.caption("Use **Print Duplicate** or **Print Original + Duplicate (1 page)** below the preview.")
    from erp_ui.document_print import document_print_toolbar
    document_print_toolbar("Gate Pass", opts[sel], key_prefix=key_prefix)


def invoice_gate_pass_panel(invoice_kind, invoice_id, key_prefix=""):
    """Show linked gate passes from invoice (sales = auto-generated on save)."""
    if invoice_kind == "sales":
        linked = db.get_gate_passes(sales_invoice_id=invoice_id)
        if linked:
            st.caption("Gate pass linked to this invoice — remarks refresh when you **Update Sale**.")
            pay_txt = gate_pass_payment_caption(linked[0])
            if pay_txt:
                st.markdown(pay_txt)
            df = pd.DataFrame([{
                "Gate Pass": r["document_no"],
                "Date / Time": fmt_datetime_from_record(r, "pass_date", time_field="pass_time"),
                "Type": r.get("pass_type"),
                "Vehicle": r.get("vehicle_no"),
                "Sales Invoice": r.get("sales_invoice_no") or "—",
            } for r in linked])
            render_dataframe_html_table(df)
            gate_pass_print_panel(linked, key_prefix=f"{key_prefix}_gp")
        else:
            st.caption(
                "No gate pass yet. Save the invoice to refresh an existing pass, "
                "or generate one below (weighbridge invoices usually auto-create on save with a weight slip)."
            )
            if st.button("Generate Gate Pass from Invoice", key=f"{key_prefix}_gp_regen"):
                try:
                    from erp_ui.helpers import uid
                    gid = db.generate_gate_pass_from_sale(invoice_id, uid(), require_approved=False)
                    ff.action_done(f"Gate pass generated (ID {gid}).")
                except Exception as e:
                    st.error(str(e))
        return

    linked = db.get_gate_passes(purchase_invoice_id=invoice_id)
    ptype = "material_in"
    label = "Inward Gate Pass"
    if linked:
        st.caption("Linked gate passes")
        df = pd.DataFrame([{
            "Gate Pass": r["document_no"],
            "Date / Time": fmt_datetime_from_record(r, "pass_date", time_field="pass_time"),
            "Type": r.get("pass_type"),
            "Vehicle": r.get("vehicle_no"),
            "Status": r.get("status"),
        } for r in linked])
        df.columns = ["Gate Pass", "Date / Time", "Type", "Vehicle", "Status"]
        render_dataframe_html_table(df)
        gate_pass_print_panel(linked, key_prefix=f"{key_prefix}_gp")
    else:
        st.caption("No inward gate pass yet. Save draft with a linked weight slip to auto-generate.")
        if st.button("Generate Inward Gate Pass", key=f"{key_prefix}_gp_regen"):
            try:
                from erp_ui.helpers import uid
                gid = db.generate_gate_pass_from_purchase(invoice_id, uid(), require_approved=False)
                ff.action_done(f"Inward gate pass generated (ID {gid}).")
            except Exception as e:
                st.error(str(e))


def page_gate_pass_entry():
    from erp_ui.helpers import sticky_page_tabs

    peek = st.session_state.get("gp_entry_tab") or "New Pass"
    std_page_header(
        "Gate Pass Entry",
        status="register" if peek == "Register" else None,
        status_kind="shell" if peek == "Register" else "invoice",
    )
    prefill = st.session_state.pop("gp_prefill", None)
    if prefill:
        _apply_prefill(prefill)

    tab = sticky_page_tabs(["New Pass", "Register"], "gp_entry_tab")
    now = datetime.now()

    if tab == "New Pass":
        fid = "gp"
        wk = lambda n: ff.widget_key(fid, n)
        type_labels = dict(db.GATE_PASS_TYPES)
        default_type = st.session_state.get("gp_pass_type", db.GATE_PASS_TYPES[0][0])
        if default_type not in type_labels:
            default_type = db.GATE_PASS_TYPES[0][0]
        type_keys = [t[0] for t in db.GATE_PASS_TYPES]
        pass_type = st.selectbox(
            "Type", type_keys, index=type_keys.index(default_type),
            format_func=lambda x: type_labels[x], key=wk("pass_type"),
        )
        is_outward = pass_type in db.GATE_PASS_OUTWARD
        is_inward = pass_type in db.GATE_PASS_INWARD

        sales_inv_id = purchase_inv_id = dn_id = grn_id = None
        if is_outward:
            st.markdown("**Link to Sales Invoice** *(required for outward pass)*")
            _, sales_inv_id, _ = smart_select(
                "Sales Invoice", _sales_invoice_rows(), f"gp_sales_inv_{pass_type}", "id",
                lambda r: r["label"],
            )
            if sales_inv_id and st.session_state.get("gp_last_sales_inv") != sales_inv_id:
                defaults = db.gate_pass_defaults_from_sales_invoice(sales_inv_id)
                _apply_prefill(defaults)
                st.session_state["gp_last_sales_inv"] = sales_inv_id
                st.rerun()
            dn_opts = ["(None)"] + [r["label"] for r in _delivery_note_rows()]
            dn_map = {r["label"]: r["id"] for r in _delivery_note_rows()}
            dn_sel = st.selectbox("Delivery Note (optional)", dn_opts, key=wk("dn_sel"))
            dn_id = dn_map.get(dn_sel) if dn_sel != "(None)" else st.session_state.get("gp_delivery_note_id")
        elif is_inward:
            st.markdown("**Link to Purchase Invoice** *(required for inward pass)*")
            _, purchase_inv_id, _ = smart_select(
                "Purchase Invoice", _purchase_invoice_rows(), f"gp_pur_inv_{pass_type}", "id",
                lambda r: r["label"],
            )
            if purchase_inv_id and st.session_state.get("gp_last_pur_inv") != purchase_inv_id:
                defaults = db.gate_pass_defaults_from_purchase_invoice(purchase_inv_id)
                _apply_prefill(defaults)
                st.session_state["gp_last_pur_inv"] = purchase_inv_id
                st.rerun()
            grn_opts = ["(None)"] + [r["label"] for r in _grn_rows()]
            grn_map = {r["label"]: r["id"] for r in _grn_rows()}
            grn_sel = st.selectbox("GRN (optional)", grn_opts, key=wk("grn_sel"))
            grn_id = grn_map.get(grn_sel) if grn_sel != "(None)" else st.session_state.get("gp_grn_id")

        gp_no = st.text_input("Gate Pass No", value=db.peek_document("GP"), key=wk("document_no"))
        c1, c2 = st.columns(2)
        gp_date = c1.date_input("Date", value=date.today(), key=wk("pass_date"))
        gp_time = c2.text_input("Time", value=now.strftime("%H:%M:%S"), key=wk("pass_time"))
        vehicle = st.text_input("Vehicle Number", value=st.session_state.get("gp_vehicle_no", ""), key=wk("vehicle_no"))
        driver = st.text_input("Driver Name", value=st.session_state.get("gp_driver_name", ""), key=wk("driver_name"))
        party_name = st.text_input(
            "Party Name", value=st.session_state.get("gp_party_name", ""), key=wk("party_name"),
        )
        party_phone = (st.session_state.get("gp_party_phone") or "").strip()
        if party_phone:
            st.caption(f"Party contact: **{party_phone}** — prints on gate pass")
        linked_inv_id = sales_inv_id or purchase_inv_id
        inv_kind = "sales" if sales_inv_id else ("purchase" if purchase_inv_id else None)
        pid = None
        mat = None
        material = ""
        qty = float(st.session_state.get("gp_quantity") or 0)
        weight = float(st.session_state.get("gp_weight") or 0)
        if linked_inv_id and inv_kind:
            mat = invoice_bill_material_select(
                inv_kind, linked_inv_id, "gp",
                default_pick=st.session_state.get("gp_invoice_line_pick"),
            )
            if mat:
                pid = mat.get("product_id")
                material = mat.get("material_desc") or ""
                qty = float(mat.get("quantity") or 0)
                weight = float(mat.get("net_weight") or st.session_state.get("gp_weight") or 0)
        else:
            _, pid, _ = smart_select(
                "Material / Item", db.get_items(), "gp_item", "id",
                lambda r: f"{r['code']} - {r['name']}",
            )
            material = st.text_input(
                "Material Description",
                value=st.session_state.get("gp_material_desc", ""),
                key=wk("material_desc_free"),
            )
            c3, c4 = st.columns(2)
            qty = c3.number_input(
                "Quantity", min_value=0.0,
                value=float(st.session_state.get("gp_quantity") or 0),
                key=wk("quantity_free"),
            )
            weight = c4.number_input(
                "Weight (kg)", min_value=0.0,
                value=float(st.session_state.get("gp_weight") or 0),
                key=wk("weight_free"),
            )
        if linked_inv_id and inv_kind:
            c3, c4 = st.columns(2)
            c3.metric("Pass Quantity", f"{qty:,.2f}")
            weight = c4.number_input(
                "Physical Weight (kg)", min_value=0.0,
                value=float(st.session_state.get("gp_weight") or weight or 0),
                key=wk("weight_linked"),
                help="Scale weight for this shipment (invoice line weights shown above).",
            )
        approved = st.text_input("Approved By / Remarks", key=wk("remarks"))
        if st.button("Save Gate Pass"):
            try:
                payload = {
                    "document_no": gp_no, "pass_type": pass_type, "pass_date": str(gp_date),
                    "pass_time": gp_time, "vehicle_no": vehicle, "driver_name": driver,
                    "party_name": party_name, "product_id": pid, "material_desc": material,
                    "quantity": qty, "weight": weight, "remarks": approved,
                    "sales_invoice_id": sales_inv_id, "purchase_invoice_id": purchase_inv_id,
                    "delivery_note_id": dn_id, "grn_id": grn_id,
                    "customer_id": st.session_state.get("gp_customer_id"),
                    "supplier_id": st.session_state.get("gp_supplier_id"),
                    "weight_slip_id": st.session_state.get("gp_weight_slip_id"),
                }
                gid = db.save_gate_pass(payload, None, uid())
                if approved:
                    db.approve_gate_pass(gid, uid())
                ff.finish_post_new_form(
                    fid,
                    "Gate pass saved — form cleared for next entry.",
                    prefixes=["gp"],
                )
            except Exception as e:
                st.error(str(e))

    elif tab == "Register":
        from erp_ui import transaction_list as txn
        txn.gate_pass_register_list()


def page_gate_pass_reports():
    """Redirect to Reports Center — Gate Pass Register."""
    st.session_state["rpt_nav_to"] = "Gate Pass Register"
    from erp_ui.reports_pages import page_reports_center
    page_reports_center()
