"""IFS Chemicals — industrial manufacturing UI (V17.1)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from erp_ui import form_flow as ff
from application import data_gateway as db
from erp_ui.helpers import std_page_header, money_input, options_with_blank, require_selected, sticky_page_tabs, render_dataframe_html_table
from application.manufacturing import (
    FormulationService, BatchManufacturingService, SprayDryerService,
    ReactorService, CorrugatedService, GravureService, PetBlowingService,
    QCLabService, PlantMaintenanceService, EnergyService, IndustrialCostingService,
    TollManufacturingService, IndustrialWarehouseService,
    IndustrialDashboardService, IndustrialReportService,
)
from application.manufacturing.spray_dryer import SPRAY_STAGES
from application.manufacturing.reactor import REACTOR_STAGES
from application.manufacturing.corrugated import CORRUGATED_STAGES
from application.manufacturing.gravure import GRAVURE_STAGES
from application.manufacturing.pet_blowing import PET_STAGES
from domain.tenant import get_tenant


def _user_id():
    u = st.session_state.get("user")
    return u["id"] if u else None


def _mach_opts():
    from application.data_gateway import get_machines
    rows = get_machines()
    return {f"{r.get('code') or r['id']} — {r['name']}": r["id"] for r in rows}


def _emp_opts():
    rows = db.get_employees(active_only=True) if hasattr(db, "get_employees") else []
    if not rows:
        try:
            import db_hr
            rows = db_hr.get_employees()
        except Exception:
            rows = []
    return {e.get("name", str(e["id"])): e["id"] for e in rows}


def _wh_opts():
    return {w["name"]: w["id"] for w in db.get_warehouses(active_only=True)}


def _prod_opts():
    return {f"{p.get('code','')} — {p['name']}": p["id"] for p in db.get_items(active_only=True)}


def _wk(prefix: str) -> str:
    """Unique Streamlit widget key for industrial pages."""
    return f"ind_{prefix}"


def _show_register(rows, columns=None, *, empty_msg="No records yet.", kpi_label="Records"):
    if not rows:
        st.info(empty_msg)
        return
    df = pd.DataFrame(rows)
    if columns:
        use_cols = [c for c in columns if c in df.columns]
        if use_cols:
            df = df[use_cols]
    st.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>{kpi_label}</p>"
        f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    render_dataframe_html_table(df)


def _ind_header(title, tab_key, register_tab="Register"):
    peek = st.session_state.get(tab_key) or register_tab
    std_page_header(
        title,
        status="register" if peek == register_tab else None,
        status_kind="shell" if peek == register_tab else "invoice",
    )


def page_formulation():
    _ind_header("Formula Master", "frm_tab")
    svc = FormulationService(get_tenant())
    tab = sticky_page_tabs(["Register", "New / Edit"], "frm_tab")
    if tab == "Register":
        _show_register(
            svc.list_formulas(),
            ["formula_code", "name", "revision", "formula_type", "status", "total_cost", "effective_from"],
            empty_msg="No formulas yet.",
            kpi_label="Formulas",
        )
    elif tab == "New / Edit":
        products = _prod_opts()
        pkeys = list(products.keys()) or ["—"]
        with st.form("frm_new"):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("Formula Code *", key=_wk("fc"))
            name = c2.text_input("Name *", key=_wk("fn"))
            ftype = c3.selectbox("Type", ["pilot", "commercial", "production"])
            prod = st.selectbox("Finished Product", pkeys)
            batch_qty = st.number_input("Standard Batch Qty (kg)", min_value=1.0, value=1000.0)
            tol = st.number_input("Tolerance %", min_value=0.0, value=2.0)
            st.caption("Add up to 5 raw material lines (% composition)")
            lines = []
            for i in range(5):
                cc1, cc2, cc3 = st.columns([3, 1, 1])
                pk = cc1.selectbox(f"RM {i+1}", ["—"] + list(_prod_opts().keys()), key=_wk(f"rm{i}"))
                pct = cc2.number_input("%", min_value=0.0, value=0.0, key=_wk(f"pct{i}"))
                if pk != "—" and pct > 0:
                    lines.append({"product_id": _prod_opts()[pk], "pct": pct, "tolerance_pct": tol})
            if st.form_submit_button("Save Formula", type="primary") and code and name and lines:
                fid = svc.save_formula({
                    "formula_code": code.strip(), "name": name.strip(),
                    "formula_type": ftype, "product_id": products.get(prod),
                    "standard_batch_qty": batch_qty, "tolerance_pct": tol, "lines": lines,
                }, _user_id())
                ff.action_done(f"Formula saved (ID {fid})")


def page_spray_dryer():
    _ind_header("Spray Dryer", "sd_tab")
    svc = SprayDryerService(get_tenant())
    batch_svc = BatchManufacturingService(get_tenant())
    tab = sticky_page_tabs(["Register", "New Batch", "Process"], "sd_tab")
    if tab == "Register":
        _show_register(svc.list_batches(), kpi_label="Batches", empty_msg="No batches yet.")
    elif tab == "New Batch":
        formulas = FormulationService(get_tenant()).list_formulas()
        fopts = {f"{f['formula_code']} R{f['revision']}": f["id"] for f in formulas} if formulas else {}
        mach = _mach_opts()
        with st.form("sd_new"):
            c1, c2, c3 = st.columns(3)
            batch_no = c1.text_input("Batch No *")
            planned = c2.number_input("Planned Qty (kg)", min_value=1.0, value=1000.0)
            shift = c3.selectbox("Shift", ["A", "B", "C"])
            formula = st.selectbox("Recipe", list(fopts.keys()) if fopts else ["—"])
            slurry = st.text_input("Slurry Tank")
            mach_lbl = st.selectbox("Machine", list(mach.keys()) if mach else ["—"])
            if st.form_submit_button("Start Spray Dryer Batch", type="primary") and batch_no:
                sd_id = svc.start_batch({
                    "batch_no": batch_no.strip(), "planned_qty": planned, "shift": shift,
                    "formula_id": fopts.get(formula), "slurry_tank": slurry,
                    "machine_id": mach.get(mach_lbl),
                }, _user_id())
                ff.action_done(f"Spray dryer batch started (ID {sd_id})")
    elif tab == "Process":
        rows = svc.list_batches()
        if not rows:
            st.info("No active batches.")
            return
        opts = {f"{r['ticket_no']} — {r['batch_no']}": r["id"] for r in rows if r.get("status") != "completed"}
        if not opts:
            st.info("All batches completed.")
            return
        sel = st.selectbox("Select batch", list(opts.keys()))
        sd_id = opts[sel]
        detail = svc.get_batch_detail(sd_id)
        if detail:
            st.json({"stage": detail.get("stage"), "hot_air": detail.get("hot_air_temp_c"),
                     "outlet": detail.get("outlet_temp_c"), "moisture": detail.get("moisture_pct")})
        c1, c2 = st.columns(2)
        stage = c1.selectbox("Advance to stage", list(SPRAY_STAGES))
        if c1.button("Advance Stage"):
            svc.advance_stage(sd_id, stage, _user_id())
            st.rerun()
        hot = c2.number_input("Hot Air °C", value=180.0)
        out = c2.number_input("Outlet °C", value=85.0)
        if c2.button("Log Temperature"):
            svc.log_temperature(sd_id, hot, out)
            st.success("Temperature logged")
        st.markdown("**Utilities**")
        u1, u2, u3 = st.columns(3)
        steam = u1.number_input("Steam (kg)", value=0.0)
        gas = u2.number_input("Gas (m³)", value=0.0)
        elec = u3.number_input("Electricity (kWh)", value=0.0)
        if st.button("Record Utilities"):
            svc.record_utilities(sd_id, steam, gas, elec)
            st.success("Utilities recorded")
        st.markdown("**Complete Batch**")
        yld = st.number_input("Yield Qty (kg)", min_value=0.0, value=950.0)
        moist = st.number_input("Moisture %", value=3.5)
        density = st.number_input("Bulk Density", value=0.35)
        loss = st.number_input("Production Loss (kg)", value=0.0)
        if st.button("Issue Materials", type="secondary"):
            row = next((r for r in rows if r["id"] == sd_id), None)
            if row:
                batch_svc.issue_materials(row["batch_ticket_id"], _user_id())
                st.success("Materials issued to production")
        if st.button("Complete & Receive FG", type="primary"):
            result = svc.complete_batch(sd_id, yld, moist, density, loss, user_id=_user_id())
            ff.action_done(f"Batch completed — yield {result.get('yield_pct', 0):.1f}%")


def page_batch_manufacturing():
    _ind_header("Batch Manufacturing", "bm_tab")
    svc = BatchManufacturingService(get_tenant())
    tab = sticky_page_tabs(["Register", "New Ticket"], "bm_tab")
    if tab == "Register":
        _show_register(
            svc.list_tickets(),
            ["ticket_no", "batch_no", "process_type", "planned_qty", "actual_qty", "yield_pct", "status", "qc_status"],
            kpi_label="Tickets",
            empty_msg="No tickets yet.",
        )
    elif tab == "New Ticket":
        from application.manufacturing.batch import PROCESS_TYPES
        with st.form("bt_new"):
            batch_no = st.text_input("Batch No *")
            ptype = st.selectbox("Process Type", PROCESS_TYPES)
            planned = st.number_input("Planned Qty", min_value=1.0, value=500.0)
            if st.form_submit_button("Create Ticket") and batch_no:
                tid = svc.create_ticket({"batch_no": batch_no.strip(), "process_type": ptype, "planned_qty": planned}, _user_id())
                ff.action_done(f"Ticket {tid} created")


def page_reactor():
    _ind_header("Chemical Reactor", "rx_tab")
    svc = ReactorService(get_tenant())
    tab = sticky_page_tabs(["Register", "New Batch"], "rx_tab")
    if tab == "Register":
        _show_register(svc.list_batches(), kpi_label="Batches", empty_msg="No batches yet.")
    elif tab == "New Batch":
        with st.form("rx_new"):
            batch_no = st.text_input("Batch No *")
            reactor = st.text_input("Reactor Code", value="R-01")
            planned = st.number_input("Planned Qty (L)", min_value=1.0, value=500.0)
            if st.form_submit_button("Start Reactor Batch") and batch_no:
                rid = svc.start_batch({"batch_no": batch_no.strip(), "reactor_code": reactor, "planned_qty": planned}, _user_id())
                ff.action_done(f"Reactor batch {rid} started")


def page_corrugated():
    _ind_header("Corrugated Production", "cg_tab")
    svc = CorrugatedService(get_tenant())
    tab = sticky_page_tabs(["Register", "New Run"], "cg_tab")
    if tab == "Register":
        _show_register(svc.list_runs(), kpi_label="Runs", empty_msg="No runs yet.")
    elif tab == "New Run":
        with st.form("cg_new"):
            c1, c2, c3 = st.columns(3)
            batch_no = c1.text_input("Batch No *")
            gsm = c2.number_input("Paper GSM", value=150.0)
            flute = c3.selectbox("Flute Type", ["A", "B", "C", "E", "BC"])
            board = st.text_input("Board Size", value="1200x2400")
            planned = st.number_input("Planned Qty (sheets)", min_value=1.0, value=1000.0)
            if st.form_submit_button("Start Run") and batch_no:
                rid = svc.start_run({
                    "batch_no": batch_no.strip(), "paper_gsm": gsm, "flute_type": flute,
                    "board_size": board, "planned_qty": planned,
                }, _user_id())
                ff.action_done(f"Corrugated run {rid} started")


def page_gravure_packaging():
    _ind_header("Gravure / Packaging", "gv_tab", register_tab="Runs")
    svc = GravureService(get_tenant())
    tab = sticky_page_tabs(["Runs", "Cylinders", "New Run"], "gv_tab")
    if tab == "Runs":
        _show_register(svc.list_runs(), kpi_label="Runs", empty_msg="No runs yet.")
    elif tab == "Cylinders":
        cyls = svc.list_cylinders()
        _show_register(cyls, kpi_label="Cylinders", empty_msg="No cylinders yet.")
        with st.form("cyl_new"):
            code = st.text_input("Cylinder Code *")
            art = st.text_input("Artwork Revision")
            repeat = st.number_input("Repeat Length (mm)", value=500.0)
            if st.form_submit_button("Save Cylinder") and code:
                svc.save_cylinder({"cylinder_code": code.strip(), "artwork_revision": art, "repeat_length_mm": repeat})
                ff.action_done("Cylinder saved")
    elif tab == "New Run":
        cyls = svc.list_cylinders()
        copts = {c["cylinder_code"]: c["id"] for c in cyls} if cyls else {}
        with st.form("gv_new"):
            batch_no = st.text_input("Batch No *")
            cyl = st.selectbox("Cylinder", list(copts.keys()) if copts else ["—"])
            micron = st.number_input("Film Micron", value=12.0)
            planned = st.number_input("Planned Qty (kg)", min_value=1.0, value=500.0)
            ptype = st.selectbox("Type", ["gravure", "flexible_packaging"])
            if st.form_submit_button("Start Run") and batch_no:
                rid = svc.start_run({
                    "batch_no": batch_no.strip(), "cylinder_id": copts.get(cyl),
                    "film_micron": micron, "planned_qty": planned, "process_type": ptype,
                }, _user_id())
                ff.action_done(f"Run {rid} started")


def page_pet_blowing():
    _ind_header("PET Bottle Blowing", "pet_tab")
    svc = PetBlowingService(get_tenant())
    tab = sticky_page_tabs(["Register", "New Run"], "pet_tab")
    if tab == "Register":
        _show_register(svc.list_runs(), kpi_label="Runs", empty_msg="No runs yet.")
    elif tab == "New Run":
        prods = _prod_opts()
        with st.form("pet_new"):
            batch_no = st.text_input("Batch No *")
            preform = st.selectbox("Preform", list(prods.keys()) if prods else ["—"])
            weight = st.number_input("Bottle Weight (g)", value=25.0)
            cavity = st.number_input("Cavities", min_value=1, value=8)
            planned = st.number_input("Planned Qty (pcs)", min_value=1.0, value=10000.0)
            if st.form_submit_button("Start Run") and batch_no:
                rid = svc.start_run({
                    "batch_no": batch_no.strip(), "preform_product_id": prods.get(preform),
                    "bottle_weight_g": weight, "cavity_count": cavity, "planned_qty": planned,
                }, _user_id())
                ff.action_done(f"PET run {rid} started")


def page_qc_lab():
    _ind_header("QC Laboratory", "qc_tab", register_tab="Inspections")
    svc = QCLabService(get_tenant())
    tab = sticky_page_tabs(["Inspections", "New Inspection", "Specifications"], "qc_tab")
    if tab == "Inspections":
        _show_register(svc.list_inspections(), kpi_label="Inspections", empty_msg="No inspections yet.")
    elif tab == "Specifications":
        for itype in ("incoming", "in_process", "finished_goods"):
            specs = svc.list_specs(itype)
            if specs:
                st.subheader(itype.replace("_", " ").title())
                _show_register(specs, kpi_label="Specs")
    elif tab == "New Inspection":
        batches = BatchManufacturingService(get_tenant()).list_tickets()
        bopts = {f"{b['ticket_no']} — {b['batch_no']}": b for b in batches} if batches else {}
        with st.form("qc_new"):
            itype = st.selectbox("Type", ["incoming", "in_process", "finished_goods"])
            batch = st.selectbox("Batch Ticket", list(bopts.keys()) if bopts else ["—"])
            if st.form_submit_button("Create Inspection"):
                b = bopts.get(batch, {})
                iid = svc.create_inspection({
                    "inspection_type": itype,
                    "batch_ticket_id": b.get("id"),
                    "batch_no": b.get("batch_no"),
                }, _user_id())
                st.session_state["qc_insp_id"] = iid
                st.success(f"Inspection {iid} created")
        iid = st.session_state.get("qc_insp_id")
        if iid:
            specs = svc.list_specs()
            if specs:
                spec = specs[0]
                results = []
                for p in spec.get("parameters", []):
                    val = st.number_input(p["param_name"], value=float(p.get("target_value") or 0))
                    results.append({
                        "parameter_id": p["id"], "param_name": p["param_name"],
                        "measured_value": val, "min_value": p.get("min_value"), "max_value": p.get("max_value"),
                    })
                if st.button("Record Results"):
                    r = svc.record_results(iid, results)
                    st.success(f"Result: {r['result']}")
                if st.button("Approve COA"):
                    coa = svc.approve_coa(iid, _user_id())
                    st.success(f"COA {coa} approved")


def page_plant_maintenance():
    std_page_header("Plant Maintenance", status="register", status_kind="shell")
    svc = PlantMaintenanceService(get_tenant())
    tab = sticky_page_tabs(["PM Schedules", "Breakdown", "Analysis"], "pm_tab")
    if tab == "PM Schedules":
        _show_register(svc.list_pm_schedules(), kpi_label="Schedules", empty_msg="No PM schedules yet.")
        mach = _mach_opts()
        with st.form("pm_new"):
            m = st.selectbox("Machine", list(mach.keys()) if mach else ["—"])
            stype = st.selectbox("Type", ["preventive", "lubrication"])
            freq = st.number_input("Frequency (days)", value=30)
            if st.form_submit_button("Add Schedule") and mach:
                svc.save_pm_schedule({"machine_id": mach[m], "schedule_type": stype, "frequency_days": int(freq)})
                ff.action_done("Schedule saved")
    elif tab == "Breakdown":
        mach = _mach_opts()
        with st.form("bd_new"):
            m = st.selectbox("Machine", list(mach.keys()) if mach else ["—"])
            cause = st.text_input("Cause")
            if st.form_submit_button("Report Breakdown") and mach and cause:
                tid = svc.create_breakdown(mach[m], cause, _user_id())
                st.success(f"Breakdown ticket {tid}")
    elif tab == "Analysis":
        st.json(svc.downtime_analysis())


def page_energy():
    std_page_header("Energy Management", status="register", status_kind="shell")
    svc = EnergyService(get_tenant())
    tab = sticky_page_tabs(["Summary", "Record Reading"], "en_tab")
    if tab == "Summary":
        summary = svc.summary()
        if summary:
            _show_register(summary, kpi_label="Readings")
        else:
            st.info("No energy readings yet.")
    elif tab == "Record Reading":
        batches = BatchManufacturingService(get_tenant()).list_tickets()
        bopts = {f"{b['ticket_no']}": b["id"] for b in batches[:20]} if batches else {}
        with st.form("en_rec"):
            utype = st.selectbox("Utility", ["steam", "gas", "electricity", "diesel", "compressed_air", "water"])
            qty = st.number_input("Quantity", min_value=0.0, value=100.0)
            uom = st.text_input("UOM", value="kg")
            batch = st.selectbox("Batch (optional)", ["—"] + list(bopts.keys()))
            if st.form_submit_button("Record"):
                bid = bopts.get(batch) if batch != "—" else None
                svc.record(bid, utype, qty, uom)
                ff.action_done("Reading recorded")


def page_industrial_costing():
    std_page_header("Industrial Costing", status="register", status_kind="shell")
    svc = IndustrialCostingService(get_tenant())
    rows = svc.variance_report()
    if rows:
        _show_register(rows, kpi_label="Cost Lines")
    else:
        st.info("Complete batches to see cost roll-ups.")


def page_toll_manufacturing():
    std_page_header("Toll Manufacturing", status="register", status_kind="shell")
    svc = TollManufacturingService(get_tenant())
    tab = sticky_page_tabs(["Agreements", "Production"], "toll_tab")
    if tab == "Agreements":
        _show_register(svc.list_agreements(), kpi_label="Agreements", empty_msg="No agreements yet.")
        custs = {c["name"]: c["id"] for c in db.get_customers(active_only=True)}
        with st.form("toll_ag"):
            cust_labels, blank = options_with_blank(custs.keys()) if custs else (["—"], "—")
            cust = st.selectbox("Customer", cust_labels)
            charge = money_input("Manufacturing Charge / kg", value=5.0, min_value=0.0, key="toll_mfg_charge")
            if st.form_submit_button("Save Agreement") and custs:
                if not require_selected("customer", cust, blank):
                    pass
                else:
                    svc.save_agreement({"customer_id": custs[cust], "manufacturing_charge": charge})
                    ff.action_done("Agreement saved")
    elif tab == "Production":
        ags = svc.list_agreements()
        aopts = {a["agreement_no"]: a["id"] for a in ags if a.get("status") == "active"} if ags else {}
        with st.form("toll_prod"):
            ag = st.selectbox("Agreement", list(aopts.keys()) if aopts else ["—"])
            batch_no = st.text_input("Batch No")
            planned = st.number_input("Planned Qty", value=500.0)
            if st.form_submit_button("Start Toll Production") and aopts and batch_no:
                tid = svc.start_toll_production(aopts[ag], {"batch_no": batch_no.strip(), "planned_qty": planned}, _user_id())
                st.success(f"Toll batch ticket {tid}")


def page_industrial_warehouse():
    std_page_header("Industrial Warehouse", status="register", status_kind="shell")
    svc = IndustrialWarehouseService(get_tenant())
    tab = sticky_page_tabs(["Zones", "Transfer", "Traceability"], "iw_tab")
    if tab == "Zones":
        _show_register(svc.list_zones(), kpi_label="Zones")
    elif tab == "Transfer":
        prods = _prod_opts()
        whs = _wh_opts()
        with st.form("iw_xfer"):
            p = st.selectbox("Product", list(prods.keys()) if prods else ["—"])
            fw = st.selectbox("From Warehouse", list(whs.keys()) if whs else ["—"])
            tw = st.selectbox("To Warehouse", list(whs.keys()) if whs else ["—"])
            qty = st.number_input("Qty", min_value=0.001, value=1.0)
            if st.form_submit_button("Transfer") and prods and whs:
                svc.inter_warehouse_transfer(prods[p], whs[fw], whs[tw], qty, user_id=_user_id())
                st.success("Transfer completed")
    elif tab == "Traceability":
        bn = st.text_input("Batch No")
        if bn and st.button("Trace"):
            trace = svc.batch_traceability(bn)
            if trace:
                _show_register(trace, kpi_label="Trace Lines")
            else:
                st.info("No trace data for this batch.")


def page_industrial_dashboards():
    std_page_header("Industrial Dashboards", status="register", status_kind="shell")
    svc = IndustrialDashboardService(get_tenant())
    view = st.selectbox("Dashboard", [
        "CEO", "Plant", "Production", "Quality", "Maintenance", "Energy", "Warehouse", "Costing",
    ])
    data = {
        "CEO": svc.ceo_dashboard, "Plant": svc.plant_dashboard,
        "Production": svc.production_dashboard, "Quality": svc.quality_dashboard,
        "Maintenance": svc.maintenance_dashboard, "Energy": svc.energy_dashboard,
        "Warehouse": svc.warehouse_dashboard, "Costing": svc.costing_dashboard,
    }[view]()
    st.json(data)


def page_industrial_reports():
    std_page_header("Industrial Reports", status="register", status_kind="shell")
    svc = IndustrialReportService(get_tenant())
    rpt = st.selectbox("Report", [
        "Production Register", "Daily Production", "Machine Utilization",
        "Yield Analysis", "Utility Consumption", "Maintenance",
    ])
    if rpt == "Production Register":
        render_dataframe_html_table(pd.DataFrame(svc.production_register()))
    elif rpt == "Daily Production":
        d = st.date_input("Date", value=date.today())
        render_dataframe_html_table(pd.DataFrame(svc.daily_production(str(d))))
    elif rpt == "Machine Utilization":
        render_dataframe_html_table(pd.DataFrame(svc.machine_utilization()))
    elif rpt == "Yield Analysis":
        render_dataframe_html_table(pd.DataFrame(svc.yield_analysis()))
    elif rpt == "Utility Consumption":
        render_dataframe_html_table(pd.DataFrame(svc.utility_consumption()))
    else:
        st.json(svc.maintenance_report())
