"""Generate all V17.2 certification reports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.v17_2.common import write_report
from tools.v17_2.discovery import run_discovery
from tools.v17_2.functional import run_functional_tests
from tools.v17_2.finance import run_finance_certification
from tools.v17_2.manufacturing import run_manufacturing_certification
from tools.v17_2.warehouse import run_warehouse_certification
from tools.v17_2.toll import run_toll_validation
from tools.v17_2.master_data import run_master_data_audit
from tools.v17_2.performance import run_performance_benchmark
from tools.v17_2.security import run_security_certification
from tools.v17_2.devices import run_device_validation
from tools.v17_2.code_quality import run_code_quality
from tools.v17_2.database_health import run_database_health
from tools.v17_2.uat import run_uat_tracking
from tools.v17_2.release_gate import evaluate_release_gate, build_checklist, build_known_issues


def main():
    import database as db
    db.init_db()

    reports = {
        "discovery": run_discovery(),
        "functional": run_functional_tests(),
        "finance": run_finance_certification(),
        "manufacturing": run_manufacturing_certification(),
        "warehouse": run_warehouse_certification(),
        "toll": run_toll_validation(),
        "master_data": run_master_data_audit(),
        "performance": run_performance_benchmark(),
        "security": run_security_certification(),
        "devices": run_device_validation(),
        "code_quality": run_code_quality(),
        "database": run_database_health(),
        "uat": run_uat_tracking(),
    }

    # Merge toll into warehouse report section
    reports["warehouse"].sections["Toll Manufacturing"] = reports["toll"].to_markdown().split("## Detailed Results")[0]
    reports["manufacturing"].sections["Industrial Devices"] = reports["devices"].sections.get("Verdict", "")

    write_report("ERP_DISCOVERY_REPORT.md", reports["discovery"].to_markdown())
    write_report("FUNCTIONAL_TEST_REPORT.md", reports["functional"].to_markdown())
    write_report("FINANCE_CERTIFICATION_REPORT.md", reports["finance"].to_markdown())
    write_report("MANUFACTURING_CERTIFICATION.md", reports["manufacturing"].to_markdown())
    write_report("WAREHOUSE_CERTIFICATION.md", reports["warehouse"].to_markdown())
    write_report("MASTER_DATA_AUDIT.md", reports["master_data"].to_markdown())
    write_report("PERFORMANCE_BENCHMARK.md", reports["performance"].to_markdown())
    write_report("SECURITY_CERTIFICATION.md", reports["security"].to_markdown())
    write_report("CODE_QUALITY_REPORT.md", reports["code_quality"].to_markdown())
    write_report("DATABASE_HEALTH_REPORT.md", reports["database"].to_markdown())
    write_report("UAT_TRACKING.md", reports["uat"].to_markdown())

    gates, go_live = evaluate_release_gate(reports)
    write_report("GO_LIVE_READINESS_REPORT.md", go_live.to_markdown())
    write_report("PRODUCTION_DEPLOYMENT_CHECKLIST.md", build_checklist(gates))
    write_report("KNOWN_ISSUES.md", build_known_issues(reports))

    # Persist validation run
    with db.get_connection() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_validation_runs'").fetchone():
            conn.execute(
                """INSERT INTO erp_validation_runs(suite,pass_count,fail_count,report_path)
                   VALUES(?,?,?,?)""",
                ("v17_2", sum(r.passed for r in reports.values()), sum(r.failed for r in reports.values()),
                 "GO_LIVE_READINESS_REPORT.md"),
            )

    print("V17.2 certification complete.")
    for name, path in [
        ("Discovery", "ERP_DISCOVERY_REPORT.md"),
        ("Go-Live", "GO_LIVE_READINESS_REPORT.md"),
        ("Known Issues", "KNOWN_ISSUES.md"),
    ]:
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
