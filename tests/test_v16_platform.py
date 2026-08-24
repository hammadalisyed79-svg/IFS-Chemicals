"""V16 platform tests — architecture, API, events, jobs, multi-company."""

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


def test_v16_tables():
    db, path = _temp_db()
    try:
        with db.get_connection() as conn:
            for t in (
                "erp_companies", "erp_branches", "erp_config", "erp_documents",
                "erp_job_queue", "erp_domain_events", "erp_integration_connectors",
                "erp_report_designs", "erp_import_batches",
            ):
                assert conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone(), t
        print("PASS v16 tables")
    finally:
        os.unlink(path)


def test_event_bus():
    db, path = _temp_db()
    try:
        from infrastructure.events.bus import publish_simple, subscribe
        from domain import events as E
        received = []
        subscribe(E.CUSTOMER_CREATED, lambda e: received.append(e.event_type))
        publish_simple(E.CUSTOMER_CREATED, aggregate_type="customer", aggregate_id=1, payload={"code": "T"})
        assert received == [E.CUSTOMER_CREATED]
        print("PASS event bus")
    finally:
        os.unlink(path)


def test_job_queue():
    db, path = _temp_db()
    try:
        from infrastructure.jobs.worker import enqueue, fetch_pending, process_jobs
        enqueue("backup", {}, created_by=1)
        assert len(fetch_pending()) >= 1
        n = process_jobs(5)
        assert n >= 0
        print("PASS job queue")
    finally:
        os.unlink(path)


def test_config_layer():
    db, path = _temp_db()
    try:
        from application.config import config
        v = config.get("database", "driver", "sqlite")
        assert v == "sqlite"
        config.set("database", "test_key", "x")
        assert config.get("database", "test_key") == "x"
        print("PASS config layer")
    finally:
        os.unlink(path)


def test_multi_company_seed():
    db, path = _temp_db()
    try:
        with db.get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM erp_companies").fetchone()[0] >= 1
            assert conn.execute("SELECT COUNT(*) FROM erp_branches").fetchone()[0] >= 1
        print("PASS multi-company seed")
    finally:
        os.unlink(path)


def test_document_repository():
    db, path = _temp_db()
    try:
        from services.document_repository import store_document
        from pathlib import Path
        tmp = Path(path).parent / "test_doc.txt"
        tmp.write_text("hello", encoding="utf-8")
        doc_id = store_document(category="pdf", title="Test", source_path=tmp, uploaded_by=1)
        assert doc_id > 0
        tmp.unlink(missing_ok=True)
        print("PASS document repository")
    finally:
        os.unlink(path)


def test_integration_registry():
    from integrations.connectors import CONNECTOR_REGISTRY
    for name in ("shopify", "woocommerce", "whatsapp", "bank_api", "powerbi", "biometric"):
        assert name in CONNECTOR_REGISTRY
    print("PASS integration registry")


def test_db_adapter():
    from infrastructure.database.adapter import get_adapter, SQLiteAdapter
    a = get_adapter()
    assert isinstance(a, SQLiteAdapter)
    print("PASS db adapter")


if __name__ == "__main__":
    test_v16_tables()
    test_event_bus()
    test_job_queue()
    test_config_layer()
    test_multi_company_seed()
    test_document_repository()
    test_integration_registry()
    test_db_adapter()
    print("All V16 platform tests passed.")
