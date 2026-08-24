"""PART 14 — UAT mode and tracking."""

from __future__ import annotations

import json
from datetime import datetime

from tools.v17_2.common import ROOT, ReportBundle, temp_database

DEPARTMENTS = {
    "Sales": ["Sales Invoices", "Sale Approval", "Sales Orders", "Quotations"],
    "Purchase": ["Purchase Invoices", "GRN", "Purchase Orders"],
    "Inventory": ["Stock", "Stock Adjustments", "Industrial Warehouse"],
    "Production": ["Spray Dryer", "Batch Manufacturing", "BOM", "QC Laboratory"],
    "Finance": ["Cash Book", "Trial Balance", "Journal Voucher"],
    "HR": ["Payroll", "Attendance", "Leave Management"],
    "Admin": ["User Management", "ERP Health Check", "Backup & Restore"],
}


def seed_uat_scenarios(conn) -> int:
    count = 0
    for dept, screens in DEPARTMENTS.items():
        for screen in screens:
            code = f"UAT-{dept[:3].upper()}-{screen[:8].upper().replace(' ', '')}"
            conn.execute(
                """INSERT OR IGNORE INTO erp_uat_scenarios(code,department,module,steps_json,is_active)
                   VALUES(?,?,?,?,1)""",
                (code, dept, screen, json.dumps([
                    "Open screen", "Create record", "Save", "Verify in register", "Logout",
                ])),
            )
            count += 1
    return count


def run_uat_tracking() -> ReportBundle:
    rep = ReportBundle("UAT Tracking — V17.2")
    db, path, _ = temp_database()
    try:
        with db.get_connection() as conn:
            n = seed_uat_scenarios(conn)
            rep.add("UAT", "Scenarios seeded", "pass", f"{n} scenarios")

            # Auto-record pending for each scenario
            rows = conn.execute("SELECT id, code, department, module FROM erp_uat_scenarios").fetchall()
            for row in rows:
                conn.execute(
                    """INSERT INTO erp_uat_runs(scenario_id, tester, department, status, comments, tested_at)
                       VALUES(?,?,?,?,?,?)""",
                    (row[0], "automated-ci", row[1], "pending",
                     f"Awaiting department sign-off for {row[3]}", datetime.now().isoformat()),
                )

            summary = conn.execute(
                "SELECT status, COUNT(*) FROM erp_uat_runs GROUP BY status"
            ).fetchall()
            rep.sections["UAT Status Summary"] = "\n".join(f"- {s}: {c}" for s, c in summary)

            rep.sections["Department Matrix"] = "\n".join(
                f"| {dept} | {len(screens)} screens | pending |" for dept, screens in DEPARTMENTS.items()
            )
            rep.add("UAT Mode", "erp_uat_scenarios table", "pass", "V17.2 migration")
            rep.add("UAT Mode", "Department-wise tracking", "pass", f"{len(DEPARTMENTS)} departments")

    finally:
        import os
        os.unlink(path)

    rep.sections["Instructions"] = (
        "Departments execute scenarios manually; update `erp_uat_runs.status` to pass/fail. "
        "No UI changes in V17.2 — tracking via database + this report."
    )
    return rep
