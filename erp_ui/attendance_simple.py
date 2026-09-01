"""Daily attendance — bulk sheet, one department register at a time."""

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


def _emp_dept(e):
    return (e.get("department_name") or e.get("department") or "Unassigned").strip() or "Unassigned"


def _load_employees(search=None, department=None):
    emps = db.get_employees_hr(active_only=True, search=search) if hasattr(db, "get_employees_hr") else db.get_employees()
    # Always department-wise sort (API already sorts; keep stable if fallback)
    emps = sorted(emps, key=lambda e: (_emp_dept(e).upper(), (e.get("full_name") or "").upper(), e.get("code") or ""))
    if department and department != "All departments":
        emps = [e for e in emps if _emp_dept(e) == department]
    return emps


def _dept_options(emps, *, include_all=True):
    depts = sorted({_emp_dept(e) for e in emps}, key=str.upper)
    if include_all:
        return ["All departments"] + depts
    return depts


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
            "department": _emp_dept(e),
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
        "Department": r.get("department_name") or "",
        "Code": r.get("employee_code") or r.get("emp_code") or "",
        "Employee": r.get("employee_name", ""),
        "Status": STATUS_LABELS.get(r.get("status"), r.get("status", "")),
        "OT (hrs)": float(r.get("overtime_hrs") or 0),
        "Late (min)": float(r.get("late_mins") or 0),
        "Notes": r.get("notes") or "",
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
    ths = "".join(
        f"<th>{h}</th>"
        for h in ("Date", "Department", "Code", "Employee", "Status", "OT (hrs)", "Late (min)", "Notes")
    )
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('att_date') or ''))}</td>"
            f"<td>{escape(str(r.get('department_name') or '—'))}</td>"
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
    return df


def _summary_counts(df):
    if df is None or df.empty:
        return {}
    vc = df["status"].value_counts()
    return {s: int(vc.get(s, 0)) for s in STATUSES}


def _daily_sheet_tab():
    st.markdown(
        "**Daily attendance** — each department has its own register. "
        "Select a department, mark the sheet, then **Save**."
    )

    nav = st.columns([1, 1, 1, 2])
    ds_key = "att_bulk_date"
    if ds_key not in st.session_state:
        st.session_state[ds_key] = date.today()
    if nav[0].button("◀ Previous Day", key="att_prev"):
        st.session_state[ds_key] = st.session_state[ds_key] - timedelta(days=1)
        st.session_state.pop("att_preset", None)
        st.rerun()
    if nav[1].button("Today", key="att_today"):
        st.session_state[ds_key] = date.today()
        st.session_state.pop("att_preset", None)
        st.rerun()
    if nav[2].button("Next Day ▶", key="att_next"):
        st.session_state[ds_key] = st.session_state[ds_key] + timedelta(days=1)
        st.session_state.pop("att_preset", None)
        st.rerun()
    # Do not pass value= when key is already in session_state (avoids Streamlit warning)
    att_date = nav[3].date_input("Attendance Date", key=ds_key)
    ds = str(att_date)

    all_emps = _load_employees()
    if not all_emps:
        st.warning("Add employees first under **HR → Employees**.")
        return

    dept_opts = _dept_options(all_emps, include_all=True)
    _ATT_DEPT_DEFAULT_V = 2  # v2: default register = All departments
    if (
        "att_dept" not in st.session_state
        or st.session_state.get("att_dept") not in dept_opts
        or st.session_state.get("_att_dept_default_v", 0) < _ATT_DEPT_DEFAULT_V
    ):
        st.session_state["att_dept"] = dept_opts[0]
        st.session_state["_att_dept_default_v"] = _ATT_DEPT_DEFAULT_V

    f1, f2, f3 = st.columns([2, 1.5, 1])
    search = f1.text_input("Search", placeholder="Code, name, mobile…", key="att_search")
    dept = f2.selectbox("Department register", dept_opts, key="att_dept")
    show_only = f3.selectbox("Show", ["All employees", "Not yet saved today", "Already marked"], key="att_show")

    emps = _load_employees(search=search or None, department=dept)
    existing_map = db.get_attendance_map_for_date(ds) if hasattr(db, "get_attendance_map_for_date") else {
        r["employee_id"]: r for r in db.get_attendance(ds, ds)
    }

    if show_only == "Not yet saved today":
        emps = [e for e in emps if e["id"] not in existing_map]
    elif show_only == "Already marked":
        emps = [e for e in emps if e["id"] in existing_map]

    # Dept headcounts for quick navigation
    dept_counts = {}
    for e in all_emps:
        d = _emp_dept(e)
        dept_counts[d] = dept_counts.get(d, 0) + 1
    chips = " · ".join(f"**{d}** {n}" for d, n in sorted(dept_counts.items(), key=lambda x: x[0].upper()))
    st.caption(f"Active by department: {chips}")

    if not emps:
        st.info("No employees match your filters. Pick another department register.")
        return

    if dept == "All departments":
        st.warning(
            "You are viewing **all departments** mixed. "
            "Prefer one department at a time — each register is separate."
        )

    preset = st.session_state.pop("att_preset", None)
    df = _build_sheet(emps, existing_map, force_status=preset)

    counts = _summary_counts(df)
    scoped = all_emps if dept == "All departments" else [e for e in all_emps if _emp_dept(e) == dept]
    marked_scoped = len([e for e in scoped if e["id"] in existing_map])
    k1, k2, k3, k4, k5, k6 = st.columns(6, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>In View</p>"
        f"<p class='txn-kpi-val'>{len(emps):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Saved (dept)</p>"
        f"<p class='txn-kpi-val'>{marked_scoped}/{len(scoped)}</p></div>",
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
    qa[3].caption(
        f"Quick-fill applies to **{dept}** list below, then click **Save All**."
    )

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
        height=min(640, 80 + max(len(df), 1) * 35),
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
            ff.action_done(
                f"Saved **{dept}** attendance for **{n}** employee(s) on **{ds}**."
            )
        except Exception as e:
            st.error(str(e))
    c2.caption(
        f"Register: **{dept}** · Active in this register: **{len(scoped)}** · "
        f"Total active staff: **{len(all_emps)}**."
    )


def _quick_entry_tab():
    st.caption("Use for one-off corrections — bulk entry is on **Daily Sheet**.")
    att_date = st.date_input("Date", value=date.today(), key="att_q_date")
    emps = _load_employees()
    _, eid, _ = smart_select(
        "Employee", emps, "att_q_emp", "id",
        lambda r: f"{_emp_dept(r)} · {r['code']} - {r.get('full_name', r.get('name', ''))}",
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
    all_emps = _load_employees()
    c1, c2, c3 = st.columns([1, 1, 2])
    fd = str(c1.date_input("From", value=date.today().replace(day=1), key="att_reg_fd"))
    td = str(c2.date_input("To", value=date.today(), key="att_reg_td"))
    dept_opts = _dept_options(all_emps, include_all=True)
    if (
        "att_reg_dept" not in st.session_state
        or st.session_state.get("att_reg_dept") not in dept_opts
        or st.session_state.get("_att_dept_default_v", 0) < 2
    ):
        st.session_state["att_reg_dept"] = dept_opts[0]
        st.session_state["_att_dept_default_v"] = 2
    dept = c3.selectbox("Department register", dept_opts, key="att_reg_dept")
    rows = db.get_attendance(fd, td)
    if dept != "All departments":
        emps = {e["id"] for e in _load_employees(department=dept)}
        rows = [r for r in rows if r.get("employee_id") in emps]
    # Ensure department-wise order within date
    rows = sorted(
        rows,
        key=lambda r: (
            str(r.get("att_date") or ""),
            str(r.get("department_name") or "").upper(),
            str(r.get("employee_name") or "").upper(),
        ),
        reverse=False,
    )
    # att_date DESC preference for register browse
    rows = sorted(
        rows,
        key=lambda r: (
            str(r.get("att_date") or ""),
            str(r.get("department_name") or "").upper(),
            str(r.get("employee_name") or "").upper(),
        ),
        reverse=True,
    )
    if not rows:
        st.markdown(
            '<div class="erp-empty-state"><p>No attendance records for this period / department.</p></div>',
            unsafe_allow_html=True,
        )
        if st.button("Open Daily Sheet", type="primary", key="att_reg_empty_cta"):
            st.session_state["att_simple_tab"] = "Daily Sheet"
            st.rerun()
        return
    from erp_ui.list_paging import page_slice
    page_rows = page_slice(rows, "att_reg", default_size=100)
    df = pd.DataFrame([{
        "Date": r["att_date"],
        "Department": r.get("department_name") or "",
        "Code": r.get("emp_code", ""),
        "Employee": r.get("employee_name", ""),
        "Status": STATUS_LABELS.get(r.get("status"), r.get("status", "")),
        "OT (hrs)": float(r.get("overtime_hrs") or 0),
        "Late (min)": float(r.get("late_mins") or 0),
        "Notes": r.get("notes") or "",
    } for r in page_rows])
    export_df = _render_attendance_register_table(page_rows)
    export_buttons(export_df if export_df is not None else df, "attendance_register", "Attendance Register")
    st.caption(
        f"Department register: **{dept}** · "
        f"Showing paged rows — full period has **{len(rows):,}** records."
    )
    st.divider()
    st.subheader("Summary by employee")
    full_df = pd.DataFrame([{
        "Date": r["att_date"],
        "Department": r.get("department_name") or "",
        "Employee": r.get("employee_name", ""),
        "Status": STATUS_LABELS.get(r.get("status"), r.get("status", "")),
        "OT (hrs)": float(r.get("overtime_hrs") or 0),
    } for r in rows])
    summary = full_df.groupby(["Department", "Employee"]).agg(
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
        c1, c2, c3 = st.columns([1, 1, 2])
        fd, td = str(c1.date_input("From", key="otf")), str(c2.date_input("To", key="ott"))
        all_emps = _load_employees()
        dept_opts = _dept_options(all_emps, include_all=True)
        dept = c3.selectbox("Department", dept_opts, key="ot_dept")
        rows = db.report_overtime(fd, td)
        if dept != "All departments":
            allowed = {e["id"] for e in _load_employees(department=dept)}
            # report may use employee_id or code — filter by code set
            codes = {e["code"] for e in _load_employees(department=dept)}
            rows = [
                r for r in rows
                if r.get("employee_id") in allowed or r.get("code") in codes
            ]
        if rows:
            df = pd.DataFrame([{
                "Department": r.get("department_name") or r.get("department") or "",
                "Code": r.get("code", ""),
                "Employee": r.get("full_name", ""),
                "Total OT (hrs)": float(r.get("total_overtime_hrs") or 0),
                "Days with OT": int(r.get("days") or 0),
            } for r in rows])
            if "Department" in df.columns:
                df = df.sort_values(["Department", "Employee"], kind="mergesort")
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
