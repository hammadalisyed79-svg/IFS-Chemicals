"""Daily attendance — bulk sheet for 150+ employees."""

from datetime import date, timedelta
import pandas as pd
import streamlit as st
from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import uid, smart_select, std_page_header, export_buttons, sticky_page_tabs, render_dataframe_html_table

STATUSES = db.ATTENDANCE_STATUSES if hasattr(db, "ATTENDANCE_STATUSES") else [
    "present", "absent", "leave", "late", "overtime", "half_day",
]
STATUS_LABELS = {s: s.replace("_", " ").title() for s in STATUSES}


def _load_employees(search=None, department=None):
    emps = db.get_employees_hr(active_only=True, search=search) if hasattr(db, "get_employees_hr") else db.get_employees()
    if department and department != "All":
        emps = [
            e for e in emps
            if (e.get("department_name") or e.get("department") or "Unassigned") == department
        ]
    return emps


def _dept_options(emps):
    depts = sorted({
        e.get("department_name") or e.get("department") or "Unassigned"
        for e in emps
    })
    return ["All"] + depts


def _build_sheet(emps, existing_map, force_status=None):
    rows = []
    for e in emps:
        ex = existing_map.get(e["id"], {})
        if force_status:
            status = force_status
        else:
            status = ex.get("status") or "present"
        rows.append({
            "employee_id": e["id"],
            "code": e.get("code", ""),
            "name": e.get("full_name") or e.get("name", ""),
            "department": e.get("department_name") or e.get("department") or "—",
            "status": status,
            "overtime_hrs": float(ex.get("overtime_hrs") or 0),
            "late_mins": float(ex.get("late_mins") or 0),
            "notes": ex.get("notes") or "",
        })
    return pd.DataFrame(rows)


def _attendance_status_badge(status: str) -> str:
    key = (status or "present").lower()
    css = {
        "present": "inv-badge-approved",
        "absent": "inv-badge-rejected",
        "leave": "inv-badge-pending",
        "late": "inv-badge-pending",
        "overtime": "inv-badge-approved",
        "half_day": "inv-badge-draft",
    }.get(key, "inv-badge-draft")
    label = STATUS_LABELS.get(key, key.replace("_", " ").title())
    return f'<span class="inv-badge {css}">{label}</span>'


def _render_attendance_register_table(rows):
    from html import escape

    if not rows:
        return
    df = pd.DataFrame([{
        "Date": r.get("att_date"),
        "Code": r.get("employee_code", ""),
        "Employee": r.get("employee_name", ""),
        "Status": STATUS_LABELS.get(r.get("status"), r.get("status", "")),
        "OT (hrs)": float(r.get("overtime_hrs") or 0),
        "Late (min)": float(r.get("late_mins") or 0),
        "Notes": r.get("notes") or "",
        "_status_key": r.get("status"),
    } for r in rows])
    present_n = sum(1 for r in rows if (r.get("status") or "") == "present")
    absent_n = sum(1 for r in rows if (r.get("status") or "") == "absent")
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Records</p>"
        f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Present</p>"
        f"<p class='txn-kpi-val'>{present_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Absent</p>"
        f"<p class='txn-kpi-val'>{absent_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    ths = "".join(f"<th>{h}</th>" for h in ("Date", "Code", "Employee", "Status", "OT (hrs)", "Late (min)", "Notes"))
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('att_date') or ''))}</td>"
            f"<td>{escape(str(r.get('employee_code') or r.get('emp_code') or ''))}</td>"
            f"<td>{escape(str(r.get('employee_name') or ''))}</td>"
            f"<td class='txn-status-cell'>{_attendance_status_badge(r.get('status'))}</td>"
            f"<td class='txn-num'>{float(r.get('overtime_hrs') or 0):,.1f}</td>"
            f"<td class='txn-num'>{float(r.get('late_mins') or 0):,.0f}</td>"
            f"<td>{escape(str(r.get('notes') or '—'))}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    return df.drop(columns=["_status_key"], errors="ignore")


def _summary_counts(df):
    if df is None or df.empty:
        return {}
    vc = df["status"].value_counts()
    return {s: int(vc.get(s, 0)) for s in STATUSES}


def _daily_sheet_tab():
    st.markdown("**Daily attendance sheet** — edit all employees for one date, then save once.")

    nav = st.columns([1, 1, 1, 2])
    ds_key = "att_bulk_date"
    if ds_key not in st.session_state:
        st.session_state[ds_key] = date.today()
    if nav[0].button("◀ Previous Day", key="att_prev"):
        st.session_state[ds_key] -= timedelta(days=1)
        st.session_state.pop("att_preset", None)
        st.rerun()
    if nav[1].button("Today", key="att_today"):
        st.session_state[ds_key] = date.today()
        st.session_state.pop("att_preset", None)
        st.rerun()
    if nav[2].button("Next Day ▶", key="att_next"):
        st.session_state[ds_key] += timedelta(days=1)
        st.session_state.pop("att_preset", None)
        st.rerun()
    att_date = nav[3].date_input("Attendance Date", value=st.session_state[ds_key], key=ds_key)
    ds = str(att_date)

    all_emps = _load_employees()
    if not all_emps:
        st.warning("Add employees first under **HR → Employees**.")
        return

    f1, f2, f3 = st.columns([2, 1.5, 1])
    search = f1.text_input("Search", placeholder="Code, name, mobile…", key="att_search")
    dept = f2.selectbox("Department", _dept_options(all_emps), key="att_dept")
    show_only = f3.selectbox("Show", ["All employees", "Not yet saved today", "Already marked"], key="att_show")

    emps = _load_employees(search=search or None, department=dept)
    existing_map = db.get_attendance_map_for_date(ds) if hasattr(db, "get_attendance_map_for_date") else {
        r["employee_id"]: r for r in db.get_attendance(ds, ds)
    }

    if show_only == "Not yet saved today":
        emps = [e for e in emps if e["id"] not in existing_map]
    elif show_only == "Already marked":
        emps = [e for e in emps if e["id"] in existing_map]

    if not emps:
        st.info("No employees match your filters.")
        return

    preset = st.session_state.pop("att_preset", None)
    df = _build_sheet(emps, existing_map, force_status=preset)

    counts = _summary_counts(df)
    marked_today = len([e for e in all_emps if e["id"] in existing_map])
    k1, k2, k3, k4, k5, k6 = st.columns(6, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>In View</p>"
        f"<p class='txn-kpi-val'>{len(emps):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Saved Today</p>"
        f"<p class='txn-kpi-val'>{marked_today}/{len(all_emps)}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Present</p>"
        f"<p class='txn-kpi-val'>{counts.get('present', 0):,}</p></div>",
        unsafe_allow_html=True,
    )
    k4.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Absent</p>"
        f"<p class='txn-kpi-val'>{counts.get('absent', 0):,}</p></div>",
        unsafe_allow_html=True,
    )
    k5.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Leave</p>"
        f"<p class='txn-kpi-val'>{counts.get('leave', 0):,}</p></div>",
        unsafe_allow_html=True,
    )
    k6.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Late / OT</p>"
        f"<p class='txn-kpi-val'>{counts.get('late', 0) + counts.get('overtime', 0):,}</p></div>",
        unsafe_allow_html=True,
    )

    qa = st.columns([1, 1, 1, 2])
    if qa[0].button("✓ All Present", key="att_all_pres"):
        st.session_state["att_preset"] = "present"
        st.rerun()
    if qa[1].button("✗ All Absent", key="att_all_abs"):
        st.session_state["att_preset"] = "absent"
        st.rerun()
    if qa[2].button("Leave All", key="att_all_leave"):
        st.session_state["att_preset"] = "leave"
        st.rerun()
    qa[3].caption("Quick-fill applies to the filtered list below, then click **Save All**.")

    edited = st.data_editor(
        df,
        column_config={
            "employee_id": None,
            "code": st.column_config.TextColumn("Code", disabled=True, width="small"),
            "name": st.column_config.TextColumn("Employee", disabled=True, width="large"),
            "department": st.column_config.TextColumn("Department", disabled=True, width="medium"),
            "status": st.column_config.SelectboxColumn(
                "Status", options=STATUSES, required=True, width="medium",
            ),
            "overtime_hrs": st.column_config.NumberColumn("OT (hrs)", min_value=0, step=0.5, format="%.1f"),
            "late_mins": st.column_config.NumberColumn("Late (min)", min_value=0, step=1, format="%.0f"),
            "notes": st.column_config.TextColumn("Notes", width="medium"),
        },
        hide_index=True,
        use_container_width=True,
        height=min(640, 80 + len(df) * 35),
        key=f"att_editor_{ds}_{dept}_{search}_{show_only}",
    )

    c1, c2 = st.columns([1, 3])
    if c1.button("Save All Attendance", type="primary", key="att_save_bulk"):
        records = []
        for _, row in edited.iterrows():
            records.append({
                "employee_id": int(row["employee_id"]),
                "status": row["status"],
                "overtime_hrs": float(row.get("overtime_hrs") or 0),
                "late_mins": float(row.get("late_mins") or 0),
                "notes": row.get("notes") or "",
            })
        try:
            n = db.bulk_save_attendance(ds, records, uid())
            ff.action_done(f"Saved attendance for **{n}** employee(s) on **{ds}**.")
        except Exception as e:
            st.error(str(e))
    c2.caption(
        f"Tip: filter by department for large teams. "
        f"Total active staff: **{len(all_emps)}**."
    )


def _quick_entry_tab():
    st.caption("Use for one-off corrections — bulk entry is on **Daily Sheet**.")
    att_date = st.date_input("Date", value=date.today(), key="att_q_date")
    emps = db.get_employees_hr() if hasattr(db, "get_employees_hr") else db.get_employees()
    _, eid, _ = smart_select(
        "Employee", emps, "att_q_emp", "id",
        lambda r: f"{r['code']} - {r.get('full_name', r.get('name', ''))}",
    )
    if not eid:
        return
    existing = db.get_attendance(str(att_date), str(att_date), eid)
    cur = existing[0] if existing else {}
    with st.form("att_quick"):
        status = st.selectbox(
            "Status", STATUSES,
            index=STATUSES.index(cur["status"]) if cur.get("status") in STATUSES else 0,
            format_func=lambda x: STATUS_LABELS.get(x, x),
        )
        c1, c2 = st.columns(2)
        ot = c1.number_input("Overtime Hours", min_value=0.0, value=float(cur.get("overtime_hrs") or 0))
        late = c2.number_input("Late (minutes)", min_value=0.0, value=float(cur.get("late_mins") or 0))
        notes = st.text_input("Notes", value=cur.get("notes") or "")
        if st.form_submit_button("Save", type="primary"):
            db.save_attendance({
                "employee_id": eid, "att_date": str(att_date), "status": status,
                "overtime_hrs": ot, "late_mins": late, "notes": notes,
            }, uid())
            ff.action_done("Attendance saved.")


def _register_tab():
    c1, c2, c3 = st.columns([1, 1, 2])
    fd = str(c1.date_input("From", value=date.today().replace(day=1), key="att_reg_fd"))
    td = str(c2.date_input("To", value=date.today(), key="att_reg_td"))
    dept = c3.selectbox("Department", _dept_options(_load_employees()), key="att_reg_dept")
    rows = db.get_attendance(fd, td)
    if dept != "All":
        emps = {e["id"] for e in _load_employees(department=dept)}
        rows = [r for r in rows if r.get("employee_id") in emps]
    if not rows:
        st.info("No attendance records for this period.")
        return
    df = pd.DataFrame([{
        "Date": r["att_date"],
        "Code": r.get("emp_code", ""),
        "Employee": r.get("employee_name", ""),
        "Status": STATUS_LABELS.get(r.get("status"), r.get("status", "")),
        "OT (hrs)": float(r.get("overtime_hrs") or 0),
        "Late (min)": float(r.get("late_mins") or 0),
        "Notes": r.get("notes") or "",
    } for r in rows])
    export_df = _render_attendance_register_table(rows)
    export_buttons(export_df if export_df is not None else df, "attendance_register", "Attendance Register")
    st.divider()
    st.subheader("Summary by employee")
    summary = df.groupby("Employee").agg(
        Days=("Date", "count"),
        Present=("Status", lambda s: (s == "Present").sum()),
        Absent=("Status", lambda s: (s == "Absent").sum()),
        Leave=("Status", lambda s: (s == "Leave").sum()),
        OT_Hours=("OT (hrs)", "sum"),
    ).reset_index()
    render_dataframe_html_table(summary)


def page_attendance_simple():
    peek = st.session_state.get("att_simple_tab") or "Daily Sheet"
    std_page_header(
        "Attendance",
        status="register" if peek == "Register" else None,
        status_kind="shell" if peek == "Register" else "invoice",
    )
    tab = sticky_page_tabs(
        ["Daily Sheet", "Quick Entry", "Register", "Overtime Report"],
        "att_simple_tab",
    )

    if tab == "Daily Sheet":
        _daily_sheet_tab()
    elif tab == "Quick Entry":
        _quick_entry_tab()
    elif tab == "Register":
        _register_tab()
    elif tab == "Overtime Report":
        c1, c2 = st.columns(2)
        fd, td = str(c1.date_input("From", key="otf")), str(c2.date_input("To", key="ott"))
        rows = db.report_overtime(fd, td)
        if rows:
            df = pd.DataFrame([{
                "Code": r.get("code", ""),
                "Employee": r.get("full_name", ""),
                "Total OT (hrs)": float(r.get("total_overtime_hrs") or 0),
                "Days with OT": int(r.get("days") or 0),
            } for r in rows])
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Employees with OT</p>"
                f"<p class='txn-kpi-val'>{len(df):,}</p></div>",
                unsafe_allow_html=True,
            )
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Total OT Hours</p>"
                f"<p class='txn-kpi-val'>{df['Total OT (hrs)'].sum():,.1f}</p></div>",
                unsafe_allow_html=True,
            )
            render_dataframe_html_table(df)
            export_buttons(df, "overtime_report", "Overtime Report")
        else:
            st.info("No overtime in this period.")
