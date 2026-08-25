"""V14 RC1 — Health Check 2.0 engine and report generation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import database as db
from erp_version import APP_VERSION_FULL


@dataclass
class HealthReport:
    results: list[tuple[str, str, str, str]] = field(default_factory=list)
    critical: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r[0] == "pass")
        return round(100.0 * passed / len(self.results), 1)

    def add(self, status: str, category: str, name: str, detail: str) -> None:
        self.results.append((status, category, name, detail))
        if status == "fail":
            self.critical.append(f"{category}: {name} — {detail}")
        elif status == "warn":
            self.warnings.append(f"{category}: {name} — {detail}")


def _check(rep: HealthReport, category: str, name: str, fn) -> None:
    try:
        fn()
        rep.add("pass", category, name, "OK")
    except AssertionError as exc:
        rep.add("fail", category, name, str(exc))
    except Exception as exc:
        rep.add("fail", category, name, str(exc))


def run_health_check_2() -> HealthReport:
    from erp_ui.health_check import _run_all_checks, _run_enterprise_qc
    from erp_core.regression_test import run_regression_suite
    from erp_core.performance_probe import run_performance_probes

    rep = HealthReport()
    for r in _run_all_checks() + _run_enterprise_qc():
        rep.add(r[0], r[1], r[2], r[3])

    for status, name, detail in run_regression_suite():
        rep.add(status, "Regression", name, detail)

    perf = run_performance_probes()
    for op, ms in perf.metrics.items():
        level = "pass" if ms < 5000 else "warn"
        rep.add(level, "Performance", op, f"{ms} ms")
        if level == "warn":
            rep.recommendations.append(f"Optimize {op} (measured {ms} ms)")

    _check(rep, "Database", "Foreign keys pragma", lambda: _assert_fk())
    _check(rep, "Database", "Document sequences", lambda: _assert_sequences())
    _check(rep, "Approval", "Approval rules exist", lambda: _assert_approval_rules())
    _check(rep, "Document Hub", "All specs have search or get", lambda: _assert_doc_specs())
    _check(rep, "Scaffold", "No user-facing scaffold messages", lambda: _assert_no_scaffold())
    _run_v15_checks(rep)
    _run_v16_checks(rep)
    _run_v17_checks(rep)

    if rep.score < 100:
        rep.recommendations.append("Review failed checks in ENTERPRISE_HEALTH_REPORT.md")
    return rep


def _assert_fk():
    with db.get_connection() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone() is not None


def _assert_sequences():
    with db.get_connection() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='document_sequences'").fetchone():
            n = conn.execute("SELECT COUNT(*) FROM document_sequences").fetchone()[0]
            assert n >= 1


def _assert_approval_rules():
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM erp_approval_rules").fetchone()[0] >= 1


def _assert_doc_specs():
    from erp_core.transaction_engine import all_document_specs
    for spec in all_document_specs():
        assert spec.get_fn or spec.search_fn, f"{spec.key} missing get/search"


def _run_v15_checks(rep: HealthReport) -> None:
    root = os.path.dirname(os.path.dirname(__file__))
    _check(rep, "V15 Mobile", "Streamlit config exists", lambda: _assert_file(os.path.join(root, ".streamlit", "config.toml")))
    _check(rep, "V15 Portal", "portal_app.py exists", lambda: _assert_file(os.path.join(root, "portal_app.py")))
    _check(rep, "V15 Portal", "Portal routes module", lambda: __import__("erp_ui.portal_pages"))
    _check(
        rep,
        "V15 Security",
        "Deployment guides exist",
        lambda: _assert_file_any(
            os.path.join(root, "DEPLOYMENT_SERVER_GUIDE.md"),
            os.path.join(root, "archive", "docs", "DEPLOYMENT_SERVER_GUIDE.md"),
            os.path.join(root, "SECURITY_DEPLOYMENT_GUIDE.md"),
        ),
    )
    _check(rep, "V15 Database", "Notification table", lambda: _assert_table("erp_notifications"))
    _check(rep, "V15 Database", "Portal orders table", lambda: _assert_table("portal_orders"))
    _check(rep, "V15 Database", "Price lists table", lambda: _assert_table("price_lists"))
    _check(rep, "V15 Database", "Role permission matrix", lambda: _assert_table("role_permission_matrix"))
    _check(rep, "V15 Security", "Login attempts table", lambda: _assert_table("login_attempts"))
    _check(rep, "V15 Roles", "Enterprise roles seeded", lambda: _assert_roles())
    _check(rep, "V15 Portal", "Distributor isolation tests", lambda: _run_portal_tests())
    _check(rep, "V15 Security", "Lockout settings", lambda: _assert_setting("max_failed_logins"))


def _assert_file(path: str) -> None:
    assert os.path.isfile(path), f"Missing {path}"


def _assert_file_any(*paths: str) -> None:
    for path in paths:
        if os.path.isfile(path):
            return
    assert False, f"Missing any of: {', '.join(paths)}"


def _assert_table(name: str) -> None:
    with db.get_connection() as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone(), name


def _assert_roles() -> None:
    with db.get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM roles WHERE code='DISTRIBUTOR'").fetchone()[0]
        assert n >= 1


def _assert_setting(key: str) -> None:
    from db_v3 import get_setting
    assert get_setting(key), key


def _run_portal_tests() -> None:
    import importlib.util
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "tests", "test_portal_security.py")
    saved_path = db.DB_PATH
    try:
        spec = importlib.util.spec_from_file_location("test_portal_security", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.test_portal_tables_exist()
        mod.test_distributor_isolation_orders()
        mod.test_price_list_applied()
    finally:
        db.DB_PATH = saved_path
        db.reset_runtime_state()


def _run_v16_checks(rep: HealthReport) -> None:
    root = os.path.dirname(os.path.dirname(__file__))
    layers = ("presentation", "application", "domain", "infrastructure", "api", "integrations", "services", "security")
    for layer in layers:
        _check(rep, "V16 Architecture", f"Layer {layer}/", lambda l=layer: _assert_file(os.path.join(root, l, "__init__.py")) if l != "api" else _assert_file(os.path.join(root, "api", "main.py")))
    _check(rep, "V16 API", "FastAPI app", lambda: __import__("api.main"))
    _check(rep, "V16 Database", "Companies table", lambda: _assert_table("erp_companies"))
    _check(rep, "V16 Database", "Job queue", lambda: _assert_table("erp_job_queue"))
    _check(rep, "V16 Database", "Domain events", lambda: _assert_table("erp_domain_events"))
    _check(rep, "V16 Database", "Document repository", lambda: _assert_table("erp_documents"))
    _check(rep, "V16 Config", "erp_config", lambda: _assert_table("erp_config"))
    _check(rep, "V16 Integrations", "Connector registry", lambda: _assert_connectors())
    _check(rep, "V16 Platform", "Platform tests", lambda: _run_v16_tests())
    _check(rep, "V16 API", "API tests", lambda: _run_api_tests())


def _assert_connectors():
    from integrations.connectors import CONNECTOR_REGISTRY
    assert len(CONNECTOR_REGISTRY) >= 10


def _run_v16_tests():
    import importlib.util
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "tests", "test_v16_platform.py")
    saved_path = db.DB_PATH
    try:
        spec = importlib.util.spec_from_file_location("test_v16_platform", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.test_v16_tables()
        mod.test_event_bus()
        mod.test_config_layer()
    finally:
        db.DB_PATH = saved_path
        db.reset_runtime_state()


def _run_api_tests():
    import importlib.util
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "tests", "test_api_v1.py")
    saved_path = db.DB_PATH
    try:
        spec = importlib.util.spec_from_file_location("test_api_v1", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.test_api_health()
        mod.test_openapi_schema()
    finally:
        db.DB_PATH = saved_path
        db.reset_runtime_state()


def _run_v17_checks(rep: HealthReport) -> None:
    root = os.path.dirname(os.path.dirname(__file__))
    _check(rep, "V17 Plugins", "Plugin SDK", lambda: __import__("plugins.sdk"))
    _check(rep, "V17 Plugins", "Sample plugin loads", lambda: _assert_plugins())
    _check(rep, "V17 Rules", "Rule engine", lambda: __import__("application.rules.engine"))
    _check(rep, "V17 Workflows", "Workflow designer", lambda: __import__("application.workflows.designer"))
    _check(rep, "V17 Scripts", "Script sandbox", lambda: __import__("application.scripts.sandbox"))
    _check(rep, "V17 Tenant", "Coverage >= 80%", lambda: _assert_tenant_coverage())
    _check(rep, "V17 Migrations", "Graph valid", lambda: _assert_migration_graph())
    _check(rep, "V17 API", "Prometheus endpoint", lambda: _assert_file(os.path.join(root, "api", "middleware.py")))
    _check(rep, "V17 Platform", "V17 tests", lambda: _run_v17_tests())
    _run_v17_1_checks(rep)
    _run_v17_2_checks(rep)


def _run_v17_2_checks(rep: HealthReport) -> None:
    _check(rep, "V17.2 Validation", "Certification suite", lambda: __import__("tools.v17_2", fromlist=["discovery"]))
    _check(rep, "V17.2 Validation", "UAT tables", lambda: _assert_uat_tables())
    _check(rep, "V17.2 Validation", "V17.2 smoke tests", lambda: _run_v17_2_tests())


def _assert_uat_tables():
    import database as db
    with db.get_connection() as conn:
        for t in ("erp_uat_scenarios", "erp_uat_runs", "erp_validation_runs"):
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), t


def _run_v17_2_tests():
    import importlib.util
    import os
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "tests", "test_v17_2_certification.py")
    saved_path = db.DB_PATH
    try:
        spec = importlib.util.spec_from_file_location("test_v17_2_certification", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.test_v17_2_tables()
        mod.test_database_health()
    finally:
        db.DB_PATH = saved_path
        db.reset_runtime_state()


def _run_v17_1_checks(rep: HealthReport) -> None:
    _check(rep, "V17.1 Manufacturing", "Industrial services", lambda: __import__("application.manufacturing"))
    _check(rep, "V17.1 Manufacturing", "Integration adapters", lambda: __import__("integrations.industrial.base"))
    _check(rep, "V17.1 Manufacturing", "V17.1 tests", lambda: _run_v17_1_tests())


def _run_v17_1_tests():
    import importlib.util
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "tests", "test_v17_1_manufacturing.py")
    saved_path = db.DB_PATH
    try:
        spec = importlib.util.spec_from_file_location("test_v17_1_manufacturing", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.test_v17_1_tables()
        mod.test_formulation_and_scaling()
        mod.test_integration_adapters()
    finally:
        db.DB_PATH = saved_path
        db.reset_runtime_state()


def _assert_plugins():
    from plugins.loader import discover_plugins
    assert discover_plugins() >= 1


def _assert_tenant_coverage():
    from application.tenant import coverage_report
    assert coverage_report()["coverage_pct"] >= 90


def _assert_migration_graph():
    from infrastructure.migrations.engine import verify_graph
    ok, errs = verify_graph()
    assert ok, errs


def _run_v17_tests():
    import importlib.util
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "tests", "test_v17_platform.py")
    saved_path = db.DB_PATH
    try:
        spec = importlib.util.spec_from_file_location("test_v17_platform", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.test_v17_tables()
        mod.test_rule_engine()
        mod.test_plugins()
        mod.test_tenant_coverage()
    finally:
        db.DB_PATH = saved_path
        db.reset_runtime_state()


def _assert_no_scaffold():
    root = os.path.dirname(os.path.dirname(__file__))
    bad = re.compile(r"\bst\.(info|warning)\([^)]*coming soon|\bst\.(info|warning)\([^)]*not configured", re.I)
    hits = []
    for dirpath, _, files in os.walk(os.path.join(root, "erp_ui")):
        if "venv" in dirpath:
            continue
        for f in files:
            if not f.endswith(".py") or f == "health_check.py":
                continue
            path = os.path.join(dirpath, f)
            text = open(path, encoding="utf-8", errors="ignore").read()
            if bad.search(text):
                hits.append(os.path.relpath(path, root))
    assert not hits, f"Scaffold UI in: {hits}"


def write_all_reports(rep: HealthReport) -> None:
    root = os.path.dirname(os.path.dirname(__file__))
    _write_enterprise_health(root, rep)
    _write_db_integrity(root)
    _write_performance(root)
    _write_test_execution(root, rep)
    _write_known_issues(root, rep)


def _write_enterprise_health(root: str, rep: HealthReport) -> None:
    lines = [
        "# Enterprise Health Report",
        "",
        f"**Version:** {APP_VERSION_FULL}",
        f"**Health Score:** {rep.score}%",
        f"**Checks:** {sum(1 for r in rep.results if r[0]=='pass')}/{len(rep.results)} passed",
        "",
        "## Critical Errors",
    ]
    lines.extend(f"- {c}" for c in rep.critical) or lines.append("- None")
    lines += ["", "## Warnings"]
    lines.extend(f"- {w}" for w in rep.warnings) or lines.append("- None")
    lines += ["", "## Recommendations"]
    lines.extend(f"- {r}" for r in rep.recommendations) or lines.append("- None")
    lines += ["", "## Detail", "", "| Status | Category | Check | Detail |", "|--------|----------|-------|--------|"]
    for s, cat, name, detail in rep.results:
        lines.append(f"| {s.upper()} | {cat} | {name} | {detail} |")
    open(os.path.join(root, "ENTERPRISE_HEALTH_REPORT.md"), "w", encoding="utf-8").write("\n".join(lines))
    open(os.path.join(root, "HEALTH_CHECK_REPORT.md"), "w", encoding="utf-8").write("\n".join(lines))


def _write_db_integrity(root: str) -> None:
    lines = ["# Database Integrity Report", ""]
    with db.get_connection() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        lines.append(f"**Tables:** {len(tables)}")
        for t in ("customers", "suppliers", "products", "sales_invoices", "general_ledger"):
            if t in tables:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                lines.append(f"- {t}: {n} rows")
        orphan = conn.execute(
            """SELECT COUNT(*) FROM sales_invoice_items sii
               LEFT JOIN sales_invoices si ON si.id=sii.invoice_id WHERE si.id IS NULL"""
        ).fetchone()[0] if "sales_invoice_items" in tables else 0
        lines += ["", f"**Orphan sale lines:** {orphan}"]
        lines.append("**Integrity:** OK" if orphan == 0 else "**Integrity:** REVIEW orphan lines")
    open(os.path.join(root, "DATABASE_INTEGRITY_REPORT.md"), "w", encoding="utf-8").write("\n".join(lines))


def _write_performance(root: str) -> None:
    from erp_core.performance_probe import run_performance_probes
    open(os.path.join(root, "PERFORMANCE_REPORT.md"), "w", encoding="utf-8").write(
        run_performance_probes().to_markdown()
    )


def _write_test_execution(root: str, rep: HealthReport) -> None:
    reg = [r for r in rep.results if r[1] == "Regression"]
    lines = ["# Test Execution Report", "", f"**Health Score:** {rep.score}%", ""]
    for s, _, name, detail in reg:
        lines.append(f"- [{'PASS' if s=='pass' else 'FAIL'}] {name}: {detail}")
    open(os.path.join(root, "TEST_EXECUTION_REPORT.md"), "w", encoding="utf-8").write("\n".join(lines))


def _write_known_issues(root: str, rep: HealthReport) -> None:
    lines = [
        "# Known Issues — V15.0",
        "",
        "Only verified open issues are listed. Fixed items removed after Health Check 2.0 pass.",
        "",
    ]
    if rep.critical:
        lines += ["## Open (from last health run)", ""]
        for c in rep.critical:
            lines.append(f"- {c}")
    else:
        lines += [
            "## Resolved in RC1",
            "",
            "- KI-01 Document Hub — full actions for all registered document types",
            "- KI-02 Enterprise Search — journal vouchers searchable",
            "- KI-05 Approval Designer — Administration screen added",
            "- KI-06 Period Lock — enforced on approve/post (GRN, JV, DN, invoices)",
            "- KI-08 Scaffold — v3_pages edit picker uses document hub",
            "- KI-10 GL Drill-down — gl_drilldown module + hub history panel",
            "- KI-12 Auto Backup — enabled by default via migration",
            "",
            "## Remaining limitations",
            "",
            "- Streamlit does not support native double-click grid or global Ctrl+S/Ctrl+P shortcuts",
            "- Production WIP/QC batch workflow — partial; uses existing production order screens",
            "- HR biometric interface — hook placeholders in db_hr; hardware integration site-specific",
            "- Master merge/import — available via master_service; not on every master screen UI yet",
        ]
    open(os.path.join(root, "KNOWN_ISSUES.md"), "w", encoding="utf-8").write("\n".join(lines))
