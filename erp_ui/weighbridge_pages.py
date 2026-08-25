"""Weight Scale — matches modern_weight_scale_final workflow."""

from datetime import date, datetime
import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui import form_flow as ff
from erp_ui.helpers import uid, user_role, smart_select, std_page_header, export_buttons
from erp_ui.document_print import document_print_toolbar
from erp_ui.theme import inject_weighbridge_kiosk_css


def _print_first_weight_slip(slip_id, key_prefix="ws1_print"):
    st.markdown("**Print 1st weight slip**")
    st.caption("For parties who need a gate copy after first weigh only (before 2nd weight).")
    document_print_toolbar("Weight Slip", slip_id, key_prefix=key_prefix)


def _party_label(r):
    from db_invoice_workflow import UNKNOWN_PARTY_CODE, slip_party_is_unknown

    name = r.get("customer_name") or r.get("supplier_name")
    code = (r.get("customer_code") or r.get("supplier_code") or "").strip()
    if slip_party_is_unknown(r) or (name or "").strip().upper() in (UNKNOWN_PARTY_CODE, "UNKNOWN PARTY"):
        return "UNKNOWN — assign at 2nd weight"
    if not name:
        return "—"
    return f"{code} - {name}" if code else name


def _party_fmt(r):
    """Dropdown label: account code + name (+ phone)."""
    phone = (r.get("phone") or "").strip()
    base = f"{r.get('code') or ''} - {r.get('name') or ''}".strip(" -")
    return f"{base} ({phone})" if phone else base


def _calc_net(first_w, second_w):
    """Reference logic: Net = Gross − Tare (higher − lower weight)."""
    w1, w2 = float(first_w or 0), float(second_w or 0)
    if w1 and w2:
        return round(abs(w1 - w2), 3)
    return 0.0


def _slip_invoice_status(r):
    from db_commercial import weight_slip_is_linked
    if weight_slip_is_linked(r):
        inv = r.get("sales_invoice_no") or r.get("purchase_invoice_no") or ""
        return f"Linked — {inv}" if inv else "Linked on invoice"
    ref = r.get("sales_invoice_no") or r.get("purchase_invoice_no")
    if ref:
        return f"Completed — attach slip on invoice {ref}"
    return "Completed — attach slip on Sales / Purchase invoice"


def _weight_slip_status_badge(status: str | None) -> str:
    from html import escape
    key = (status or "").lower()
    if key in ("pending", "first_weigh", "pending 2nd"):
        return '<span class="inv-badge inv-badge-pending">Pending 2nd</span>'
    if key == "completed":
        return '<span class="inv-badge inv-badge-approved">Completed</span>'
    if key == "cancelled":
        return '<span class="inv-badge inv-badge-cancelled">Cancelled</span>'
    return f'<span class="inv-badge inv-badge-draft">{escape(str(status or "—"))}</span>'


def _render_weight_slip_html_table(rows, *, mode: str = "pending") -> None:
    from html import escape

    if mode == "pending":
        headers = ("Slip", "Date", "Vehicle", "Party", "Item", "First (kg)", "First Time", "Invoice", "Status")
    else:
        headers = ("Slip", "Date", "Vehicle", "Party", "Item", "First (kg)", "Second (kg)", "Net (kg)", "Bill ref", "Status")
    ths = "".join(f"<th>{h}</th>" for h in headers)
    body = []
    for r in rows:
        if mode == "pending":
            cells = [
                escape(str(r.get("document_no") or "")),
                escape(str(r.get("slip_date") or "")),
                escape(str(r.get("vehicle_no") or "")),
                escape(_party_label(r)),
                escape(str(r.get("product_name") or "—")),
                f"{float(r.get('first_weight') or 0):,.3f}",
                escape(str(r.get("first_weight_time") or r.get("slip_time") or "")),
                escape(str(r.get("sales_invoice_no") or r.get("purchase_invoice_no") or "—")),
                _weight_slip_status_badge("pending"),
            ]
        else:
            st_txt = _slip_invoice_status(r)
            badge = (
                '<span class="inv-badge inv-badge-approved">Linked</span>'
                if "Linked" in st_txt
                else '<span class="inv-badge inv-badge-pending">Unlinked</span>'
            )
            cells = [
                escape(str(r.get("document_no") or "")),
                escape(str(r.get("slip_date") or "")),
                escape(str(r.get("vehicle_no") or "")),
                escape(_party_label(r)),
                escape(str(r.get("product_name") or "—")),
                f"{float(r.get('first_weight') or 0):,.3f}",
                f"{float(r.get('second_weight') or 0):,.3f}",
                f"{float(r.get('net_weight') or 0):,.3f}",
                escape(str(r.get("sales_invoice_no") or r.get("purchase_invoice_no") or "—")),
                badge,
            ]
        row_cells = []
        for i, val in enumerate(cells):
            cls = " class='txn-num'" if i in (5, 6, 7) and mode != "pending" else ""
            if i == 5 and mode == "pending":
                cls = " class='txn-num'"
            if i == len(cells) - 1:
                row_cells.append(f"<td class='txn-status-cell'>{val}</td>")
            elif cls:
                row_cells.append(f"<td{cls}>{val}</td>")
            else:
                row_cells.append(f"<td>{val}</td>")
        body.append("<tr>" + "".join(row_cells) + "</tr>")
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def _pending_complete_eligible(slip):
    if not slip:
        return False
    return (
        slip.get("status") == "first_weigh"
        or (
            slip.get("status") == "cancelled"
            and float(slip.get("second_weight") or 0) <= 0
            and float(slip.get("net_weight") or 0) <= 0
        )
    )


def _second_weight_form_body(slip_id: int, *, key_prefix: str = "ws2"):
    """Shared 2nd-weight fields (used by dialog and backup panel)."""
    from db_invoice_workflow import (
        UNKNOWN_PARTY_CODE,
        slip_party_is_unknown,
        is_unknown_party,
    )

    slip = db.get_weight_slip_pro(slip_id)
    if not _pending_complete_eligible(slip):
        st.error("This slip is not awaiting second weight.")
        if st.button("Close", key=f"{key_prefix}_close_bad"):
            st.session_state.pop("ws_edit_slip_id", None)
            st.rerun()
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.info(
        f"Completing pending slip **{slip['document_no']}** — "
        f"Party **{_party_label(slip)}** — Vehicle **{slip.get('vehicle_no', '—')}** | "
        f"First: **{float(slip.get('first_weight') or 0):,.3f} kg** at {slip.get('first_weight_time', '—')}"
    )
    st.caption(f"Current party: **{_party_label(slip)}**")
    if slip.get("product_name") or slip.get("sales_invoice_no") or slip.get("purchase_invoice_no"):
        inv_ref = slip.get("sales_invoice_no") or slip.get("purchase_invoice_no") or ""
        bits = [b for b in [slip.get("product_name"), f"Bill {inv_ref}" if inv_ref else ""] if b]
        st.caption(" · ".join(bits))

    is_sale = bool(slip.get("customer_id")) or (slip.get("party_type") or "") == "customer"
    need_party = slip_party_is_unknown(slip)
    cid2 = sid2 = None
    party_type_2 = None
    if need_party:
        st.warning(
            "Party was **UNKNOWN** at 1st weight — select the real party before completing 2nd weight."
        )
        party_type_2 = st.selectbox(
            "Type",
            ["SALE (Customer)", "PURCHASE (Supplier)"],
            index=0 if is_sale else 1,
            key=f"{key_prefix}_ptype",
        )
        party_type_2 = party_type_2 or ("SALE (Customer)" if is_sale else "PURCHASE (Supplier)")
        _real_cust = [
            r for r in db.get_customers(active_only=True)
            if str(r.get("code") or "").upper() != UNKNOWN_PARTY_CODE
        ]
        _real_sup = [
            r for r in db.get_suppliers(active_only=True)
            if str(r.get("code") or "").upper() != UNKNOWN_PARTY_CODE
        ]
        if str(party_type_2).startswith("SALE"):
            _, cid2, _ = smart_select(
                "Customer account *", _real_cust, f"{key_prefix}_c", "id",
                _party_fmt,
            )
        else:
            _, sid2, _ = smart_select(
                "Supplier account *", _real_sup, f"{key_prefix}_s", "id",
                _party_fmt,
            )
    else:
        ptype_lbl = "SALE (Customer)" if is_sale else "PURCHASE (Supplier)"
        st.success(
            f"Party locked from 1st weight: **{_party_label(slip)}** · {ptype_lbl}"
        )
        st.caption("No re-selection needed. Only UNKNOWN parties are asked again at 2nd weight.")

    second_w = st.number_input("Second Weight (kg)", min_value=0.0, step=0.001, key=f"{key_prefix}_sw")
    second_t = st.text_input("Second Weight Time", value=ts, key=f"{key_prefix}_st")
    st.metric("Net Weight (Gross − Tare)", f"{_calc_net(slip.get('first_weight'), second_w):,.3f} kg")
    c1, c2 = st.columns(2)
    if c1.button("Complete / Save Second Weight", type="primary", key=f"{key_prefix}_save"):
        try:
            if second_w <= 0:
                raise ValueError("Second weight is required.")
            party_update = None
            if need_party:
                if str(party_type_2).startswith("SALE"):
                    if not cid2:
                        raise ValueError("Select the customer for this dispatch.")
                    if is_unknown_party(cid2, "customer"):
                        raise ValueError("Select a real customer (not UNKNOWN) at 2nd weight.")
                    party_update = {"party_type": "customer", "customer_id": cid2}
                else:
                    if not sid2:
                        raise ValueError("Select the supplier for this receipt.")
                    if is_unknown_party(sid2, "supplier"):
                        raise ValueError("Select a real supplier (not UNKNOWN) at 2nd weight.")
                    party_update = {"party_type": "supplier", "supplier_id": sid2}
            db.complete_weight_slip(
                slip_id, second_w, second_t, uid(), party_update=party_update,
            )
            st.session_state["ws_print_id"] = slip_id
            st.session_state.pop("ws_edit_slip_id", None)
            st.session_state["ws_entry_tab"] = "Completed Slips"
            ff.action_done(
                f"Slip completed — **{slip.get('document_no', '')}**. "
                "Use **Completed Slips → Create draft invoice** wizard below, "
                "or attach this slip on Sales/Purchase Invoices."
            )
        except Exception as e:
            st.error(str(e))
    if c2.button("Cancel (keep pending)", key=f"{key_prefix}_cancel"):
        st.session_state.pop("ws_edit_slip_id", None)
        st.rerun()


@st.dialog("Complete Second Weight", width="large")
def _second_weight_dialog(slip_id: int):
    """Modal popup for 2nd weight — call only while ws_edit_slip_id is set (no tabs underneath)."""
    from erp_ui.dialog_shell import dialog_shell_marker

    dialog_shell_marker()
    _second_weight_form_body(int(slip_id), key_prefix="ws2_dlg")


def page_weight_entry():
    from erp_ui.helpers import sticky_page_tabs

    edit_id = st.session_state.get("ws_edit_slip_id")
    if edit_id:
        std_page_header("Weight Entry", status="register", status_kind="shell")
        try:
            _second_weight_dialog(int(edit_id))
        except Exception as ex:
            st.warning(f"Popup could not open ({ex}). Use the form below.")
        st.info(
            "**Second weight popup** should appear in the centre of the screen. "
            "If it does not, enter the 2nd weight in the backup form below."
        )
        with st.container(border=True):
            st.markdown("##### Backup — Complete Second Weight")
            _second_weight_form_body(int(edit_id), key_prefix="ws2_bak")
        return

    peek = st.session_state.get("ws_entry_tab") or "Weight Entry"
    std_page_header(
        "Weight Entry",
        status="register" if peek == "All Slips Register" else None,
        status_kind="shell" if peek == "All Slips Register" else "invoice",
    )
    tab = sticky_page_tabs([
        "Weight Entry", "Pending 2nd Weight", "Completed Slips", "All Slips Register", "Print Slip", "Edit / Delete",
    ], "ws_entry_tab")
    kiosk = st.toggle(
        "Kiosk mode (large touch targets)",
        value=bool(st.session_state.get("erp_wb_kiosk")),
        key="erp_wb_kiosk_toggle",
        help="For weighbridge operators — larger buttons and inputs.",
    )
    st.session_state["erp_wb_kiosk"] = kiosk
    if kiosk:
        inject_weighbridge_kiosk_css()
    now = datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")

    if tab == "Weight Entry":
        st.markdown("**New first weight**")
        st.caption("Complete pending 2nd weight from the **Pending 2nd Weight** tab (opens a popup).")
        fid = "ws_first"
        wk = lambda n: ff.widget_key(fid, n)
        slip_no = st.text_input("Slip No", db.next_weight_slip_no(), key=wk("no"), disabled=True)
        c1, c2 = st.columns(2)
        slip_date = c1.date_input("Date", value=date.today(), key=wk("date"))
        slip_time = c2.text_input("Time", value=now.strftime("%H:%M:%S"), key=wk("time"))
        party_type = st.selectbox("Type", ["SALE (Customer)", "PURCHASE (Supplier)"], key=wk("party"))
        party_type = party_type or "SALE (Customer)"
        st.caption(
            "At **1st weight** record vehicle and party (or mark **UNKNOWN**). "
            "At **2nd weight** the party is kept automatically; only UNKNOWN slips ask for a party again. "
            "Items/invoice are chosen later on the invoice."
        )
        unknown_party = st.checkbox(
            "Party unknown — use UNKNOWN (assign at 2nd weight)",
            value=False,
            key=wk("unk2"),
            help="Tick only when the vehicle is weighed before the customer/supplier is known.",
        )
        cid = sid = None
        if unknown_party:
            from db_invoice_workflow import unknown_party_id
            if str(party_type).startswith("SALE"):
                cid = unknown_party_id("customer", uid())
            else:
                sid = unknown_party_id("supplier", uid())
            st.info("Party set to **UNKNOWN**. Select the real party when completing 2nd weight.")
        elif str(party_type).startswith("SALE"):
            _, cid, _ = smart_select(
                "Customer account *", db.get_customers(active_only=True), "ws1_c", "id",
                _party_fmt,
            )
        else:
            _, sid, _ = smart_select(
                "Supplier account *", db.get_suppliers(active_only=True), "ws1_s", "id",
                _party_fmt,
            )
        c3, c4 = st.columns(2)
        vehicle_no = c3.text_input("Vehicle No *", key=wk("v"))
        driver = c4.text_input("Driver Name", key=wk("d"))
        first_w = st.number_input("First Weight (kg) *", min_value=0.0, step=0.001, key=wk("fw"))
        first_t = st.text_input("First Weight Time", value=ts, key=wk("ft"))
        remarks = st.text_input("Remarks", key=wk("rm"))

        if st.button("Save First Weight", type="primary", key="ws1_save"):
            if first_w <= 0:
                st.error("First weight is required.")
            elif not vehicle_no.strip():
                st.error("Vehicle number is required.")
            elif str(party_type).startswith("SALE") and not cid:
                st.error("Select a customer, or tick **Party unknown**.")
            elif str(party_type).startswith("PURCHASE") and not sid:
                st.error("Select a supplier, or tick **Party unknown**.")
            else:
                try:
                    payload = {
                        "document_no": slip_no, "slip_date": str(slip_date), "slip_time": slip_time,
                        "customer_id": cid, "supplier_id": sid, "product_id": None,
                        "party_type": "customer" if cid else "supplier",
                        "vehicle_no": vehicle_no.strip().upper(), "driver_name": driver,
                        "first_weight": first_w, "second_weight": 0,
                        "gross_weight": first_w, "tare_weight": 0, "net_weight": 0,
                        "first_weight_time": first_t, "remarks": remarks,
                    }
                    slip_id = db.save_weight_slip_first(payload, uid())
                    msg = f"First weight saved — **{slip_no}**."
                    if unknown_party:
                        msg += " Party is **UNKNOWN** — assign customer/supplier at 2nd weight."
                    else:
                        msg += " Complete 2nd weight when ready (Pending tab)."
                    ff.finish_post_new_form(
                        fid,
                        msg,
                        retain={"ws_print_id": slip_id, "ws_entry_tab": "Weight Entry"},
                    )
                except Exception as e:
                    st.error(str(e))

        print_id = st.session_state.get("ws_print_id")
        if print_id:
            with st.container(border=True):
                st.markdown("**Last saved 1st weight — print ticket**")
                c1, c2 = st.columns(2)
                if c1.button("Go to Pending 2nd Weight", type="primary", key="ws1_goto_pend"):
                    st.session_state["ws_entry_tab"] = "Pending 2nd Weight"
                    st.rerun()
                _print_first_weight_slip(int(print_id), "ws1_after_save")

    elif tab == "Pending 2nd Weight":
        st.markdown("**Slips awaiting second weight**")
        pending = db.get_all_pending_weight_slips()
        if not pending:
            st.info("No pending slips.")
            if st.button("New first weight", type="primary", key="ws_pend_empty_cta"):
                st.session_state["ws_entry_tab"] = "Weight Entry"
                st.rerun()
        else:
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Pending 2nd Weight</p>"
                f"<p class='txn-kpi-val'>{len(pending):,}</p></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="txn-status-strip">'
                f'<span class="inv-badge inv-badge-pending">Pending 2nd</span>&nbsp;'
                f"<strong>{len(pending)}</strong></div>",
                unsafe_allow_html=True,
            )
            _render_weight_slip_html_table(pending, mode="pending")
            opts = {
                f"{r['document_no']} | {_party_label(r)} | {r.get('vehicle_no','')} | "
                f"{float(r.get('first_weight') or 0):,.3f} kg": r["id"]
                for r in pending
            }
            sel = st.selectbox("Select pending slip", list(opts.keys()), key="ws_pending_sel")
            c_go, c_pr = st.columns([2, 1])
            if c_go.button("Complete Second Weight", type="primary", key="ws_pending_go"):
                st.session_state["ws_edit_slip_id"] = opts[sel]
                st.rerun()
            if c_pr.button("Print 1st weight slip", key="ws_pending_print"):
                st.session_state["ws_print_id"] = opts[sel]
                st.session_state["ws_pending_print_id"] = opts[sel]
                st.rerun()
            if st.session_state.get("ws_pending_print_id") == opts[sel]:
                _print_first_weight_slip(opts[sel], "ws_pending_pr")
            st.caption("Select a slip and **Complete Second Weight** to open the popup, or print the 1st-weight ticket here.")

    elif tab == "Completed Slips":
        st.markdown("**Completed slips**")
        from erp_ui.weighbridge_wizard import render_slip_to_invoice_wizard

        with st.container(border=True):
            render_slip_to_invoice_wizard(key_prefix="wb_completed_wiz")
        completed = db.get_completed_unlinked_slips()
        if not completed:
            st.caption("No completed slips waiting to be picked on an invoice.")
            c1, c2 = st.columns(2)
            if c1.button("Pending 2nd Weight", key="ws_comp_empty_pend"):
                st.session_state["ws_entry_tab"] = "Pending 2nd Weight"
                st.rerun()
            if c2.button("New first weight", type="primary", key="ws_comp_empty_new"):
                st.session_state["ws_entry_tab"] = "Weight Entry"
                st.rerun()
        else:
            from db_commercial import weight_slip_is_linked
            linked_n = sum(1 for r in completed if weight_slip_is_linked(r))
            unlinked_n = len(completed) - linked_n
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Completed Slips</p>"
                f"<p class='txn-kpi-val'>{len(completed):,}</p></div>",
                unsafe_allow_html=True,
            )
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Awaiting Invoice</p>"
                f"<p class='txn-kpi-val'>{unlinked_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            if linked_n or unlinked_n:
                parts = []
                if unlinked_n:
                    parts.append(
                        '<span class="inv-badge inv-badge-pending">Unlinked</span>&nbsp;'
                        f"<strong>{unlinked_n}</strong>"
                    )
                if linked_n:
                    parts.append(
                        '<span class="inv-badge inv-badge-approved">Linked</span>&nbsp;'
                        f"<strong>{linked_n}</strong>"
                    )
                st.markdown(
                    f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
                    unsafe_allow_html=True,
                )
            _render_weight_slip_html_table(completed, mode="completed")
            df = pd.DataFrame([{
                "Slip": r["document_no"],
                "Date": r.get("slip_date"),
                "Vehicle": r.get("vehicle_no"),
                "Party": _party_label(r),
                "Item": r.get("product_name") or "—",
                "First (kg)": f"{float(r.get('first_weight') or 0):,.3f}",
                "Second (kg)": f"{float(r.get('second_weight') or 0):,.3f}",
                "Net (kg)": f"{float(r.get('net_weight') or 0):,.3f}",
                "Bill ref": r.get("sales_invoice_no") or r.get("purchase_invoice_no") or "—",
                "Status": _slip_invoice_status(r),
            } for r in completed])
            export_buttons(df, "completed_weights", "Completed Weights")

    elif tab == "All Slips Register":
        from erp_ui import transaction_list as txn
        txn.weight_slip_register_list()

    elif tab == "Print Slip":
        rows = db.get_weight_slips_pro()
        pending_print = [r for r in rows if r.get("status") == "first_weigh"]
        done = [r for r in rows if r.get("status") == "completed"]
        if not pending_print and not done:
            st.info("No slips to print.")
        else:
            print_mode = st.radio(
                "Print",
                ["1st weight only (pending 2nd)", "Completed (final slip)"] if pending_print and done
                else (["1st weight only (pending 2nd)"] if pending_print else ["Completed (final slip)"]),
                horizontal=True,
                key="ws_print_mode",
            )
            pool = pending_print if "1st weight" in print_mode else done
            from erp_ui.list_paging import page_slice
            pool = page_slice(pool, "ws_print_pg", default_size=50)
            pre = st.session_state.get("ws_print_id")
            labels = []
            for r in pool:
                party = _party_label(r)
                if r.get("status") == "first_weigh":
                    labels.append(
                        f"{r['document_no']} — {party} — {r.get('vehicle_no', '')} — "
                        f"1st: {float(r.get('first_weight') or 0):,.0f} kg (pending)"
                    )
                else:
                    labels.append(
                        f"{r['document_no']} — {party} — {r.get('vehicle_no', '')} — "
                        f"net {float(r.get('net_weight') or 0):,.0f} kg"
                    )
            if not labels:
                st.info("No slips on this page.")
                return
            default_idx = 0
            if pre:
                for i, r in enumerate(pool):
                    if r["id"] == pre:
                        default_idx = i
                        break
            sel = st.selectbox("Slip", labels, index=default_idx, key="ws3_sel")
            if not sel:
                return
            sid = pool[labels.index(sel)]["id"]
            document_print_toolbar("Weight Slip", sid, key_prefix="ws_print")

    elif tab == "Edit / Delete":
        st.markdown(
            "**Edit or cancel weight slips.** Slips on an invoice must be **detached** first — "
            "only when the invoice is **draft**. Approved invoices: **unapprove** → detach → fix slip → "
            "re-attach on invoice → save → submit → approve again."
        )
        rows = db.get_weight_slips_pro()
        from db_commercial import (
            weight_slip_is_linked,
            list_weight_slip_invoice_attachments,
            detach_weight_slip_from_invoice,
        )
        from db_invoice_workflow import WEIGHT_SLIP_CANCELLED, _infer_reopen_status
        from erp_ui.helpers import admin_unapprove_panel

        editable = [
            r for r in rows
            if r.get("status") in ("first_weigh", "completed", WEIGHT_SLIP_CANCELLED)
        ]
        # Pending first, then completed, cancelled last (newest within each group)
        _rank = {"first_weigh": 0, "completed": 1, WEIGHT_SLIP_CANCELLED: 2}
        editable.sort(
            key=lambda r: (_rank.get(r.get("status"), 9), -(int(r.get("id") or 0))),
        )
        if not editable:
            st.info("No slips available for edit/delete.")
        else:
            from erp_ui.list_paging import page_slice
            page_rows = page_slice(editable, "ws_ed_pg", default_size=50)
            keep_id = st.session_state.get("ws_ed_focus_id")
            opts = {}
            for r in page_rows:
                st_lbl = r.get("status", "")
                if st_lbl == WEIGHT_SLIP_CANCELLED:
                    st_lbl = f"cancelled → {_infer_reopen_status(r)}"
                elif st_lbl == "first_weigh":
                    st_lbl = "pending 2nd"
                inv_ref = r.get("sales_invoice_no") or r.get("purchase_invoice_no")
                if inv_ref:
                    st_lbl = f"{st_lbl} | on {inv_ref}"
                opts[f"{r['document_no']} | {_party_label(r)} | {r.get('vehicle_no','')} | {st_lbl}"] = r
            labels = list(opts.keys())
            if not labels:
                st.info("No slips on this page.")
                return
            default_ix = 0
            if keep_id:
                for i, r in enumerate(page_rows):
                    if r["id"] == keep_id:
                        default_ix = i
                        break
                st.session_state.pop("ws_ed_focus_id", None)
            sel = st.selectbox("Select slip", labels, index=default_ix, key="ws_ed_sel")
            if not sel:
                return
            slip = opts[sel]
            sid = slip["id"]
            is_admin = user_role() == "admin"
            attachments = list_weight_slip_invoice_attachments(sid) if weight_slip_is_linked(slip) else []
            is_linked = bool(attachments) or weight_slip_is_linked(slip)
            is_cancelled = slip.get("status") == WEIGHT_SLIP_CANCELLED
            reopen_as = _infer_reopen_status(slip) if is_cancelled else slip.get("status")
            is_pending = reopen_as == "first_weigh"
            is_completed = reopen_as == "completed"

            if attachments:
                n_ref = sum(1 for a in attachments if a.get("link_role") == "reference")
                st.info(
                    f"Slip **{slip['document_no']}** is linked to **{len(attachments)}** invoice(s)"
                    + (f" (1 primary + {n_ref} reference)" if n_ref else " (**primary**).")
                )
                for attachment in attachments:
                    inv_no = attachment.get("invoice_no", "—")
                    inv_st = (attachment.get("status") or "draft").lower()
                    inv_id = attachment.get("id")
                    kind = attachment.get("kind", "sales")
                    role = attachment.get("link_role") or "primary"
                    kind_lbl = "Sales" if kind == "sales" else "Purchase"
                    edit_module = "Sales Invoices" if kind == "sales" else "Purchase Invoices"
                    role_lbl = "PRIMARY (full weight)" if role == "primary" else "REFERENCE only"

                    with st.container(border=True):
                        st.markdown(
                            f"**{kind_lbl} {inv_no}** — {role_lbl} · status **{inv_st}**"
                        )
                        if inv_st == "approved":
                            st.warning(
                                "Unapprove → detach → edit slip → re-attach on invoice → save → submit → approve."
                            )
                            admin_unapprove_panel(
                                "sale" if kind == "sales" else "purchase",
                                inv_id,
                                inv_no,
                                f"ws_detach_{sid}_{kind}_{inv_id}",
                            )
                        elif inv_st == "pending_approval":
                            st.error(
                                f"Pending approval — reject from **Sale/Purchase Approval**, "
                                "or unapprove if posted by mistake."
                            )
                        elif inv_st == "draft":
                            if st.button(
                                f"Detach {inv_no}",
                                type="primary" if role == "primary" else "secondary",
                                key=f"ws_detach_{sid}_{kind}_{inv_id}",
                            ):
                                try:
                                    detach_weight_slip_from_invoice(
                                        sid, uid(), invoice_id=inv_id, kind=kind,
                                    )
                                    st.session_state["ws_ed_focus_id"] = sid
                                    ff.action_done(
                                        f"Detached from **{inv_no}** ({role_lbl}). "
                                        f"On **{edit_module} → Edit** re-select slip if needed."
                                    )
                                except Exception as e:
                                    st.error(str(e))
                        else:
                            st.error(
                                f"Status **{inv_st}** — detach only when **draft** "
                                f"(after admin unapprove)."
                            )
                st.divider()

            if is_linked:
                st.caption(
                    "Edit/cancel unlock after **all** invoices are detached "
                    "(or detach each draft link above)."
                )
            elif is_cancelled:
                st.warning(
                    f"Slip **{slip['document_no']}** is **cancelled**. "
                    "Edit below and **Save** to reopen it, or use **Complete 2nd weight** if only 1st weight was recorded."
                )

            if not is_linked and is_pending:
                from db_invoice_workflow import UNKNOWN_PARTY_CODE, slip_party_is_unknown

                st.caption(f"Party: **{_party_label(slip)}**")
                if slip_party_is_unknown(slip):
                    st.warning("Party is UNKNOWN — set the real party below or when completing 2nd weight.")
                # Party edit outside form (smart_select uses widgets incompatible with st.form)
                is_sale_ed = bool(slip.get("customer_id")) or (slip.get("party_type") or "") == "customer"
                ptype_ed = st.selectbox(
                    "Party type",
                    ["SALE (Customer)", "PURCHASE (Supplier)"],
                    index=0 if is_sale_ed else 1,
                    key="ws_ed_ptype",
                )
                _rc = [r for r in db.get_customers(active_only=True) if str(r.get("code") or "").upper() != UNKNOWN_PARTY_CODE]
                _rs = [r for r in db.get_suppliers(active_only=True) if str(r.get("code") or "").upper() != UNKNOWN_PARTY_CODE]
                cid_ed = sid_ed = None
                keep_unknown = st.checkbox("Keep UNKNOWN for now", value=slip_party_is_unknown(slip), key="ws_ed_keep_unk")
                if not keep_unknown:
                    if str(ptype_ed).startswith("SALE"):
                        _, cid_ed, _ = smart_select(
                            "Customer account", _rc, "ws_ed_c", "id",
                            _party_fmt,
                            default_id=slip.get("customer_id") if is_sale_ed and not slip_party_is_unknown(slip) else None,
                        )
                    else:
                        _, sid_ed, _ = smart_select(
                            "Supplier account", _rs, "ws_ed_s", "id",
                            _party_fmt,
                            default_id=slip.get("supplier_id") if (not is_sale_ed) and not slip_party_is_unknown(slip) else None,
                        )
                with st.form("ws_edit_form"):
                    c1, c2 = st.columns(2)
                    vehicle = c1.text_input("Vehicle No", value=slip.get("vehicle_no") or "")
                    driver = c2.text_input("Driver Name", value=slip.get("driver_name") or "")
                    first_w = st.number_input(
                        "First Weight (kg)", min_value=0.0,
                        value=float(slip.get("first_weight") or 0), step=0.001,
                    )
                    first_t = st.text_input("First Weight Time", value=slip.get("first_weight_time") or "")
                    remarks = st.text_input("Remarks", value=slip.get("remarks") or "")
                    btn_lbl = "Save & Reopen Slip" if is_cancelled else "Update Pending Slip"
                    if st.form_submit_button(btn_lbl, type="primary"):
                        try:
                            payload = {
                                "vehicle_no": vehicle.strip().upper(),
                                "driver_name": driver,
                                "first_weight": first_w,
                                "first_weight_time": first_t,
                                "remarks": remarks,
                                "gross_weight": first_w,
                            }
                            if not keep_unknown:
                                if str(ptype_ed).startswith("SALE"):
                                    if not cid_ed:
                                        raise ValueError("Select a customer, or tick Keep UNKNOWN.")
                                    payload.update({
                                        "customer_id": cid_ed, "supplier_id": None, "party_type": "customer",
                                    })
                                else:
                                    if not sid_ed:
                                        raise ValueError("Select a supplier, or tick Keep UNKNOWN.")
                                    payload.update({
                                        "supplier_id": sid_ed, "customer_id": None, "party_type": "supplier",
                                    })
                            db.update_weight_slip(sid, payload, uid())
                            ff.action_done("Slip saved." + (" Reopened for use." if is_cancelled else ""))
                        except Exception as e:
                            st.error(str(e))
                if is_cancelled:
                    if st.button("Complete 2nd weight", key="ws_ed_goto_entry"):
                        st.session_state["ws_edit_slip_id"] = sid
                        st.rerun()

            elif not is_linked and is_completed:
                from db_invoice_workflow import UNKNOWN_PARTY_CODE, slip_party_is_unknown

                st.caption(f"Party: **{_party_label(slip)}**")
                is_sale_ed = bool(slip.get("customer_id")) or (slip.get("party_type") or "") == "customer"
                ptype_ed = st.selectbox(
                    "Party type",
                    ["SALE (Customer)", "PURCHASE (Supplier)"],
                    index=0 if is_sale_ed else 1,
                    key="ws_edc_ptype",
                )
                _rc = [r for r in db.get_customers(active_only=True) if str(r.get("code") or "").upper() != UNKNOWN_PARTY_CODE]
                _rs = [r for r in db.get_suppliers(active_only=True) if str(r.get("code") or "").upper() != UNKNOWN_PARTY_CODE]
                cid_ed = sid_ed = None
                if str(ptype_ed).startswith("SALE"):
                    _, cid_ed, _ = smart_select(
                        "Customer account", _rc, "ws_edc_c", "id",
                        _party_fmt,
                        default_id=slip.get("customer_id") if is_sale_ed else None,
                    )
                else:
                    _, sid_ed, _ = smart_select(
                        "Supplier account", _rs, "ws_edc_s", "id",
                        _party_fmt,
                        default_id=slip.get("supplier_id") if not is_sale_ed else None,
                    )
                with st.form("ws_edit_completed_form"):
                    c1, c2 = st.columns(2)
                    vehicle = c1.text_input("Vehicle No", value=slip.get("vehicle_no") or "")
                    driver = c2.text_input("Driver Name", value=slip.get("driver_name") or "")
                    first_w = st.number_input(
                        "First Weight (kg)", min_value=0.0,
                        value=float(slip.get("first_weight") or 0), step=0.001,
                    )
                    second_w = st.number_input(
                        "Second Weight (kg)", min_value=0.0,
                        value=float(slip.get("second_weight") or 0), step=0.001,
                    )
                    first_t = st.text_input("First Weight Time", value=slip.get("first_weight_time") or "")
                    second_t = st.text_input("Second Weight Time", value=slip.get("second_weight_time") or "")
                    remarks = st.text_input("Remarks", value=slip.get("remarks") or "")
                    st.metric("Net Weight", f"{_calc_net(first_w, second_w):,.3f} kg")
                    btn_lbl = "Save & Reopen Completed Slip" if is_cancelled else "Update Completed Slip"
                    if st.form_submit_button(btn_lbl, type="primary"):
                        try:
                            payload = {
                                "vehicle_no": vehicle.strip().upper(),
                                "driver_name": driver,
                                "first_weight": first_w,
                                "second_weight": second_w,
                                "first_weight_time": first_t,
                                "second_weight_time": second_t,
                                "remarks": remarks,
                            }
                            if str(ptype_ed).startswith("SALE"):
                                if not cid_ed:
                                    raise ValueError("Select a customer.")
                                payload.update({
                                    "customer_id": cid_ed, "supplier_id": None, "party_type": "customer",
                                })
                            else:
                                if not sid_ed:
                                    raise ValueError("Select a supplier.")
                                payload.update({
                                    "supplier_id": sid_ed, "customer_id": None, "party_type": "supplier",
                                })
                            db.update_weight_slip(sid, payload, uid())
                            ff.action_done("Slip saved." + (" Reopened for use." if is_cancelled else ""))
                        except Exception as e:
                            st.error(str(e))

            if not is_linked:
                st.divider()
            reason = st.text_input("Cancel reason (optional)", key="ws_cancel_r")
            c1, c2 = st.columns(2)
            if c1.button("Cancel Slip", key="ws_cancel_btn", disabled=is_cancelled or is_linked):
                try:
                    db.cancel_weight_slip(sid, uid(), reason)
                    st.session_state["ws_ed_focus_id"] = sid
                    ff.action_done(f"Slip **{slip['document_no']}** cancelled — it remains in this list. "
                        "Edit and save to reopen, or complete 2nd weight from Pending.")
                except Exception as e:
                    st.error(str(e))
            if c2.button("Delete Slip (Admin)", key="ws_del_btn", disabled=not is_admin or is_linked):
                try:
                    db.delete_weight_slip(sid, uid())
                    ff.action_done("Slip deleted.")
                except Exception as e:
                    st.error(str(e))
            if not is_admin:
                st.caption("Only administrators can permanently delete slips.")


def page_weight_reports():
    from html import escape

    std_page_header("Weight Reports", status="register", status_kind="shell")
    c1, c2 = st.columns(2)
    fd, td = str(c1.date_input("From", value=date.today().replace(day=1))), str(c2.date_input("To", value=date.today()))
    pending_n = len(db.get_all_pending_weight_slips())
    completed_today = len([
        r for r in db.get_weight_slips_pro(str(date.today()), str(date.today()))
        if r.get("status") == "completed"
    ])
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Pending 2nd Weight</p>"
        f"<p class='txn-kpi-val'>{pending_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Completed Today</p>"
        f"<p class='txn-kpi-val'>{completed_today:,}</p></div>",
        unsafe_allow_html=True,
    )
    rows = db.get_weight_slips_pro(fd, td)
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Slips in Period</p>"
        f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    if rows:
        first_n = sum(1 for r in rows if r.get("status") == "first_weigh")
        done_n = sum(1 for r in rows if r.get("status") == "completed")
        if first_n or done_n:
            parts = []
            if first_n:
                parts.append(
                    '<span class="inv-badge inv-badge-pending">Pending 2nd</span>&nbsp;'
                    f"<strong>{first_n}</strong>"
                )
            if done_n:
                parts.append(
                    '<span class="inv-badge inv-badge-approved">Completed</span>&nbsp;'
                    f"<strong>{done_n}</strong>"
                )
            st.markdown(
                f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
                unsafe_allow_html=True,
            )
        ths = "".join(
            f"<th>{h}</th>"
            for h in ("Slip", "Date", "Status", "Party", "Vehicle", "Item", "Net (kg)", "Invoice")
        )
        body = []
        for r in rows:
            party = _party_label(r)
            inv = r.get("sales_invoice_no") or r.get("purchase_invoice_no") or "—"
            st_key = r.get("status") or "draft"
            if st_key == "first_weigh":
                badge = _weight_slip_status_badge("pending")
            elif st_key == "completed":
                badge = '<span class="inv-badge inv-badge-approved">Completed</span>'
            else:
                badge = _weight_slip_status_badge(st_key)
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('document_no') or ''))}</td>"
                f"<td>{escape(str(r.get('slip_date') or ''))}</td>"
                f"<td class='txn-status-cell'>{badge}</td>"
                f"<td>{escape(party)}</td>"
                f"<td>{escape(str(r.get('vehicle_no') or ''))}</td>"
                f"<td>{escape(str(r.get('product_name') or '—'))}</td>"
                f"<td class='txn-num'>{float(r.get('net_weight') or 0):,.3f}</td>"
                f"<td>{escape(str(inv))}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        df = pd.DataFrame(rows)
        show = [c for c in [
            "document_no", "slip_date", "status", "customer_name", "supplier_name",
            "vehicle_no", "driver_name", "product_name",
            "first_weight", "second_weight", "net_weight",
            "first_weight_time", "second_weight_time", "print_time",
            "sales_invoice_no", "purchase_invoice_no",
        ] if c in df.columns]
        export_buttons(df[show], "weight_scale_report", "Weight Scale Report")
    else:
        st.info("No data.")
