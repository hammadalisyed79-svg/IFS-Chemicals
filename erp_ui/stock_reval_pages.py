"""Stock Revaluation UI — reset on-hand value at last purchase or manual rate."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import fmt_money, std_page_header, uid


def page_stock_revaluation():
    from erp_ui.helpers import sticky_page_tabs

    std_page_header("Stock Revaluation", status="posted", status_kind="shell")
    tab = sticky_page_tabs(["New Revaluation", "History"], "srv_tab")

    wh_list = db.get_warehouses()
    wh_opts = {f"{w['code']} — {w['name']}": w["id"] for w in wh_list}
    if not wh_opts:
        st.warning("Create a warehouse first.")
        return

    if tab == "New Revaluation":
        c1, c2, c3 = st.columns(3)
        reval_date = c1.date_input("Date", value=date.today(), key="srv_date")
        wh_lbl = c2.selectbox("Warehouse", list(wh_opts.keys()), key="srv_wh")
        rate_mode = c3.selectbox(
            "Rate source",
            ["last_purchase", "manual"],
            format_func=lambda x: "Last purchase rate" if x == "last_purchase" else "Manual (edit below)",
            key="srv_mode",
        )
        notes = st.text_input("Notes", key="srv_notes")
        wh_id = wh_opts[wh_lbl]

        if st.button("Load stock lines", key="srv_load"):
            lines = db.preview_revaluation_lines(wh_id, rate_mode)
            st.session_state["srv_lines"] = lines
            st.session_state["srv_wh_id"] = wh_id
            st.session_state["srv_rate_mode"] = rate_mode

        lines = st.session_state.get("srv_lines") or []
        if not lines:
            st.info("Click **Load stock lines** to preview qty, old rate, new rate, and value delta.")
        else:
            df = pd.DataFrame([{
                "Code": L["code"],
                "Product": L["name"],
                "Qty": L["qty"],
                "Old Rate": L["old_rate"],
                "New Rate": L["new_rate"],
                "Delta Value": L["delta_value"],
                "Source": L["rate_source"],
                "product_id": L["product_id"],
            } for L in lines])
            edited = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                disabled=["Code", "Product", "Qty", "Old Rate", "Delta Value", "Source", "product_id"]
                if rate_mode != "manual"
                else ["Code", "Product", "Qty", "Old Rate", "Delta Value", "Source", "product_id"],
                column_config={
                    "New Rate": st.column_config.NumberColumn(min_value=0.0, format="%.4f"),
                    "product_id": None,
                },
                key="srv_editor",
            )
            # Recompute deltas if manual edits
            out_lines = []
            for _, row in edited.iterrows():
                qty = float(row["Qty"] or 0)
                old = float(row["Old Rate"] or 0)
                new = float(row["New Rate"] or 0)
                out_lines.append({
                    "product_id": int(row["product_id"]),
                    "qty": qty,
                    "old_rate": old,
                    "new_rate": new,
                    "delta_value": round(qty * (new - old), 2),
                    "rate_source": rate_mode,
                })
            total_delta = sum(L["delta_value"] for L in out_lines)
            st.metric("Total value delta", fmt_money(total_delta))

            b1, b2 = st.columns(2)
            if b1.button("Save draft", key="srv_save"):
                try:
                    rid = db.save_stock_revaluation(
                        {
                            "reval_date": str(reval_date),
                            "warehouse_id": st.session_state.get("srv_wh_id") or wh_id,
                            "rate_mode": st.session_state.get("srv_rate_mode") or rate_mode,
                            "notes": notes,
                        },
                        out_lines,
                        None,
                        uid(),
                    )
                    st.success(f"Draft saved (id {rid}). Post from History or below.")
                    st.session_state["srv_draft_id"] = rid
                except Exception as e:
                    st.error(str(e))
            if b2.button("Save & Post", type="primary", key="srv_post"):
                try:
                    rid = db.save_stock_revaluation(
                        {
                            "reval_date": str(reval_date),
                            "warehouse_id": st.session_state.get("srv_wh_id") or wh_id,
                            "rate_mode": st.session_state.get("srv_rate_mode") or rate_mode,
                            "notes": notes,
                        },
                        out_lines,
                        None,
                        uid(),
                    )
                    delta = db.post_stock_revaluation(rid, uid())
                    st.session_state.pop("srv_lines", None)
                    ff.action_done(f"Posted. Inventory value change: {fmt_money(delta)}")
                except Exception as e:
                    st.error(str(e))

    elif tab == "History":
        from erp_ui.helpers import render_dataframe_html_table
        rows = db.get_stock_revaluations()
        if not rows:
            st.info("No revaluations yet.")
            return
        k1, k2 = st.columns(2, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Revaluations</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        posted_n = sum(1 for r in rows if (r.get("status") or "").lower() == "posted")
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Posted</p>"
            f"<p class='txn-kpi-val'>{posted_n:,}</p></div>",
            unsafe_allow_html=True,
        )
        hist_df = pd.DataFrame([{
            "Document": r["document_no"],
            "Date": r["reval_date"],
            "Warehouse": r.get("warehouse_name") or r.get("warehouse_code"),
            "Mode": r.get("rate_mode"),
            "Delta": r.get("total_delta"),
            "Status": r.get("status"),
        } for r in rows])
        render_dataframe_html_table(hist_df)
        drafts = [r for r in rows if r.get("status") == "draft"]
        if drafts:
            opts = {f"{r['document_no']} — {r['reval_date']}": r["id"] for r in drafts}
            sel = st.selectbox("Post draft", list(opts.keys()), key="srv_post_sel")
            c_post, c_cancel_d = st.columns(2)
            if c_post.button("Post selected", type="primary", key="srv_post_hist"):
                try:
                    delta = db.post_stock_revaluation(opts[sel], uid())
                    ff.action_done(f"Posted. Delta: {fmt_money(delta)}")
                except Exception as e:
                    st.error(str(e))
            if c_cancel_d.button("Cancel draft", key="srv_cancel_draft"):
                try:
                    db.cancel_stock_revaluation(opts[sel], uid())
                    ff.action_done("Draft cancelled.")
                except Exception as e:
                    st.error(str(e))

        posted = [r for r in rows if r.get("status") == "posted"]
        if posted:
            st.divider()
            popts = {f"{r['document_no']} — {r['reval_date']} (delta {r.get('total_delta')})": r["id"] for r in posted}
            psel = st.selectbox("Reverse posted revaluation", list(popts.keys()), key="srv_rev_sel")
            if st.button("Cancel & reverse GL", type="secondary", key="srv_cancel_posted"):
                try:
                    db.cancel_stock_revaluation(popts[psel], uid())
                    ff.action_done("Revaluation cancelled — old rates restored and GL reversed.")
                except Exception as e:
                    st.error(str(e))
