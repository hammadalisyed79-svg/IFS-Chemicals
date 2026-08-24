"""Fiscal year setup, pre-close checklist, and year-end closing."""

from datetime import date
import pandas as pd
import streamlit as st
from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import uid, std_page_header, fmt_money, user_role, sticky_page_tabs, render_dataframe_html_table


def _fy_status_label(fy):
    if fy.get("is_closed"):
        return "closed"
    if fy.get("is_active"):
        return "active"
    return "open"


def page_fiscal_year_closing():
    peek = st.session_state.get("fy_page_tab") or "Fiscal Years"
    std_page_header(
        "Fiscal Year Closing",
        status="register" if peek == "Fiscal Years" else None,
        status_kind="shell",
    )
    tab = sticky_page_tabs(["Fiscal Years", "Close Year", "Audit Log"], "fy_page_tab")

    if tab == "Fiscal Years":
        active = db.get_active_fiscal_year()
        if active:
            st.success(
                f"**Active fiscal year:** {active['fy_code']} "
                f"({active['start_date']} → {active['end_date']})"
            )
        else:
            st.warning("No active open fiscal year — create one or activate an existing year.")

        rows = db.get_fiscal_years()
        if rows:
            df = pd.DataFrame([{
                "Code": r["fy_code"],
                "Start": r["start_date"],
                "End": r["end_date"],
                "Status": _fy_status_label(r),
                "Net P/L": r.get("net_profit") if r.get("is_closed") else None,
                "P&L Ref": r.get("pl_close_ref") or "—",
                "Closed At": (r.get("closed_at") or "—")[:16],
            } for r in rows])
            render_dataframe_html_table(df)
        else:
            st.info("No fiscal years defined yet.")

        st.divider()
        st.subheader("Create Fiscal Year")
        code, start, end = db.suggest_next_fiscal_year()
        c1, c2, c3 = st.columns(3)
        fy_code = c1.text_input("FY Code", value=code, key="fy_new_code")
        fy_start = c2.date_input("Start Date", value=date.fromisoformat(start), key="fy_new_start")
        fy_end = c3.date_input("End Date", value=date.fromisoformat(end), key="fy_new_end")
        make_active = st.checkbox("Set as active fiscal year", value=True, key="fy_new_active")
        if st.button("Create Fiscal Year", type="primary", key="fy_create"):
            try:
                db.create_fiscal_year(
                    fy_code, str(fy_start), str(fy_end), uid(), make_active=make_active,
                )
                ff.action_done(f"Fiscal year **{fy_code}** created.")
            except Exception as e:
                st.error(str(e))

        open_years = [r for r in rows if not r.get("is_closed")]
        if open_years:
            st.divider()
            st.subheader("Activate Fiscal Year")
            opts = {f"{r['fy_code']} ({r['start_date']} → {r['end_date']})": r["id"] for r in open_years}
            pick = st.selectbox("Select year to activate", list(opts.keys()), key="fy_activate_sel")
            if st.button("Set Active", key="fy_activate_btn"):
                try:
                    db.set_active_fiscal_year(opts[pick], uid())
                    ff.action_done("Active fiscal year updated.")
                except Exception as e:
                    st.error(str(e))

    elif tab == "Close Year":
        years = db.get_fiscal_years()
        open_years = [r for r in years if not r.get("is_closed")]
        if not open_years:
            st.info("All fiscal years are closed. Create a new fiscal year to continue operations.")
            closed = [r for r in years if r.get("is_closed")]
            if closed and user_role() == "admin":
                st.divider()
                st.subheader("Reopen Closed Year (Administrator)")
                ro_opts = {f"{r['fy_code']} ({r['start_date']} → {r['end_date']})": r["id"] for r in closed}
                ro_lbl = st.selectbox("Closed year", list(ro_opts.keys()), key="fy_reopen_sel")
                reason = st.text_input("Reason for reopen", key="fy_reopen_reason")
                if st.button("Reopen Fiscal Year", key="fy_reopen_btn"):
                    try:
                        code = db.reopen_fiscal_year(ro_opts[ro_lbl], uid(), reason)
                        ff.action_done(f"Fiscal year **{code}** reopened — posting allowed again for that period.")
                    except Exception as e:
                        st.error(str(e))
            return

        fy_opts = {f"{r['fy_code']} ({r['start_date']} → {r['end_date']})": r["id"] for r in open_years}
        sel_lbl = st.selectbox("Fiscal year to close", list(fy_opts.keys()), key="fy_close_sel")
        fy_id = fy_opts[sel_lbl]
        chk = db.get_fiscal_close_checklist(fy_id)
        fy = chk["fiscal_year"]

        st.markdown(f"### Pre-close checklist — **{fy['fy_code']}**")
        st.caption(f"Period: {fy['start_date']} to {fy['end_date']}")

        def _row(ok, label, detail=""):
            icon = "✅" if ok else "❌"
            st.markdown(f"{icon} **{label}**" + (f" — {detail}" if detail else ""))

        _row(chk["draft_sales"] == 0, "No draft/rejected sales invoices", f"{chk['draft_sales']} open")
        _row(chk["pending_sales"] == 0, "No sales pending approval", f"{chk['pending_sales']} pending")
        _row(chk["draft_purchases"] == 0, "No draft/rejected purchase invoices", f"{chk['draft_purchases']} open")
        _row(chk["pending_purchases"] == 0, "No purchases pending approval", f"{chk['pending_purchases']} pending")
        _row(chk["draft_journals"] == 0, "No draft journal vouchers", f"{chk['draft_journals']} draft")
        _row(chk["draft_grn"] == 0, "No draft GRNs", f"{chk['draft_grn']} draft")
        _row(
            chk["trial_balance_ok"],
            "General ledger balanced for period",
            f"Dr {fmt_money(chk['gl_debits'])} / Cr {fmt_money(chk['gl_credits'])}",
        )
        _row(
            abs(chk["ar_difference"]) < 0.01,
            "AR control matches customer sub-ledger",
            f"Diff {fmt_money(chk['ar_difference'])}",
        )
        _row(
            abs(chk["ap_difference"]) < 0.01,
            "AP control matches supplier sub-ledger",
            f"Diff {fmt_money(chk['ap_difference'])}",
        )
        _row(
            chk["pl_already_closed"] or abs(chk["net_profit"]) < 0.01,
            "P&L transfer",
            "Already posted" if chk["pl_already_closed"] else f"Net {fmt_money(chk['net_profit'])} to transfer",
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Net Profit / (Loss)", fmt_money(chk["net_profit"]))
        m2.metric("GL Debits", fmt_money(chk["gl_debits"]))
        m3.metric("GL Credits", fmt_money(chk["gl_credits"]))

        if chk["blockers"]:
            st.error("**Resolve before closing:**\n\n" + "\n".join(f"• {b}" for b in chk["blockers"]))

        st.divider()
        st.markdown("""
**Closing will:**
1. Post net P&L to **Retained Earnings** (accounts configured in Chart of Accounts → Posting Setup)
2. Mark the fiscal year **closed** and remove active status
3. **Block** new invoices, cash/bank entries, and GL postings dated in this period
        """)
        close_desc = st.text_input("Closing notes (optional)", key="fy_close_desc")
        transfer_pl = st.checkbox("Transfer P&L to retained earnings", value=True, key="fy_close_pl")
        if st.button(
            "Close Fiscal Year",
            type="primary",
            key="fy_close_btn",
            disabled=not chk["can_close"],
        ):
            try:
                res = db.close_fiscal_year(fy_id, uid(), close_desc, transfer_pl=transfer_pl)
                msg = f"Fiscal year **{res['fy_code']}** closed."
                if res.get("pl_close"):
                    msg += f" P&L reference **{res['pl_close']['reference_no']}** ({fmt_money(res['net_profit'])})."
                st.balloons()
                ff.action_done(msg)
            except Exception as e:
                st.error(str(e))

        st.caption(
            "After closing, create the next fiscal year under **Fiscal Years** tab and set it active."
        )

    elif tab == "Audit Log":
        st.caption("Fiscal year close/reopen only. For all system activity see **Administration → Audit Log**.")
        logs = db.get_fiscal_closure_log(limit=100)
        if logs:
            df = pd.DataFrame([{
                "When": (r.get("created_at") or "")[:19],
                "FY": r.get("fy_code"),
                "Action": r.get("action", "").title(),
                "User": r.get("user_name") or "—",
                "Reason": r.get("reason") or "",
            } for r in logs])
            render_dataframe_html_table(df)
        else:
            st.info("No fiscal closure events yet.")
