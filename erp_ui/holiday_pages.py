"""Administration — weekly off-days and gazetted holidays."""

from datetime import date
import streamlit as st
from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import uid, std_page_header, sticky_page_tabs


def page_holidays():
    std_page_header("Holidays", status="register", status_kind="shell")
    if st.session_state.get("user", {}).get("role") != "admin":
        st.warning("Only administrators can change the holiday calendar.")
        st.stop()

    tab = sticky_page_tabs(["Weekly off-days", "Gazetted holidays"], "holiday_page_tab")

    if tab == "Weekly off-days":
        st.caption("Selected weekdays repeat every week (e.g. Sunday weekly off).")
        current = db.get_weekly_holidays()
        cols = st.columns(7)
        picks = []
        from db_holidays import WEEKDAY_LABELS
        for i, (label, wd) in enumerate(WEEKDAY_LABELS):
            if cols[i].checkbox(label, value=wd in current, key=f"hol_wd_{wd}"):
                picks.append(wd)
        if st.button("Save weekly off-days", type="primary", key="hol_save_weekly"):
            db.save_weekly_holidays(picks, uid())
            ff.action_done("Weekly holidays saved.")

    elif tab == "Gazetted holidays":
        st.caption("One-off dates use the full year. Annual holidays repeat every year on the same month and day.")
        with st.form("hol_add_gaz"):
            c1, c2, c3 = st.columns([1.2, 2, 1])
            hd = c1.date_input("Date", value=date.today(), key="hol_gaz_date")
            nm = c2.text_input("Holiday name", placeholder="e.g. Eid ul-Fitr", key="hol_gaz_name")
            annual = c3.checkbox("Every year", value=False, key="hol_gaz_annual")
            if st.form_submit_button("Add holiday"):
                try:
                    db.add_gazetted_holiday(hd, nm, is_annual=annual, user_id=uid())
                    ff.action_done("Holiday added.")
                except Exception as e:
                    st.error(str(e))

        rows = db.list_gazetted_holidays()
        if not rows:
            st.info("No gazetted holidays defined yet.")
        else:
            for r in rows:
                c1, c2, c3 = st.columns([2, 3, 1])
                tag = " (annual)" if r.get("is_annual") else ""
                c1.write(r["holiday_date"])
                c2.write(f"{r['name']}{tag}")
                if c3.button("Remove", key=f"hol_del_{r['id']}"):
                    db.delete_gazetted_holiday(r["id"])
                    st.rerun()
