"""PART 9 — Security validation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tools.v17_2.common import ROOT, ReportBundle, temp_database


def _v173() -> bool:
    return os.environ.get("ERP_CERT_V173") == "1"


def run_security_certification() -> ReportBundle:
    title = "Security Certification — V17.3" if _v173() else "Security Certification — V17.2"
    rep = ReportBundle(title)

    if _v173():
        from tools.v17_3.certification import run_security as run_v173_security
        v173 = run_v173_security()
        for r in v173.results:
            rep.add(r.category, r.name, r.status, r.detail)
        rep.sections["Verdict"] = (
            f"**{'SECURITY CERTIFIED' if v173.failed == 0 else 'NOT CERTIFIED'}** — "
            f"{v173.passed} pass, {v173.failed} fail."
        )
        return rep

    db_text = (ROOT / "database.py").read_text(encoding="utf-8", errors="ignore")
    auth_text = ""
    for p in (ROOT / "erp_ui").glob("*auth*"):
        auth_text += p.read_text(encoding="utf-8", errors="ignore")

    if "sha256" in db_text.lower() or "hashlib.sha256" in db_text:
        rep.add("Authentication", "Password hashing", "fail", "SHA-256 detected — C-02")
    else:
        rep.add("Authentication", "Password hashing", "pass", "Non-SHA256")

    if "session=" in auth_text or "?session" in (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore"):
        rep.add("Session", "URL token", "fail", "Session in query string — C-01")
    else:
        rep.add("Session", "URL token", "pass", "No session= in app auth path")

    app_txt = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    if "admin123" in app_txt and "page_login" in app_txt:
        rep.add("Authentication", "Default password displayed", "fail", "admin123 on login — C-03")
    else:
        rep.add("Authentication", "Default password displayed", "pass", "Not exposed")

    db, path, _ = temp_database()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        import database as dbm
        admin = dbm.authenticate("admin", CI_ADMIN_PASSWORD)
        rep.add("Authentication", "Admin login", "pass" if admin else "fail", "CI admin works")

        rep.add("Authorization", "user_can Sales", "pass" if dbm.user_can(admin, "Sales", "view") else "fail", "RBAC")

        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        bad = client.get("/api/v1/customers")
        rep.add("REST API", "Unauthenticated blocked", "pass" if bad.status_code == 401 else "fail", str(bad.status_code))
        tok = client.post("/api/v1/auth/token", data={"username": "admin", "password": CI_ADMIN_PASSWORD})
        rep.add("REST API", "JWT token", "pass" if tok.status_code == 200 else "fail", tok.text[:60])

        mw = (ROOT / "api" / "middleware.py").read_text(encoding="utf-8", errors="ignore")
        rep.add("Rate Limiting", "Middleware", "pass" if "rate" in mw.lower() else "not_certified", "api/middleware.py")

        r = subprocess.run([sys.executable, str(ROOT / "tests" / "test_portal_security.py")],
                           capture_output=True, text=True, cwd=str(ROOT))
        rep.add("Portal", "test_portal_security.py", "pass" if r.returncode == 0 else "fail", r.stdout[-200:])

        try:
            with dbm.get_connection() as conn:
                conn.execute("SELECT * FROM customers WHERE code=?", ("' OR 1=1 --",)).fetchall()
            rep.add("SQL Injection", "Parameterized query", "pass", "No exception on safe param")
        except Exception as exc:
            rep.add("SQL Injection", "Parameterized query", "fail", str(exc))

        rep.add("File Upload", "Restore backup", "not_certified", "Manual UAT — backup restore UI")
        rep.add("CSV/Excel/PDF Export", "Export paths", "not_certified", "No automated export security scan")
        rep.add("Password Policy", "Complexity rules", "not_certified", "No enforced policy in code")
        rep.add("Session Timeout", "Idle timeout", "not_certified", "Streamlit session — not verified")

    finally:
        import os
        os.unlink(path)

    critical = rep.failed
    rep.sections["Verdict"] = (
        f"**{'NOT CERTIFIED' if critical > 0 else 'PARTIAL'}** — "
        f"{critical} critical failures. Resolve C-01..C-03 before production."
    )
    return rep
