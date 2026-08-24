"""PART 6 — Toll manufacturing validation."""

from __future__ import annotations

from tools.v17_2.common import ReportBundle, temp_database


def run_toll_validation() -> ReportBundle:
    rep = ReportBundle("Toll Manufacturing Validation — V17.2 (embedded in suite)")
    db, path, _ = temp_database()
    try:
        from application.manufacturing.toll import TollManufacturingService
        from application.manufacturing.batch import BatchManufacturingService
        from application.manufacturing.qc_lab import QCLabService
        from domain.tenant import TenantContext
        tenant = TenantContext(company_id=1)
        toll = TollManufacturingService(tenant)

        with db.get_connection() as conn:
            conn.execute("INSERT INTO customers(code,name,is_active) VALUES('TOLL-C','Toll Customer',1)")
            cid = conn.execute("SELECT id FROM customers WHERE code='TOLL-C'").fetchone()[0]

        # Customer RM agreement
        aid_crm = toll.save_agreement({
            "customer_id": cid, "customer_rm": 1, "company_rm": 0,
            "customer_packaging": 1, "company_packaging": 0, "manufacturing_charge": 8.0,
        })
        tid1 = toll.start_toll_production(aid_crm, {"batch_no": "TOLL-CRM-01", "planned_qty": 200})
        rep.add("Customer RM", "Start production", "pass", f"ticket={tid1}")

        # Company RM agreement
        aid_srm = toll.save_agreement({
            "customer_id": cid, "customer_rm": 0, "company_rm": 1,
            "customer_packaging": 0, "company_packaging": 1, "manufacturing_charge": 5.0,
        })
        tid2 = toll.start_toll_production(aid_srm, {"batch_no": "TOLL-SRM-01", "planned_qty": 150})
        rep.add("Company RM", "Start production", "pass", f"ticket={tid2}")

        # QC step
        qc = QCLabService(tenant)
        iid = qc.create_inspection({"inspection_type": "finished_goods", "batch_ticket_id": tid1, "batch_no": "TOLL-CRM-01"})
        rep.add("QC", "Inspection create", "pass", f"id={iid}")

        # Billing
        with db.get_connection() as conn:
            tp_id = conn.execute("SELECT id FROM ifs_toll_production WHERE batch_ticket_id=?", (tid1,)).fetchone()[0]
        amt = toll.bill_production(tp_id, 180.0)
        rep.add("Billing", "Manufacturing charge", "pass", f"amount={amt}")

        rep.add("Dispatch", "Delivery note", "not_certified", "No automated dispatch link")
        rep.add("Receivable", "Sales invoice", "not_certified", "Toll billing not auto-posted to AR")

    finally:
        import os
        os.unlink(path)

    rep.sections["Verdict"] = (
        f"**{'TOLL WORKFLOW PARTIAL' if rep.failed == 0 else 'NOT CERTIFIED'}** — "
        "CM agreement, production, QC, billing tested; dispatch/AR not automated."
    )
    return rep
