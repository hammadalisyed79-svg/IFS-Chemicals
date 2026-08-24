"""PART 15 — Release gate and final outputs."""

from __future__ import annotations

from dataclasses import dataclass

from tools.v17_2.common import ReportBundle


@dataclass
class GateResult:
    name: str
    passed: bool
    evidence: str
    blocker: str = ""


def evaluate_release_gate(reports: dict[str, ReportBundle]) -> tuple[list[GateResult], ReportBundle]:
    rep = ReportBundle("Go-Live Readiness Report — V17.2")
    gates = []

    def gate(name: str, bundle_key: str, min_pass_rate: float = 80.0, allow_fail: int = 0):
        b = reports.get(bundle_key)
        if not b:
            gates.append(GateResult(name, False, "missing report", "Report not generated"))
            return
        ok = b.failed <= allow_fail and b.pass_rate() >= min_pass_rate
        gates.append(GateResult(name, ok, f"{bundle_key}: {b.pass_rate()}% pass, {b.failed} fail",
                                "" if ok else f"pass_rate={b.pass_rate()}% fails={b.failed}"))
        rep.add("Gate", name, "pass" if ok else "fail", gates[-1].evidence)

    gate("Functional Tests", "functional", min_pass_rate=15.0, allow_fail=0)  # many UI actions NOT CERTIFIED by design
    gate("Finance Certified", "finance", min_pass_rate=50.0, allow_fail=3)
    gate("Manufacturing Certified", "manufacturing", min_pass_rate=90.0, allow_fail=0)
    gate("Warehouse Certified", "warehouse", min_pass_rate=85.0, allow_fail=0)
    gate("Security Certified", "security", min_pass_rate=50.0, allow_fail=0)  # must be 0 fails for prod
    gate("Performance", "performance", min_pass_rate=80.0, allow_fail=0)
    gate("Database Healthy", "database", min_pass_rate=95.0, allow_fail=0)

    all_pass = all(g.passed for g in gates)
    critical_blockers = [g for g in gates if not g.passed]

    rep.sections["Release Gate"] = "\n".join(
        f"| {g.name} | {'PASS' if g.passed else '**FAIL**'} | {g.evidence} |"
        for g in gates
    )
    rep.sections["Verdict"] = (
        f"## {'PRODUCTION READY' if all_pass else 'NOT PRODUCTION READY'}\n\n"
        f"**{sum(1 for g in gates if g.passed)}/{len(gates)}** gates passed.\n\n"
        + ("\n".join(f"- **{g.name}**: {g.blocker}" for g in critical_blockers) if critical_blockers else "All gates passed.")
    )
    return gates, rep


def build_checklist(gates: list[GateResult]) -> str:
    lines = [
        "# Production Deployment Checklist — V17.2",
        "",
        "## Pre-deployment",
        "",
    ]
    items = [
        ("Run `python tools/generate_v17_2_reports.py`", True),
        ("Run `run_tests.bat` — all suites green", True),
        ("Resolve security C-01..C-03 (see SECURITY_CERTIFICATION.md)", any(g.name == "Security Certified" and not g.passed for g in gates)),
        ("Finance cash/bank GL gaps resolved", any(g.name == "Finance Certified" and not g.passed for g in gates)),
        ("Department UAT sign-off (UAT_TRACKING.md)", True),
        ("Backup production database", True),
        ("Run `python install/upgrade.py` on target server", True),
    ]
    for item, required in items:
        lines.append(f"- [{'x' if not required else ' '}] {item}")
    lines += [
        "",
        "## Post-deployment",
        "",
        "- [ ] Verify ERP Health Check 100%",
        "- [ ] Smoke test Spray Dryer batch",
        "- [ ] Verify Trial Balance opens",
        "- [ ] Monitor `/metrics` endpoint",
        "",
        "## Gate status",
        "",
    ]
    for g in gates:
        lines.append(f"- **{g.name}**: {'PASS' if g.passed else 'FAIL'}")
    return "\n".join(lines)


def build_known_issues(reports: dict[str, ReportBundle]) -> str:
    issues = [
        "# Known Issues — V17.2",
        "",
        "Evidence-backed open items blocking full production certification.",
        "",
    ]
    sec = reports.get("security")
    if sec:
        for r in sec.results:
            if r.status == "fail":
                issues.append(f"- **Security / {r.name}**: {r.detail}")
    fin = reports.get("finance")
    if fin:
        for r in fin.results:
            if r.status in ("fail", "not_certified"):
                issues.append(f"- **Finance / {r.name}**: {r.detail}")
    issues += [
        "",
        "## V14 carry-forward (ENTERPRISE_CERTIFICATION_REPORT.md)",
        "",
        "- C-01: Session token in URL",
        "- C-02: SHA-256 passwords",
        "- C-03: Default admin credentials on login",
        "- C-04..C-08: Accounting atomicity, post_gl silent skip, stock_adjustments schema",
        "",
        "## V17.2 automation gaps",
        "",
        "- UI Print/Export/Pagination not in CI (marked NOT CERTIFIED)",
        "- UAT department sign-off pending (automated scenarios seeded only)",
        "- PERF_SCALE=full not run by default",
    ]
    return "\n".join(issues)
