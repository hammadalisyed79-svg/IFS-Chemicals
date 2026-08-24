"""Generate all V17.3 certification reports — PASS/FAIL only."""

from __future__ import annotations

import os
import subprocess
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
from tools.v17_3.certification import (
    build_enterprise_report,
    run_architecture,
    run_database,
    run_factory_sim,
    run_finance,
    run_functional,
    run_performance,
    run_security,
)


def _playwright_ok() -> bool:
    e2e = ROOT / "tests" / "e2e" / "test_ui_playwright.py"
    if not e2e.exists():
        return False
    r = subprocess.run([sys.executable, str(e2e)], capture_output=True, text=True, cwd=str(ROOT))
    return r.returncode == 0


def main():
    os.environ["ERP_CERT_V173"] = "1"
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

    for bundle in reports.values():
        bundle.finalize_v173()

    reports["warehouse"].sections["Toll Manufacturing"] = reports["toll"].to_markdown(v173=True).split("## Detailed Results")[0]
    reports["manufacturing"].sections["Industrial Devices"] = reports["devices"].sections.get("Verdict", "")

    write_report("ERP_DISCOVERY_REPORT.md", reports["discovery"].to_markdown(v173=True))
    write_report("FUNCTIONAL_TEST_REPORT.md", reports["functional"].to_markdown(v173=True))
    write_report("FINANCE_CERTIFICATION_REPORT.md", reports["finance"].to_markdown(v173=True))
    write_report("MANUFACTURING_CERTIFICATION.md", reports["manufacturing"].to_markdown(v173=True))
    write_report("WAREHOUSE_CERTIFICATION.md", reports["warehouse"].to_markdown(v173=True))
    write_report("MASTER_DATA_AUDIT.md", reports["master_data"].to_markdown(v173=True))
    write_report("PERFORMANCE_BENCHMARK.md", reports["performance"].to_markdown(v173=True))
    write_report("SECURITY_CERTIFICATION.md", reports["security"].to_markdown(v173=True))
    write_report("CODE_QUALITY_REPORT.md", reports["code_quality"].to_markdown(v173=True))
    write_report("DATABASE_HEALTH_REPORT.md", reports["database"].to_markdown(v173=True))
    write_report("UAT_TRACKING.md", reports["uat"].to_markdown(v173=True))

    gates = {
        "Security": run_security(),
        "Architecture": run_architecture(),
        "Functional": run_functional(),
        "Finance": run_finance(),
        "Manufacturing": reports["manufacturing"],
        "Warehouse": reports["warehouse"],
        "Database": run_database(),
        "Performance": run_performance(),
        "Factory": run_factory_sim(),
    }

    write_report("ENTERPRISE_CERTIFICATION_REPORT.md", build_enterprise_report(gates))

    print("V17.3 certification complete.")
    for name, bundle in gates.items():
        print(f"  {name}: {bundle.passed} pass, {bundle.failed} fail")
    print("  ENTERPRISE_CERTIFICATION_REPORT.md")


if __name__ == "__main__":
    main()
