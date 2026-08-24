"""V17.3 certification — PASS or FAIL only (no NOT CERTIFIED)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.v17_2.common import ReportBundle, write_report, temp_database
from tools.architecture_audit import scan_forbidden_ui_imports


def _run(cmd: list[str]) -> tuple[bool, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def run_security() -> ReportBundle:
    rep = ReportBundle("Security — V17.3")
    db, path, _ = temp_database()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        text = (ROOT / "database.py").read_text(encoding="utf-8")
        rep.add("Security", "Argon2id hashing", "pass" if "hash_password_argon2id" in text else "fail", "database.hash_password")
        rep.add("Security", "No SHA256 in hash_password", "pass" if "sha256(password" not in text.split("hash_password")[1][:200] else "fail", "")
        app_txt = (ROOT / "app.py").read_text(encoding="utf-8")
        rep.add("Security", "No admin123 on login", "pass" if "admin123" not in app_txt else "fail", "")
        auth = (ROOT / "erp_ui" / "auth_session.py").read_text(encoding="utf-8")
        rep.add("Security", "No session in URL", "pass" if "query_params[SESSION_PARAM]" not in auth and 'query_params["session"]' not in auth else "fail", "")
        from erp_core.password_v173 import validate_password_policy
        ok, msg = validate_password_policy(CI_ADMIN_PASSWORD, "admin")
        rep.add("Security", "Password policy", "pass" if ok else "fail", msg)
        from fastapi.testclient import TestClient
        from api.main import app
        c = TestClient(app)
        rep.add("Security", "Unauth blocked", "pass" if c.get("/api/v1/customers").status_code == 401 else "fail", "")
        tok = c.post("/api/v1/auth/token", data={"username": "admin", "password": CI_ADMIN_PASSWORD})
        rep.add("Security", "JWT auth", "pass" if tok.status_code == 200 else "fail", tok.text[:80])
        ok, out = _run([sys.executable, str(ROOT / "tests" / "test_portal_security.py")])
        rep.add("Security", "Portal security suite", "pass" if ok else "fail", out[-200:])
    finally:
        os.unlink(path)
    return rep


def run_architecture() -> ReportBundle:
    rep = ReportBundle("Architecture — V17.3")
    audit = scan_forbidden_ui_imports()
    n = audit["violation_count"]
    rep.add("Architecture", "UI direct DB imports", "pass" if n == 0 else "fail", f"{n} violations")
    if audit["violations"]:
        rep.sections["Violations"] = "\n".join(f"- `{v}`" for v in audit["violations"][:20])
    return rep


def run_functional() -> ReportBundle:
    rep = ReportBundle("Functional — V17.3")
    ok, out = _run([sys.executable, str(ROOT / "tests" / "test_v17_1_manufacturing.py")])
    rep.add("Functional", "Manufacturing suite", "pass" if ok else "fail", out[-300:])
    ok2, out2 = _run([sys.executable, str(ROOT / "tests" / "test_v17_2_certification.py")])
    rep.add("Functional", "V17.2 smoke", "pass" if ok2 else "fail", out2[-200:])
    ok3, out3 = _run([sys.executable, str(ROOT / "tests" / "test_api_v1.py")])
    rep.add("Functional", "API suite", "pass" if ok3 else "fail", out3[-200:])
    e2e = ROOT / "tests" / "e2e" / "test_ui_playwright.py"
    if e2e.exists():
        try:
            ok4, out4 = _run([sys.executable, str(e2e)])
            rep.add("Functional", "Playwright UI", "pass" if ok4 else "fail", out4[-300:])
        except Exception as exc:
            rep.add("Functional", "Playwright UI", "fail", str(exc))
    return rep


def run_finance() -> ReportBundle:
    rep = ReportBundle("Finance — V17.3")
    ok, out = _run([sys.executable, str(ROOT / "tests" / "test_v17_3_finance.py")])
    rep.add("Finance", "Full finance suite", "pass" if ok else "fail", out[-400:])
    return rep


def run_factory_sim() -> ReportBundle:
    rep = ReportBundle("Factory Simulation — V17.3")
    ok, out = _run([sys.executable, str(ROOT / "tools" / "v17_3" / "factory_simulation.py")])
    rep.add("Factory", "30-day simulation", "pass" if ok else "fail", out[-400:])
    return rep


def run_performance() -> ReportBundle:
    rep = ReportBundle("Performance — V17.3")
    env = {**os.environ, "PERF_SCALE": "full"}
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "from tools.v17_2.performance import run_performance_benchmark; b=run_performance_benchmark(); "
             "print('FAIL' if b.failed else 'PASS', b.pass_rate())"],
            capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=1800,
        )
        ok = r.returncode == 0 and "PASS" in (r.stdout or "")
        rep.add("Performance", "Full scale benchmark", "pass" if ok else "fail", (r.stdout or r.stderr)[-300:])
    except subprocess.TimeoutExpired:
        rep.add("Performance", "Full scale benchmark", "fail", "timeout 30min")
    return rep


def run_database() -> ReportBundle:
    from tools.v17_2.database_health import run_database_health
    rep = ReportBundle("Database — V17.3")
    b = run_database_health()
    for r in b.results:
        st = "pass" if r.status == "pass" else "fail"
        rep.add(r.category, r.name, st, r.detail)
    return rep


def build_enterprise_report(gates: dict[str, ReportBundle]) -> str:
    lines = [
        "# Enterprise Certification Report — V17.3",
        "",
        "**IFS Industrial ERP** — Commercial Certification",
        "",
        "## Release gates (PASS / FAIL only)",
        "",
        "| Domain | Result | Pass rate | Failures |",
        "|--------|--------|----------:|---------:|",
    ]
    all_pass = True
    for name, bundle in gates.items():
        failed = bundle.failed
        st = "PASS" if failed == 0 and bundle.pass_rate() >= 99.9 else "FAIL"
        if st == "FAIL":
            all_pass = False
        lines.append(f"| {name} | **{st}** | {bundle.pass_rate()}% | {failed} |")
    lines += [
        "",
        "## Verdict",
        "",
        f"### {'PRODUCTION READY' if all_pass else 'NOT PRODUCTION READY'}",
        "",
        "Evidence: automated suites in `tools/generate_v17_3_certification.py`, `tests/`, `tools/v17_3/`.",
        "",
    ]
    if not all_pass:
        lines.append("### Failed checks")
        lines.append("")
        for name, bundle in gates.items():
            for r in bundle.results:
                if r.status == "fail":
                    lines.append(f"- **{name} / {r.name}**: {r.detail}")
    return "\n".join(lines)


def main():
    gates = {
        "Security": run_security(),
        "Architecture": run_architecture(),
        "Functional": run_functional(),
        "Finance": run_finance(),
        "Manufacturing": ReportBundle("Mfg"),
        "Warehouse": ReportBundle("Wh"),
        "Database": run_database(),
        "Performance": run_performance(),
        "Factory": run_factory_sim(),
    }
    ok, _ = _run([sys.executable, str(ROOT / "tests" / "test_v17_1_manufacturing.py")])
    gates["Manufacturing"].add("Mfg", "V17.1 suite", "pass" if ok else "fail", "")
    from tools.v17_2.warehouse import run_warehouse_certification
    wh = run_warehouse_certification()
    for r in wh.results:
        gates["Warehouse"].add(r.category, r.name, "pass" if r.status == "pass" else "fail", r.detail)

    write_report("ENTERPRISE_CERTIFICATION_REPORT.md", build_enterprise_report(gates))
    print("Wrote ENTERPRISE_CERTIFICATION_REPORT.md")
    for n, b in gates.items():
        print(f"  {n}: {b.passed} pass, {b.failed} fail")


if __name__ == "__main__":
    main()
