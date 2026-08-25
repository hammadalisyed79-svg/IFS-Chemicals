"""HR & Payroll module pages — IFS Chemicals ERP."""

from datetime import date, datetime
import pandas as pd
import streamlit as st
from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import std_page_header, money_input, sticky_page_tabs, render_dataframe_html_table


def uid():
    u = st.session_state.get("user")
    return u["id"] if u else None


def fmt(v):
    return f"Rs. {float(v or 0):,.2f}"


def _payroll_lines_df(lines):
    """Payroll grid with employee name/code first (not raw IDs)."""
    rows = []
    for r in lines:
        rows.append({
            "Employee": r.get("employee_name") or r.get("full_name") or "—",
            "Code": r.get("emp_code") or r.get("code") or "—",
            "Basic": float(r.get("basic_salary") or 0),
            "Allowances": float(r.get("allowances") or 0),
            "Overtime": float(r.get("overtime") or 0),
            "Bonus": float(r.get("bonus") or 0),
            "Gross": float(r.get("gross_salary") or 0),
            "Tax": float(r.get("tax_deduction") or 0),
            "EOBI": float(r.get("eobi") or 0),
            "SS": float(r.get("social_security") or 0),
            "Advance Rec.": float(r.get("advance_recovery") or 0),
            "Loan Rec.": float(r.get("loan_recovery") or 0),
            "Other Ded.": float(r.get("other_deductions") or 0),
            "Total Ded.": float(r.get("total_deductions") or 0),
            "Net Salary": float(r.get("net_salary") or 0),
            "Paid": (r.get("paid_status") or "unpaid").title(),
            "Cash Doc": r.get("payment_document_no") or "—",
            "Present": float(r.get("days_present") or 0),
            "Absent": float(r.get("days_absent") or 0),
            "OT Hrs": float(r.get("overtime_hrs") or 0),
        })
    return pd.DataFrame(rows)


def export_df(df, name, title=None):
    if df is not None and not df.empty:
        from erp_ui.report_print import report_toolbar
        from erp_ui.report_profiles import report_layout
        lbl = title or name.replace("_", " ").title()
        report_toolbar(df, lbl, name, key_prefix=f"hr_{name}", layout=report_layout(lbl))


def require_hr(action="view"):
    user = st.session_state.get("user")
    if not db.user_can_hr(user, action):
        st.error("Access denied. HR / Admin permission required.")
        st.stop()


def _emp_opts(exclude_id=None):
    rows = db.get_employees_hr()
    if exclude_id:
        rows = [r for r in rows if r["id"] != exclude_id]
    return {f"{r['code']} - {r['full_name']}": r["id"] for r in rows}


def _dept_opts():
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_departments()}


def _desig_opts():
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_designations()}


def page_hr_employees():
    from html import escape

    require_hr("view")
    peek = st.session_state.get("hr_emp_tab") or "Employee List"
    std_page_header(
        "Employees",
        title="Employee Master",
        status="register" if peek == "Employee List" else None,
        status_kind="shell" if peek == "Employee List" else "invoice",
    )
    search = st.text_input("Search")
    tab = sticky_page_tabs(["Employee List", "Add Employee", "Edit / View"], "hr_emp_tab")
    rows = db.get_employees_hr(search=search or None)
    if tab == "Employee List":
        if rows:
            active_n = sum(1 for r in rows if r.get("is_active"))
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Employees</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Active</p>"
                f"<p class='txn-kpi-val'>{active_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            ths = "".join(
                f"<th>{h}</th>"
                for h in ("Code", "Name", "Department", "Designation", "Mobile", "Status")
            )
            body = []
            for r in rows:
                active = bool(r.get("is_active"))
                badge = (
                    '<span class="inv-badge inv-badge-approved">Active</span>'
                    if active
                    else '<span class="inv-badge inv-badge-cancelled">Inactive</span>'
                )
                body.append(
                    "<tr>"
                    f"<td>{escape(str(r.get('code') or ''))}</td>"
                    f"<td>{escape(str(r.get('full_name') or ''))}</td>"
                    f"<td>{escape(str(r.get('department_name') or '—'))}</td>"
                    f"<td>{escape(str(r.get('designation_name') or '—'))}</td>"
                    f"<td>{escape(str(r.get('mobile') or '—'))}</td>"
                    f"<td class='txn-status-cell'>{badge}</td>"
                    "</tr>"
                )
            st.markdown(
                '<div class="txn-reg-wrap"><table class="txn-reg-table">'
                f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
                unsafe_allow_html=True,
            )
            cols = ["code", "full_name", "father_name", "cnic", "department_name", "designation_name",
                    "mobile", "joining_date", "employment_status", "basic_salary", "is_active"]
            df = pd.DataFrame(rows)[[c for c in cols if c in rows[0]]]
            export_df(df, "employee_list")
        else:
            st.markdown(
                '<div class="erp-empty-state"><p>No employees yet.</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("Add Employee", type="primary", key="hr_emp_empty_cta"):
                st.session_state["hr_emp_tab"] = "Add Employee"
                st.rerun()
    elif tab == "Add Employee":
        if not db.user_can_hr(st.session_state.user, "add"):
            st.warning("You do not have permission to add employees.")
            return
        fid = "hr_emp_add"
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_emp_hr_{gen}"):
            c1, c2 = st.columns(2)
            code = c1.text_input("Employee Code", db.next_code("EMP", "employees"), key=wk("code"))
            name = c1.text_input("Employee Name *", key=wk("name"))
            father = c1.text_input("Father Name", key=wk("father"))
            cnic = c2.text_input("CNIC", key=wk("cnic"))
            dob = c2.date_input("Date of Birth", value=None, key=wk("dob"))
            gender = c1.selectbox("Gender", ["", "Male", "Female", "Other"], key=wk("gender"))
            marital = c2.selectbox(
                "Marital Status", ["", "Single", "Married", "Divorced", "Widowed"], key=wk("marital"),
            )
            mobile = c1.text_input("Mobile Number", key=wk("mobile"))
            email = c2.text_input("Email", key=wk("email"))
            phone = c1.text_input("Phone", key=wk("phone"))
            address = st.text_area("Address", key=wk("address"))
            depts = _dept_opts()
            desigs = _desig_opts()
            mgrs = _emp_opts()
            dept = st.selectbox("Department", [""] + list(depts.keys()), key=wk("dept"))
            desig = st.selectbox("Designation", [""] + list(desigs.keys()), key=wk("desig"))
            mgr = st.selectbox("Reporting Manager", [""] + list(mgrs.keys()), key=wk("mgr"))
            c3, c4 = st.columns(2)
            joining = c3.date_input("Joining Date", value=date.today(), key=wk("join"))
            confirm = c4.date_input("Confirmation Date", value=None, key=wk("confirm"))
            status = st.selectbox(
                "Employment Status",
                ["active", "probation", "confirmed", "resigned", "terminated"],
                key=wk("status"),
            )
            basic = money_input("Basic Salary", value=0.0, min_value=0.0, key=wk("basic"))
            bank = st.text_input("Bank Account", key=wk("bank"))
            if st.form_submit_button("Save Employee") and name:
                dept_id = depts.get(dept) if dept else None
                desig_id = desigs.get(desig) if desig else None
                dept_name = dept.split(" - ", 1)[-1] if dept else None
                desig_name = desig.split(" - ", 1)[-1] if desig else None
                db.add_employee_hr({
                    "code": code, "full_name": name, "father_name": father, "cnic": cnic,
                    "date_of_birth": str(dob) if dob else None, "gender": gender or None,
                    "marital_status": marital or None, "mobile": mobile, "phone": phone,
                    "email": email, "address": address, "department_id": dept_id,
                    "designation_id": desig_id, "manager_id": mgrs.get(mgr) if mgr else None,
                    "joining_date": str(joining), "confirmation_date": str(confirm) if confirm else None,
                    "employment_status": status, "basic_salary": basic, "bank_account": bank,
                    "department_name": dept_name, "designation_name": desig_name,
                }, uid())
                ff.action_done(
                    f"Employee **{name}** saved successfully. Form cleared for the next entry.",
                    form_id=fid,
                )
    elif tab == "Edit / View":
        if not rows:
            return
        sel = st.selectbox("Select Employee", [f"{r['code']} - {r['full_name']}" for r in rows])
        eid = next(r["id"] for r in rows if sel.startswith(r["code"]))
        emp = db.get_employee_hr(eid)
        if db.user_can_hr(st.session_state.user, "edit"):
            with st.form("edit_emp_hr"):
                c1, c2 = st.columns(2)
                code = c1.text_input("Code", value=emp["code"])
                name = c1.text_input("Name", value=emp["full_name"])
                father = c1.text_input("Father Name", value=emp.get("father_name") or "")
                cnic = c2.text_input("CNIC", value=emp.get("cnic") or "")
                mobile = c1.text_input("Mobile", value=emp.get("mobile") or emp.get("phone") or "")
                email = c2.text_input("Email", value=emp.get("email") or "")
                address = st.text_area("Address", value=emp.get("address") or "")
                depts = _dept_opts()
                desigs = _desig_opts()
                mgrs = _emp_opts(exclude_id=eid)
                dept_keys = list(depts.keys()) or [""]
                desig_keys = list(desigs.keys()) or [""]
                dept_idx = next((i for i, k in enumerate(dept_keys) if depts.get(k) == emp.get("department_id")), 0)
                desig_idx = next((i for i, k in enumerate(desig_keys) if desigs.get(k) == emp.get("designation_id")), 0)
                dept = st.selectbox("Department", dept_keys, index=min(dept_idx, len(dept_keys) - 1))
                desig = st.selectbox("Designation", desig_keys, index=min(desig_idx, len(desig_keys) - 1))
                status = st.selectbox("Status", ["active", "probation", "confirmed", "resigned", "terminated"],
                                      index=["active", "probation", "confirmed", "resigned", "terminated"].index(
                                          emp.get("employment_status") or "active"))
                basic = money_input("Basic Salary", value=float(emp.get("basic_salary") or 0), min_value=0.0, key="hr_emp_edit_basic")
                bank = st.text_input("Bank Account", value=emp.get("bank_account") or "")
                active = st.checkbox("Active", value=bool(emp.get("is_active", 1)))
                if st.form_submit_button("Update"):
                    db.update_employee_hr(eid, {
                        "code": code, "full_name": name, "father_name": father, "cnic": cnic,
                        "mobile": mobile, "email": email, "address": address,
                        "department_id": depts.get(dept), "designation_id": desigs.get(desig),
                        "employment_status": status, "basic_salary": basic, "bank_account": bank,
                        "department_name": dept.split(" - ", 1)[-1] if dept else None,
                        "designation_name": desig.split(" - ", 1)[-1] if desig else None,
                        "is_active": int(active),
                    }, uid())
                    ff.action_done("Updated.")
        st.markdown("**Leave Balances**")
        bals = db.get_leave_balances(eid)
        if bals:
            show = pd.DataFrame([{
                "Type": b["leave_type_name"],
                "Allocated": b.get("allocated", 0),
                "Used": b.get("used", 0),
                "Balance": b.get("balance", 0),
            } for b in bals])
            render_dataframe_html_table(show)
        else:
            st.caption("No leave balance records for this year.")
        if db.user_can_hr(st.session_state.user, "edit"):
            with st.expander("Allocate / allow leave"):
                st.caption("Leave starts at **0** until HR allocates days.")
                ltypes = db.get_leave_types()
                yr = st.number_input("Year", min_value=2020, max_value=2035,
                                     value=date.today().year, key=f"emp_lv_yr_{eid}")
                for lt in ltypes:
                    cur = next((b for b in bals if b["leave_type_id"] == lt["id"]), None)
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"**{lt['name']}**" + ("" if lt.get("is_paid") else " (unpaid)"))
                    if lt.get("days_per_year"):
                        c1.caption(f"Standard policy: {lt['days_per_year']} days/year")
                    days = c2.number_input(
                        "Allocate days", min_value=0.0,
                        value=float(cur["allocated"] if cur else 0),
                        key=f"emp_lv_{eid}_{lt['id']}",
                    )
                    if c3.button("Save", key=f"emp_lv_save_{eid}_{lt['id']}"):
                        try:
                            db.allocate_leave(eid, lt["id"], days, int(yr), uid(), mode="set")
                            ff.action_done(f"{lt['name']} allocation updated.")
                        except Exception as ex:
                            st.error(str(ex))
                if st.button("Apply standard policy (CL/SL/AL)", key=f"emp_lv_std_{eid}"):
                    try:
                        db.apply_standard_leave_allocation(eid, int(yr), uid())
                        ff.action_done("Standard leave policy applied.")
                    except Exception as ex:
                        st.error(str(ex))
        st.markdown("**Salary Structure**")
        with st.form("sal_struct"):
            ss = db.get_salary_structure(eid) or {}
            c1, c2, c3 = st.columns(3)
            with c1:
                b = money_input("Basic", value=float(ss.get("basic_salary") or emp.get("basic_salary") or 0), min_value=0.0, key="hr_ss_basic")
            with c2:
                h = money_input("Housing Allowance", value=float(ss.get("housing_allowance") or 0), min_value=0.0, key="hr_ss_house")
            with c3:
                t = money_input("Transport Allowance", value=float(ss.get("transport_allowance") or 0), min_value=0.0, key="hr_ss_trans")
            with c1:
                m = money_input("Medical Allowance", value=float(ss.get("medical_allowance") or 0), min_value=0.0, key="hr_ss_med")
            with c2:
                o = money_input("Other Allowance", value=float(ss.get("other_allowance") or 0), min_value=0.0, key="hr_ss_other")
            if st.form_submit_button("Save Salary Structure") and db.user_can_hr(st.session_state.user, "edit"):
                db.save_salary_structure({
                    "employee_id": eid, "basic_salary": b, "housing_allowance": h,
                    "transport_allowance": t, "medical_allowance": m, "other_allowance": o,
                    "effective_from": str(date.today()),
                }, uid())
                ff.action_done("Salary structure saved.")


def page_designations():
    from html import escape

    require_hr("view")
    peek = st.session_state.get("desig_tab") or "List"
    std_page_header(
        "Employees",
        title="Designation Master",
        status="register" if peek == "List" else None,
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab = sticky_page_tabs(["List", "Add", "Edit / Delete"], "desig_tab")
    rows = db.get_designations(active_only=False)
    if tab == "List":
        if rows:
            active_n = sum(1 for r in rows if r.get("is_active"))
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Designations</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Active</p>"
                f"<p class='txn-kpi-val'>{active_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            ths = "".join(f"<th>{h}</th>" for h in ("Code", "Name", "Active"))
            body = []
            for r in rows:
                badge = (
                    '<span class="inv-badge inv-badge-approved">Active</span>'
                    if r.get("is_active")
                    else '<span class="inv-badge inv-badge-cancelled">Inactive</span>'
                )
                body.append(
                    "<tr>"
                    f"<td>{escape(str(r.get('code') or ''))}</td>"
                    f"<td>{escape(str(r.get('name') or ''))}</td>"
                    f"<td class='txn-status-cell'>{badge}</td>"
                    "</tr>"
                )
            st.markdown(
                '<div class="txn-reg-wrap"><table class="txn-reg-table">'
                f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
                unsafe_allow_html=True,
            )
    elif tab == "Add":
        if db.user_can_hr(st.session_state.user, "add"):
            with st.form("add_desig"):
                code = st.text_input("Code", db.next_code("DSG", "designations"))
                name = st.text_input("Designation Name")
                if st.form_submit_button("Save") and name:
                    db.add_designation({"code": code, "name": name}, uid())
                    st.rerun()
    elif tab == "Edit / Delete":
        if rows and db.user_can_hr(st.session_state.user, "edit"):
            sel = st.selectbox("Select", [f"{r['code']} - {r['name']}" for r in rows])
            did = next(r["id"] for r in rows if sel.startswith(r["code"]))
            d = db.get_designation(did)
            with st.form("edit_desig"):
                code = st.text_input("Code", value=d["code"])
                name = st.text_input("Name", value=d["name"])
                active = st.checkbox("Active", value=bool(d.get("is_active", 1)))
                if st.form_submit_button("Update"):
                    db.update_designation(did, {"code": code, "name": name, "is_active": int(active)}, uid())
                    st.rerun()


def page_attendance():
    require_hr("view")
    peek = st.session_state.get("hr_att_tab") or "Daily Entry"
    std_page_header(
        "Attendance",
        status="register" if peek == "Attendance Register" else None,
        status_kind="shell" if peek == "Attendance Register" else "invoice",
    )
    tab = sticky_page_tabs(["Daily Entry", "Attendance Register", "Overtime Report"], "hr_att_tab")
    emps = _emp_opts()
    if tab == "Daily Entry":
        if not emps:
            st.warning("Add employees first.")
            return
        att_date = st.date_input("Date", value=date.today())
        if db.user_can_hr(st.session_state.user, "add"):
            st.markdown("**Mark attendance for all employees**")
            records = []
            for label, eid in emps.items():
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                c1.write(label)
                status = c2.selectbox("Status", db.ATTENDANCE_STATUSES, key=f"att_st_{eid}_{att_date}")
                late = c3.number_input("Late (mins)", value=0.0, key=f"att_late_{eid}_{att_date}")
                ot = c4.number_input("OT (hrs)", value=0.0, key=f"att_ot_{eid}_{att_date}")
                records.append({"employee_id": eid, "status": status, "late_mins": late, "overtime_hrs": ot})
            if st.button("Save Daily Attendance"):
                db.bulk_save_attendance(str(att_date), records, uid())
                ff.action_done("Attendance saved.")
    elif tab == "Attendance Register":
        c1, c2 = st.columns(2)
        fd = c1.date_input("From", value=date.today().replace(day=1))
        td = c2.date_input("To", value=date.today())
        rows = db.get_attendance(str(fd), str(td))
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
            export_df(pd.DataFrame(rows), "attendance_register")
    elif tab == "Overtime Report":
        c1, c2 = st.columns(2)
        fd = c1.date_input("OT From", value=date.today().replace(day=1), key="ot_from")
        td = c2.date_input("OT To", value=date.today(), key="ot_to")
        ot_rows = db.report_overtime(str(fd), str(td))
        if ot_rows:
            render_dataframe_html_table(pd.DataFrame(ot_rows))


def page_leave():
    require_hr("view")
    peek = st.session_state.get("leave_tab") or "Leave Requests"
    std_page_header(
        "Leave Management",
        status="register" if peek == "Leave Requests" else None,
        status_kind="shell" if peek == "Leave Requests" else "invoice",
    )
    tab = sticky_page_tabs(["Leave Requests", "New Request", "Approvals", "Allocate Leaves"], "leave_tab")
    if tab == "Leave Requests":
        rows = db.get_leave_requests()
        if rows:
            pending_n = sum(1 for r in rows if (r.get("status") or "").lower() == "pending")
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Requests</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Pending</p>"
                f"<p class='txn-kpi-val'>{pending_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            from erp_ui.list_paging import page_slice
            view = page_slice(rows, "leave_req_pg", default_size=50)
            render_dataframe_html_table(pd.DataFrame(view))
            export_df(pd.DataFrame(rows), "leave_report")
        else:
            st.markdown(
                '<div class="erp-empty-state"><p>No leave requests yet.</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("New Leave Request", type="primary", key="leave_empty_cta"):
                st.session_state["leave_tab"] = "New Request"
                st.rerun()
    elif tab == "New Request":
        emps = _emp_opts()
        ltypes = {lt["name"]: lt for lt in db.get_leave_types()}
        if emps and ltypes and db.user_can_hr(st.session_state.user, "add"):
            with st.form("leave_req"):
                emp = st.selectbox("Employee", list(emps.keys()))
                lt_name = st.selectbox("Leave Type", list(ltypes.keys()))
                lt = ltypes[lt_name]
                eid = emps[emp]
                bals = {b["leave_type_id"]: b for b in db.get_leave_balances(eid)}
                bal = bals.get(lt["id"])
                if lt.get("is_paid"):
                    if bal and float(bal.get("allocated") or 0) > 0:
                        st.info(
                            f"Available: **{float(bal.get('balance') or 0):g}** day(s) "
                            f"(allocated {float(bal.get('allocated') or 0):g}, used {float(bal.get('used') or 0):g})"
                        )
                    else:
                        st.warning("No leave allocated for this type. HR must allocate leave first.")
                else:
                    st.caption("Unpaid leave — no allocation required.")
                c1, c2 = st.columns(2)
                fd = c1.date_input("From Date")
                td = c2.date_input("To Date")
                days = (td - fd).days + 1
                st.caption(f"Days: {days}")
                reason = st.text_input("Reason")
                if st.form_submit_button("Submit Request"):
                    db.save_leave_request({
                        "employee_id": eid, "leave_type_id": lt["id"],
                        "from_date": str(fd), "to_date": str(td), "days": days, "reason": reason,
                    }, uid())
                    ff.action_done("Leave request submitted.")
    elif tab == "Approvals":
        pending = db.get_leave_requests(status="pending")
        if pending and db.user_can_hr(st.session_state.user, "approve"):
            for r in pending:
                st.write(f"**{r['document_no']}** — {r['employee_name']} — {r['leave_type_name']} ({r['days']} days)")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"appr_lv_{r['id']}"):
                    db.approve_leave_request(r["id"], uid(), True)
                    st.rerun()
                if c2.button("Reject", key=f"rej_lv_{r['id']}"):
                    db.approve_leave_request(r["id"], uid(), False)
                    st.rerun()
        elif not pending:
            st.info("No pending leave requests.")
    elif tab == "Allocate Leaves":
        if not db.user_can_hr(st.session_state.user, "edit"):
            st.info("You need HR edit permission to allocate leave.")
        else:
            st.markdown("**Allocate leave allowance**")
            st.caption(
                "New employees start with **0 allocated** days. Set allowances here before leave can be taken "
                "(except unpaid leave)."
            )
            yr = st.number_input("Year", min_value=2020, max_value=2035, value=date.today().year, key="lv_alloc_yr")
            emps = _emp_opts()
            ltypes = db.get_leave_types()
            scope = st.radio("Apply to", ["One employee", "All active employees"], horizontal=True, key="lv_alloc_scope")
            if scope == "One employee":
                if not emps:
                    st.warning("Add employees first.")
                else:
                    emp_lbl = st.selectbox("Employee", list(emps.keys()), key="lv_alloc_emp")
                    eid = emps[emp_lbl]
                    st.markdown("**Set allocation by leave type**")
                    for lt in ltypes:
                        bals = {b["leave_type_id"]: b for b in db.get_leave_allocation_register(int(yr), eid)}
                        cur = bals.get(lt["id"])
                        c1, c2, c3 = st.columns([2, 1, 1])
                        c1.write(f"**{lt['name']}**")
                        if lt.get("days_per_year"):
                            c1.caption(f"Policy default: {lt['days_per_year']} days")
                        val = c2.number_input(
                            "Days", min_value=0.0, value=float(cur["allocated"] if cur else 0),
                            key=f"lv_alloc_{eid}_{lt['id']}",
                        )
                        if c3.button("Set", key=f"lv_set_{eid}_{lt['id']}"):
                            try:
                                db.allocate_leave(eid, lt["id"], val, int(yr), uid(), mode="set")
                                ff.action_done(f"Updated {lt['name']}.")
                            except Exception as ex:
                                st.error(str(ex))
                    if st.button("Apply standard policy for this employee", key="lv_std_one"):
                        try:
                            db.apply_standard_leave_allocation(eid, int(yr), uid())
                            ff.action_done("Standard policy applied (CL 10, SL 10, AL 14).")
                        except Exception as ex:
                            st.error(str(ex))
            else:
                st.markdown("Apply **standard policy** from leave type master to every active employee:")
                st.caption("Casual 10, Sick 10, Annual 14 days (paid types only).")
                if st.button("Apply standard policy to all employees", type="primary", key="lv_std_all"):
                    try:
                        n = db.apply_standard_leave_allocation_all(int(yr), uid())
                        ff.action_done(f"Standard leave applied to {n} employee(s).")
                    except Exception as ex:
                        st.error(str(ex))
            st.divider()
            reg = db.get_leave_allocation_register(int(yr))
            if reg:
                df = pd.DataFrame([{
                    "Employee": r["employee_name"],
                    "Leave Type": r["leave_type_name"],
                    "Allocated": r.get("allocated", 0),
                    "Used": r.get("used", 0),
                    "Balance": r.get("balance", 0),
                } for r in reg])
                render_dataframe_html_table(df)
                export_df(df, f"leave_allocation_{yr}")
            else:
                st.info("No leave balance records for this year yet.")


def _ensure_hr_schema():
    """Apply HR DB upgrades (e.g. per-employee payment columns) on each payroll page load."""
    with db.get_connection() as conn:
        import db_hr as hrmod
        hrmod.apply_hr(conn, db)


def _render_employee_cash_payments(pid, pr):
    """Per-employee Pay cash / Pay bank — requires payroll status posted or paid."""
    status = pr.get("status")
    can_pay = db.user_can_hr(st.session_state.user, "post") or db.user_can_hr(st.session_state.user, "add")

    st.markdown("### Pay employees (cash / bank)")
    if status not in ("posted", "paid"):
        st.warning(
            f"Payroll status is **{status}**. To pay in cash: **Approve** → **Post to GL** → then use the buttons here. "
            "(Draft payroll cannot be paid yet.)"
        )
        return
    if not can_pay:
        st.info("You need HR **post** or **add** permission to record salary payments.")
        return

    paid_n = sum(1 for l in pr["lines"] if l.get("paid_status") == "paid")
    st.caption(
        f"One **Cash Book** voucher (CP-…) per employee. Paid: **{paid_n} / {len(pr['lines'])}**"
    )
    pay_date = st.date_input(
        "Payment date",
        value=date.fromisoformat(str(pr["run_date"])[:10]) if pr.get("run_date") else date.today(),
        key=f"pr_pay_date_{pid}",
    )
    pmode = st.radio("Payment mode", ["cash", "bank"], horizontal=True, key=f"pr_pay_mode_{pid}")
    if pmode == "cash" and db.is_cash_day_closed(str(pay_date)):
        st.warning(
            f"Cash book for **{pay_date}** is closed — change date or reopen the day in **Finance → Cash Book**."
        )
    bank_id = None
    if pmode == "bank":
        bank_accts = [
            a for a in db.get_accounts()
            if (a.get("account_type") or "").lower() in ("bank", "asset")
            and str(a.get("code") or "").startswith("11")
        ] or [a for a in db.get_accounts() if a.get("is_active")]
        bank_opts = {f"{a['code']} - {a['name']}": a["id"] for a in bank_accts}
        if bank_opts:
            bank_id = bank_opts[st.selectbox("Bank account", list(bank_opts.keys()), key=f"pr_bank_{pid}")]
        else:
            st.warning("Add a bank account in Chart of Accounts first.")

    unpaid = [l for l in pr["lines"] if l.get("paid_status") != "paid"]
    if unpaid and (pmode == "cash" or (pmode == "bank" and bank_id)):
        if st.button(f"Pay all {len(unpaid)} unpaid in {pmode}", type="primary", key=f"pr_pay_all_{pid}"):
            try:
                docs = db.pay_payroll(pid, uid(), pmode, str(pay_date), bank_id)
                ff.action_done(f"Paid {len(docs)} employee(s). Check **Finance → Cash Book**.")
            except Exception as e:
                st.error(str(e))

    for line in pr["lines"]:
        lc1, lc2, lc3, lc4 = st.columns([3, 1.2, 1, 1])
        lc1.write(
            f"**{line.get('employee_name')}** ({line.get('emp_code')}) — Net **{fmt(line.get('net_salary'))}**"
        )
        if line.get("paid_status") == "paid":
            lc2.success(line.get("payment_document_no") or "Paid")
            if lc3.button("Undo", key=f"pr_unpay_{line['id']}"):
                try:
                    db.rollback_payroll_line_payment(line["id"], uid(), "Undo payment")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        elif float(line.get("net_salary") or 0) > 0:
            btn_label = "Pay cash" if pmode == "cash" else "Pay bank"
            if lc4.button(btn_label, type="primary", key=f"pr_pay_{line['id']}"):
                try:
                    if pmode == "bank" and not bank_id:
                        raise ValueError("Select bank account.")
                    res = db.pay_payroll_line(line["id"], uid(), pmode, str(pay_date), bank_id)
                    ff.action_done(f"**{res['document_no']}** — Cash Book")
                except Exception as e:
                    st.error(str(e))
        else:
            lc2.caption("No net pay")


def page_payroll():
    require_hr("view")
    _ensure_hr_schema()
    peek = st.session_state.get("hr_pay_tab") or "Payroll Runs"
    std_page_header(
        "Payroll",
        title="Payroll Processing",
        status="register" if peek == "Payroll Runs" else None,
        status_kind="shell" if peek == "Payroll Runs" else "invoice",
    )
    tab = sticky_page_tabs(
        ["Payroll Runs", "Generate Payroll", "Process / Pay", "Edit Lines", "Salary Slips"],
        "hr_pay_tab",
    )
    if tab == "Payroll Runs":
        runs = db.get_payroll_runs()
        if runs:
            k1, k2 = st.columns(2, gap="small")
            k1.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Payroll Runs</p>"
                f"<p class='txn-kpi-val'>{len(runs):,}</p></div>",
                unsafe_allow_html=True,
            )
            paid_n = sum(1 for r in runs if (r.get("status") or "").lower() == "paid")
            k2.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Paid</p>"
                f"<p class='txn-kpi-val'>{paid_n:,}</p></div>",
                unsafe_allow_html=True,
            )
            from erp_ui.list_paging import page_slice
            view = page_slice(runs, "hr_pay_runs_pg", default_size=40)
            render_dataframe_html_table(pd.DataFrame(view))
            export_df(pd.DataFrame(runs), "payroll_register")
        else:
            st.markdown(
                '<div class="erp-empty-state"><p>No payroll runs yet.</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("Generate Payroll", type="primary", key="pay_empty_cta"):
                st.session_state["hr_pay_tab"] = "Generate Payroll"
                st.rerun()
    elif tab == "Generate Payroll":
        if db.user_can_hr(st.session_state.user, "add"):
            c1, c2 = st.columns(2)
            month = c1.number_input("Month", 1, 12, date.today().month, key="pay_gen_month")
            year = c2.number_input("Year", 2020, 2035, date.today().year, key="pay_gen_year")
            existing = db.get_payroll_for_period(int(month), int(year))
            if existing:
                st.warning(
                    f"Payroll already exists for **{month}/{year}**: "
                    f"**{existing['document_no']}** ({existing['status']}). "
                    "Rollback below to delete it, then generate again."
                )
                can_rb_gen = (
                    db.user_can_hr(st.session_state.user, "delete")
                    or db.user_can_hr(st.session_state.user, "add")
                )
                if can_rb_gen:
                    gen_reason = st.text_input(
                        "Rollback reason",
                        key="pay_gen_rb_reason",
                        placeholder="Required to remove this payroll run",
                    )
                    if st.button("Rollback generated payroll", type="secondary", key="pay_gen_rb"):
                        try:
                            db.rollback_generated_payroll(existing["id"], uid(), gen_reason)
                            ff.action_done(f"Removed **{existing['document_no']}**. "
                                "Advance/loan recoveries restored. You can generate payroll again.")
                        except Exception as e:
                            st.error(str(e))
            st.caption(
                "Defaults: **Tax, EOBI & Social Security = 0**. "
                "**Loan recovery** is automatic for issued loans. "
                "Use **Edit Lines** to add statutory deductions if needed. "
                "View balances on **Employee Ledger**."
            )
            if st.button("Generate Monthly Payroll"):
                try:
                    pid = db.generate_payroll(int(month), int(year), uid())
                    ff.action_done(f"Payroll generated (ID {pid}).")
                except Exception as e:
                    st.error(str(e))
        elif db.user_can_hr(st.session_state.user, "view"):
            st.info("You need HR add permission to generate payroll.")
    elif tab == "Process / Pay":
        runs = [r for r in db.get_payroll_runs() if r["status"] in ("draft", "approved", "posted", "paid")]
        if runs:
            sel = st.selectbox("Select Payroll", [f"{r['document_no']} — {r['payroll_month']}/{r['payroll_year']} ({r['status']})" for r in runs])
            pid = next(r["id"] for r in runs if r["document_no"] in sel)
            pr = db.get_payroll_run(pid)
            if pr and pr.get("lines"):
                st.info(
                    f"**{pr['document_no']}** — {pr['payroll_month']}/{pr['payroll_year']} — Status: **{pr['status'].upper()}**"
                )
                steps = ["draft", "approved", "posted", "paid"]
                st.progress((steps.index(pr["status"]) + 1) / len(steps) if pr["status"] in steps else 0.25)

                _render_employee_cash_payments(pid, pr)
                st.divider()

                if pr["status"] == "draft":
                    st.caption("Need to change amounts? Use **Edit Lines** (draft only).")
                elif pr["status"] == "approved":
                    st.caption("Next step: click **Post to GL** below, then pay each employee in cash above.")
                if db.payroll_gl_posted(pid):
                    st.caption(f"GL accrual posted — ref: payroll / {pr['document_no']}")
                render_dataframe_html_table(_payroll_lines_df(pr["lines"]))
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Gross", fmt(pr["total_gross"]))
                m2.metric("Total Deductions", fmt(pr["total_deductions"]))
                m3.metric("Total Net", fmt(pr["total_net"]))
                c1, c2, c3 = st.columns(3)
                if pr["status"] == "draft" and db.user_can_hr(st.session_state.user, "approve"):
                    if c1.button("Approve Payroll"):
                        try:
                            db.approve_payroll(pid, uid())
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                if pr["status"] == "approved" and db.user_can_hr(st.session_state.user, "approve"):
                    if c1.button("Unapprove → Edit", key=f"unapprove_pr_{pid}"):
                        try:
                            db.unapprove_payroll(pid, uid())
                            ff.action_done("Returned to draft. Open **Edit Lines** to modify payroll.")
                        except Exception as e:
                            st.error(str(e))
                if pr["status"] in ("draft", "approved") and db.user_can_hr(st.session_state.user, "post"):
                    if c2.button("Post to GL"):
                        try:
                            db.post_payroll_gl(pid, uid())
                            ff.action_done("Posted to general ledger.")
                        except Exception as e:
                            st.error(str(e))
                if pr["status"] in ("posted", "paid") and db.user_can_hr(st.session_state.user, "post"):
                    st.divider()
                    st.markdown("**Rollback posted salary voucher**")
                    rb_reason = st.text_input(
                        "Reason (required)",
                        key=f"pr_rb_reason_{pid}",
                        placeholder="e.g. Wrong amounts — re-post after correction",
                    )
                    rb_label = (
                        "Rollback payment & GL voucher"
                        if pr["status"] == "paid"
                        else "Rollback GL voucher"
                    )
                    if st.button(rb_label, type="secondary", key=f"pr_rb_{pid}"):
                        try:
                            db.rollback_payroll_gl(pid, uid(), rb_reason)
                            ff.action_done("Payroll GL reversed. Status is **approved** — unapprove to edit lines, "
                                "then post again when ready.")
                        except Exception as e:
                            st.error(str(e))

                can_rb_gen = (
                    db.user_can_hr(st.session_state.user, "delete")
                    or db.user_can_hr(st.session_state.user, "add")
                )
                if can_rb_gen:
                    st.divider()
                    st.markdown("**Rollback generated payroll (delete run)**")
                    st.caption(
                        "Removes this payroll completely (lines, GL vouchers, advance/loan recoveries). "
                        f"Then regenerate for **{pr['payroll_month']}/{pr['payroll_year']}** on **Generate Payroll**."
                    )
                    del_reason = st.text_input(
                        "Delete reason (required)",
                        key=f"pr_del_reason_{pid}",
                        placeholder="e.g. Wrong month generated — regenerate",
                    )
                    if st.button("Rollback generated payroll", type="secondary", key=f"pr_del_{pid}"):
                        try:
                            doc = pr["document_no"]
                            period = f"{pr['payroll_month']}/{pr['payroll_year']}"
                            db.rollback_generated_payroll(pid, uid(), del_reason)
                            ff.action_done(f"Deleted **{doc}** ({period}). GL reversed if posted. "
                                "Open **Generate Payroll** to create a new run.")
                        except Exception as e:
                            st.error(str(e))
    elif tab == "Edit Lines":
        runs = [r for r in db.get_payroll_runs() if r["status"] == "draft"]
        if not runs:
            st.info(
                "No draft payroll to edit. **Unapprove** an approved payroll on **Process / Pay**, "
                "or generate a new payroll run."
            )
        elif not db.user_can_hr(st.session_state.user, "edit"):
            st.info("You need HR edit permission to modify payroll lines.")
        else:
            sel = st.selectbox(
                "Draft Payroll",
                [f"{r['document_no']} — {r['payroll_month']}/{r['payroll_year']}" for r in runs],
                key="pr_edit_run",
            )
            pid = next(r["id"] for r in runs if r["document_no"] in sel)
            pr = db.get_payroll_run(pid)
            if not pr or not pr.get("lines"):
                st.warning("No payroll lines found.")
            else:
                line_opts = {
                    f"{l.get('employee_name', '—')} ({l.get('emp_code', '')}) — Net {fmt(l['net_salary'])}": l
                    for l in pr["lines"]
                }
                sel_line = st.selectbox("Employee", list(line_opts.keys()), key="pr_edit_line")
                line = line_opts[sel_line]
                st.caption("Adjust earnings and deductions. Gross and net salary recalculate on save.")
                with st.form("payroll_line_edit"):
                    st.markdown("**Earnings**")
                    e1, e2, e3, e4 = st.columns(4)
                    with e1:
                        basic = money_input("Basic Salary", value=float(line.get("basic_salary") or 0), min_value=0.0, key="pr_ed_basic")
                    with e2:
                        allowances = money_input("Allowances", value=float(line.get("allowances") or 0), min_value=0.0, key="pr_ed_allw")
                    with e3:
                        overtime = money_input("Overtime", value=float(line.get("overtime") or 0), min_value=0.0, key="pr_ed_ot")
                    with e4:
                        bonus = money_input("Bonus", value=float(line.get("bonus") or 0), min_value=0.0, key="pr_ed_bonus")
                    st.markdown("**Deductions** (Tax / EOBI / SS default nil — enter only if applicable)")
                    d1, d2, d3, d4, d5, d6 = st.columns(6)
                    with d1:
                        tax = money_input("Tax", value=float(line.get("tax_deduction") or 0), min_value=0.0, key="pr_ed_tax")
                    with d2:
                        eobi = money_input("EOBI", value=float(line.get("eobi") or 0), min_value=0.0, key="pr_ed_eobi")
                    with d3:
                        ss = money_input("Social Security", value=float(line.get("social_security") or 0), min_value=0.0, key="pr_ed_ss")
                    with d4:
                        adv = money_input("Advance Recovery", value=float(line.get("advance_recovery") or 0), min_value=0.0, key="pr_ed_adv")
                    with d5:
                        loan = money_input("Loan Recovery", value=float(line.get("loan_recovery") or 0), min_value=0.0, key="pr_ed_loan")
                    with d6:
                        other = money_input("Other Deductions", value=float(line.get("other_deductions") or 0), min_value=0.0, key="pr_ed_other")
                    st.markdown("**Attendance (reference)**")
                    a1, a2, a3 = st.columns(3)
                    days_present = a1.number_input("Days Present", min_value=0.0, value=float(line.get("days_present") or 0), step=0.5)
                    days_absent = a2.number_input("Days Absent", min_value=0.0, value=float(line.get("days_absent") or 0), step=0.5)
                    ot_hrs = a3.number_input("Overtime Hours", min_value=0.0, value=float(line.get("overtime_hrs") or 0), step=0.5)
                    preview_gross = basic + allowances + overtime + bonus
                    preview_ded = tax + eobi + ss + adv + loan + other
                    st.info(
                        f"Preview — Gross: **{fmt(preview_gross)}** | "
                        f"Deductions: **{fmt(preview_ded)}** | Net: **{fmt(preview_gross - preview_ded)}**"
                    )
                    if st.form_submit_button("Save Changes", type="primary"):
                        try:
                            db.update_payroll_line(line["id"], {
                                "basic_salary": basic, "allowances": allowances,
                                "overtime": overtime, "bonus": bonus,
                                "tax_deduction": tax, "eobi": eobi,
                                "social_security": ss, "advance_recovery": adv,
                                "loan_recovery": loan, "other_deductions": other,
                                "days_present": days_present, "days_absent": days_absent,
                                "overtime_hrs": ot_hrs,
                            }, uid())
                            ff.action_done("Payroll line updated.")
                        except Exception as e:
                            st.error(str(e))
                st.divider()
                render_dataframe_html_table(_payroll_lines_df(pr["lines"]))
    elif tab == "Salary Slips":
        runs = db.get_payroll_runs()
        if runs:
            sel = st.selectbox("Payroll for Slips", [f"{r['document_no']} — {r['payroll_month']}/{r['payroll_year']}" for r in runs])
            pid = next(r["id"] for r in runs if r["document_no"] in sel)
            pr = db.get_payroll_run(pid)
            if pr and pr.get("lines"):
                for line in pr["lines"]:
                    with st.expander(f"{line['employee_name']} — Net: {fmt(line['net_salary'])}"):
                        st.write(f"Basic: {fmt(line['basic_salary'])} | Allowances: {fmt(line['allowances'])}")
                        st.write(f"Overtime: {fmt(line['overtime'])} | Gross: {fmt(line['gross_salary'])}")
                        st.write(f"Deductions: {fmt(line['total_deductions'])} | Net: {fmt(line['net_salary'])}")
                        st.write(f"Bank: {line.get('bank_account') or '—'}")
                export_df(_payroll_lines_df(pr["lines"]), f"salary_sheet_{pr['document_no']}")


def page_advances():
    require_hr("view")
    peek = st.session_state.get("hr_adv_tab") or "Advance List"
    std_page_header(
        "Employee Advances",
        status="register" if peek == "Advance List" else None,
        status_kind="shell" if peek == "Advance List" else "invoice",
    )
    tab = sticky_page_tabs(["Advance List", "New Request", "Approve / Issue"], "hr_adv_tab")
    if tab == "Advance List":
        rows = db.get_advances()
        if rows:
            from erp_ui.list_paging import page_slice
            view = page_slice(rows, "hr_adv_list_pg", default_size=40)
            render_dataframe_html_table(pd.DataFrame(view))
        else:
            st.markdown(
                '<div class="erp-empty-state"><p>No employee advances yet.</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("New Advance Request", type="primary", key="adv_empty_cta"):
                st.session_state["hr_adv_tab"] = "New Request"
                st.rerun()
        out = db.report_outstanding_advances()
        if out:
            st.markdown("**Outstanding Advances**")
            render_dataframe_html_table(pd.DataFrame(out))
    elif tab == "New Request":
        emps = _emp_opts()
        if emps and db.user_can_hr(st.session_state.user, "add"):
            with st.form("adv_req"):
                emp = st.selectbox("Employee", list(emps.keys()))
                amt = money_input("Amount", value=0.0, min_value=0.0, key="hr_adv_amt")
                months = st.number_input("Recovery Months", 1, 24, 3)
                req_date = st.date_input("Request Date", value=date.today())
                reason = st.text_input("Reason")
                if st.form_submit_button("Submit"):
                    db.save_advance({
                        "employee_id": emps[emp], "amount": amt, "recovery_months": int(months),
                        "request_date": str(req_date), "reason": reason,
                    }, uid())
                    st.rerun()
    elif tab == "Approve / Issue":
        pending = db.get_advances(status="pending")
        approved = db.get_advances(status="approved")
        if db.user_can_hr(st.session_state.user, "approve"):
            for r in pending:
                st.write(f"**{r['document_no']}** — {r['employee_name']} — {fmt(r['amount'])}")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"adv_a_{r['id']}"):
                    db.approve_advance(r["id"], uid(), True)
                    st.rerun()
                if c2.button("Reject", key=f"adv_r_{r['id']}"):
                    db.approve_advance(r["id"], uid(), False)
                    st.rerun()
        if db.user_can_hr(st.session_state.user, "post"):
            for r in approved:
                st.write(f"Issue **{r['document_no']}** — {fmt(r['amount'])}")
                if st.button("Issue Advance", key=f"adv_i_{r['id']}"):
                    db.issue_advance(r["id"], uid())
                    st.rerun()


def page_loans():
    require_hr("view")
    peek = st.session_state.get("hr_loan_tab") or "Loan List"
    std_page_header(
        "Employee Advances",
        title="Employee Loans",
        status="register" if peek == "Loan List" else None,
        status_kind="shell" if peek == "Loan List" else "invoice",
    )
    tab = sticky_page_tabs(["Loan List", "New Loan", "Approve / Issue"], "hr_loan_tab")
    if tab == "Loan List":
        rows = db.get_loans()
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
        out = db.report_outstanding_loans()
        if out:
            st.markdown("**Outstanding Loans**")
            render_dataframe_html_table(pd.DataFrame(out))
    elif tab == "New Loan":
        emps = _emp_opts()
        if emps and db.user_can_hr(st.session_state.user, "add"):
            with st.form("loan_req"):
                emp = st.selectbox("Employee", list(emps.keys()))
                amt = money_input("Loan Amount", value=0.0, min_value=0.0, key="hr_loan_amt")
                inst = st.number_input("Installments", 1, 60, 12)
                issue_date = st.date_input("Issue Date", value=date.today())
                reason = st.text_input("Reason")
                if st.form_submit_button("Submit"):
                    db.save_loan({
                        "employee_id": emps[emp], "amount": amt, "installments": int(inst),
                        "issue_date": str(issue_date), "reason": reason,
                    }, uid())
                    st.rerun()
    elif tab == "Approve / Issue":
        if db.user_can_hr(st.session_state.user, "approve"):
            for r in db.get_loans(status="pending"):
                st.write(f"**{r['document_no']}** — {r['employee_name']} — {fmt(r['amount'])}")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"ln_a_{r['id']}"):
                    db.approve_loan(r["id"], uid(), True)
                    st.rerun()
                if c2.button("Reject", key=f"ln_r_{r['id']}"):
                    db.approve_loan(r["id"], uid(), False)
                    st.rerun()
        if db.user_can_hr(st.session_state.user, "post"):
            for r in db.get_loans(status="approved"):
                if st.button(f"Issue {r['document_no']}", key=f"ln_i_{r['id']}"):
                    db.issue_loan(r["id"], uid())
                    st.rerun()


def page_expense_claims():
    require_hr("view")
    peek = st.session_state.get("exp_claim_tab") or "Claims"
    std_page_header(
        "Employee Advances",
        title="Expense Claims",
        status="register" if peek == "Claims" else None,
        status_kind="shell" if peek == "Claims" else "invoice",
    )
    tab = sticky_page_tabs(["Claims", "New Claim", "Approve / Reimburse"], "exp_claim_tab")
    if tab == "Claims":
        rows = db.get_expense_claims()
        if rows:
            render_dataframe_html_table(pd.DataFrame(rows))
    elif tab == "New Claim":
        emps = _emp_opts()
        if emps and db.user_can_hr(st.session_state.user, "add"):
            with st.form("exp_claim"):
                emp = st.selectbox("Employee", list(emps.keys()))
                claim_date = st.date_input("Claim Date", value=date.today())
                desc = st.text_input("Description")
                amt = money_input("Amount", value=0.0, min_value=0.0, key="hr_exp_amt")
                if st.form_submit_button("Submit Claim"):
                    db.save_expense_claim({
                        "employee_id": emps[emp], "claim_date": str(claim_date),
                        "description": desc, "amount": amt,
                    }, uid())
                    st.rerun()
    elif tab == "Approve / Reimburse":
        if db.user_can_hr(st.session_state.user, "approve"):
            for r in db.get_expense_claims(status="pending"):
                st.write(f"**{r['document_no']}** — {r['employee_name']} — {fmt(r['amount'])} — {r['description']}")
                c1, c2 = st.columns(2)
                if c1.button("Approve", key=f"ex_a_{r['id']}"):
                    db.approve_expense_claim(r["id"], uid(), True)
                    st.rerun()
                if c2.button("Reject", key=f"ex_r_{r['id']}"):
                    db.approve_expense_claim(r["id"], uid(), False)
                    st.rerun()
        if db.user_can_hr(st.session_state.user, "post"):
            for r in db.get_expense_claims(status="approved"):
                if not r.get("reimbursed") and st.button(f"Reimburse {r['document_no']}", key=f"ex_p_{r['id']}"):
                    db.reimburse_expense_claim(r["id"], uid())
                    st.rerun()


def page_employee_ledger():
    from erp_ui.helpers import render_ledger_summary_table

    require_hr("view")
    std_page_header("Employee Ledger", status="posted", status_kind="shell")
    st.caption(
        "Debit = advance/loan issued or salary paid. Credit = recoveries and net salary accrued. "
        "Closing = outstanding advance + loan − unpaid salary. "
        "Opening Balance adjusts for imported payroll recoveries that have no matching issue documents."
    )
    emps = _emp_opts()
    if not emps:
        st.info("Add employees first.")
        return
    c1, c2, c3 = st.columns(3)
    emp_lbl = c1.selectbox("Employee", list(emps.keys()), key="emp_ledger_sel")
    fd = c2.date_input("From", value=None, key="emp_ledger_from")
    td = c3.date_input("To", value=None, key="emp_ledger_to")
    emp, entries = db.get_employee_ledger(
        emps[emp_lbl],
        str(fd) if fd else None,
        str(td) if td else None,
    )
    if not emp:
        st.info("Employee not found.")
        return
    closing = float(entries[-1]["balance"]) if entries else 0.0
    st.subheader(f"{emp.get('full_name') or emp.get('code')}")
    adv_out = sum(
        float(a.get("outstanding_amount") or 0)
        for a in db.get_advances(status="issued", employee_id=emp["id"])
    )
    loan_out = sum(
        float(l.get("outstanding_amount") or 0)
        for l in db.get_loans(status="issued", employee_id=emp["id"])
    )
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Outstanding Advance</p>"
        f"<p class='txn-kpi-val'>{fmt(adv_out)}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Outstanding Loan</p>"
        f"<p class='txn-kpi-val'>{fmt(loan_out)}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Ledger Balance</p>"
        f"<p class='txn-kpi-val'>{fmt(closing)}</p></div>",
        unsafe_allow_html=True,
    )
    if len(entries) > 1:
        df = pd.DataFrame(entries)[["date", "ref", "description", "debit", "credit", "balance"]]
        df.columns = ["Date", "Ref", "Description", "Debit", "Credit", "Balance"]
        render_ledger_summary_table(entries)
        export_df(df, "employee_ledger", f"Employee Ledger - {emp.get('full_name')}")
    else:
        st.info("No ledger entries in this period.")


def page_hr_reports():
    require_hr("view")
    std_page_header("Reports Center", title="HR Reports", status="register", status_kind="shell")
    report = st.selectbox("Report", [
        "Employee List", "Employee Ledger", "Attendance Report", "Leave Report", "Overtime Report",
        "Payroll Register", "Department Salary Cost", "Outstanding Advances",
        "Outstanding Loans", "Employee History",
    ])
    if report == "Employee Ledger":
        page_employee_ledger()
        return
    if report == "Employee List":
        df = pd.DataFrame(db.report_employee_list())
        render_dataframe_html_table(df)
        export_df(df, "employees")
    elif report == "Attendance Report":
        c1, c2 = st.columns(2)
        fd, td = c1.date_input("From", value=date.today().replace(day=1)), c2.date_input("To", value=date.today())
        df = pd.DataFrame(db.report_attendance(str(fd), str(td)))
        render_dataframe_html_table(df)
        export_df(df, "attendance")
    elif report == "Leave Report":
        df = pd.DataFrame(db.report_leave())
        render_dataframe_html_table(df)
        export_df(df, "leave")
    elif report == "Overtime Report":
        c1, c2 = st.columns(2)
        fd, td = c1.date_input("From", key="r_ot_f"), c2.date_input("To", key="r_ot_t")
        df = pd.DataFrame(db.report_overtime(str(fd), str(td)))
        render_dataframe_html_table(df)
    elif report == "Payroll Register":
        df = pd.DataFrame(db.report_payroll_register())
        render_dataframe_html_table(df)
        export_df(df, "payroll_register")
    elif report == "Department Salary Cost":
        runs = db.get_payroll_runs()
        if runs:
            sel = st.selectbox("Payroll Period", [f"{r['document_no']} — {r['payroll_month']}/{r['payroll_year']}" for r in runs])
            pid = next(r["id"] for r in runs if r["document_no"] in sel)
            df = pd.DataFrame(db.report_dept_salary_cost(pid))
            render_dataframe_html_table(df)
            export_df(df, "dept_salary_cost")
    elif report == "Outstanding Advances":
        df = pd.DataFrame(db.report_outstanding_advances())
        render_dataframe_html_table(df)
    elif report == "Outstanding Loans":
        df = pd.DataFrame(db.report_outstanding_loans())
        render_dataframe_html_table(df)
    elif report == "Employee History":
        emps = _emp_opts()
        if emps:
            emp = st.selectbox("Employee", list(emps.keys()))
            hist = db.report_employee_history(emps[emp])
            st.json(hist)
