"""V17 platform tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _temp_db():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    return db, path


def test_v17_tables():
    db, path = _temp_db()
    try:
        with db.get_connection() as conn:
            for t in ("erp_plugins", "erp_business_rules", "erp_workflow_definitions", "erp_scripts", "erp_webhooks"):
                assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), t
        print("PASS v17 tables")
    finally:
        os.unlink(path)


def test_rule_engine():
    db, path = _temp_db()
    try:
        from application.rules.engine import evaluate_rules, assert_rules
        r = evaluate_rules("price", {"rate": 0})
        assert any(not x.passed for x in r)
        assert_rules("price", {"rate": 10})
        print("PASS rule engine")
    finally:
        os.unlink(path)


def test_workflow():
    db, path = _temp_db()
    try:
        from application.workflows.designer import can_transition, apply_transition
        ok, ns = can_transition("sales_invoice", "draft", "submit")
        assert ok
        ns2 = apply_transition("sales_invoice", "draft", "submit", {})
        assert ns2 == "submitted"
        print("PASS workflow designer")
    finally:
        os.unlink(path)


def test_script_sandbox():
    db, path = _temp_db()
    try:
        from application.scripts.sandbox import validate_script, run_scripts, save_script
        body = "context['x'] = context.get('y', 0) + 1"
        validate_script(body)
        save_script("T1", "Test", "before_save", body, "sales_invoice")
        ctx = run_scripts("before_save", "sales_invoice", {"y": 5})
        assert ctx.get("x") == 6
        try:
            validate_script("import os")
            assert False
        except ValueError:
            pass
        print("PASS script sandbox")
    finally:
        os.unlink(path)


def test_plugins():
    from plugins.loader import discover_plugins
    from plugins.sdk import REGISTRY
    n = discover_plugins()
    assert n >= 1
    assert "com.ifs.sample" in REGISTRY.plugins
    print("PASS plugin SDK")


def test_tenant_coverage():
    db, path = _temp_db()
    try:
        from application.tenant import coverage_report, set_scope, validate_row
        set_scope(1, 1, enforce=True)
        r = coverage_report()
        assert r["coverage_pct"] >= 90
        try:
            validate_row({"company_id": 99}, table="test")
            assert False
        except PermissionError:
            pass
        print("PASS tenant isolation")
    finally:
        os.unlink(path)


def test_migration_engine():
    from infrastructure.migrations.engine import verify_graph, MIGRATION_GRAPH
    ok, errs = verify_graph()
    assert ok, errs
    assert any(m.migration_id == "v17_extensibility" for m in MIGRATION_GRAPH)
    print("PASS migration engine")


def test_event_bus_multi():
    db, path = _temp_db()
    try:
        from infrastructure.events.bus import publish_simple, subscribe
        from domain.events import INVOICE_CREATED
        hits = []
        subscribe(INVOICE_CREATED, lambda e: hits.append(1))
        subscribe(INVOICE_CREATED, lambda e: hits.append(2))
        publish_simple(INVOICE_CREATED, aggregate_type="invoice", aggregate_id=1)
        assert hits == [1, 2]
        print("PASS multi-subscriber events")
    finally:
        os.unlink(path)


def test_prometheus():
    from infrastructure.observability.prometheus import inc, export_prometheus
    inc("test_counter")
    body = export_prometheus()
    assert "ifs_test_counter" in body
    print("PASS prometheus export")


if __name__ == "__main__":
    test_v17_tables()
    test_rule_engine()
    test_workflow()
    test_script_sandbox()
    test_plugins()
    test_tenant_coverage()
    test_migration_engine()
    test_event_bus_multi()
    test_prometheus()
    print("All V17 platform tests passed.")
