"""REST API v1 tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _boot():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = __import__("pathlib").Path(path)
    db.reset_runtime_state()
    db.init_db()
    from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
    set_ci_admin(db)
    return db, path, CI_ADMIN_PASSWORD


def test_api_health():
    db, path, _pw = _boot()
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("ok", "degraded")
        print("PASS API health")
    finally:
        os.unlink(path)


def test_api_auth_and_customers():
    db, path, pw = _boot()
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        r = client.post("/api/v1/auth/token", data={"username": "admin", "password": pw})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        r2 = client.get("/api/v1/customers", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        print("PASS API auth + customers")
    finally:
        os.unlink(path)


def test_openapi_schema():
    db, path, _pw = _boot()
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        r = client.get("/api/v1/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "/api/v1/customers" in schema.get("paths", {})
        assert "/api/v1/health" in schema.get("paths", {})
        print("PASS OpenAPI schema")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    test_api_health()
    test_api_auth_and_customers()
    test_openapi_schema()
    print("All API tests passed.")
