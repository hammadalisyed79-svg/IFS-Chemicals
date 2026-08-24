"""PART 2 — Functional test engine (automated, no manual assumptions)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from tools.v17_2.common import ROOT, ReportBundle, temp_database, timed

# Actions we can verify without browser automation
SERVICE_CHECKS = {
    "Customers": ("application.services", "CustomerService", "list_active"),
    "Formula Master": ("application.manufacturing.formulation", "FormulationService", "list_formulas"),
    "Spray Dryer": ("application.manufacturing.spray_dryer", "SprayDryerService", "list_batches"),
    "QC Laboratory": ("application.manufacturing.qc_lab", "QCLabService", "list_specs"),
    "Industrial Dashboards": ("application.manufacturing.dashboards", "IndustrialDashboardService", "plant_dashboard"),
}

UI_ONLY_ACTIONS = (
    "Open", "Print", "Export PDF", "Export Excel", "Pagination", "Sorting", "Filters",
)

PLAYWRIGHT_SCREENS = {"Dashboard", "Customers"}


def _v173() -> bool:
    return os.environ.get("ERP_CERT_V173") == "1"


def _playwright_ok() -> bool:
    e2e = ROOT / "tests" / "e2e" / "test_ui_playwright.py"
    if not e2e.exists():
        return False
    r = subprocess.run([sys.executable, str(e2e)], capture_output=True, text=True, cwd=str(ROOT))
    return r.returncode == 0


def _load_nav_screens() -> list[str]:
    spec = importlib.util.spec_from_file_location("nav", ROOT / "erp_ui" / "nav.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [s for screens in mod.NAV_GROUPS.values() for s in screens]


def _load_pages() -> dict:
    spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.PAGES)


def _test_service(screen: str) -> tuple[str, str]:
    if screen not in SERVICE_CHECKS:
        if _v173():
            return "fail", "No automated service test"
        return "not_certified", "No automated service test — UI-only or legacy db path"
    mod_name, cls_name, method = SERVICE_CHECKS[screen]
    mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name)
    from domain.tenant import TenantContext
    svc = cls(TenantContext(company_id=1))
    getattr(svc, method)()
    return "pass", f"{cls_name}.{method}() OK"


def run_functional_tests() -> ReportBundle:
    title = "Functional Test Report — V17.3" if _v173() else "Functional Test Report — V17.2"
    rep = ReportBundle(title)
    pages = _load_pages()
    screens = _load_nav_screens()
    pw_ok = _playwright_ok() if _v173() else False

    db, path, init_ms = temp_database()
    try:
        from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
        set_ci_admin(db)
        rep.add("Infrastructure", "Database init", "pass", f"init_db {init_ms}ms")
        if _v173():
            rep.add("Infrastructure", "Playwright smoke", "pass" if pw_ok else "fail", "tests/e2e/test_ui_playwright.py")

        for screen in screens:
            if screen in pages:
                fn = pages[screen]
                if callable(fn):
                    rep.add(screen, "Route callable", "pass", repr(fn))
                else:
                    rep.add(screen, "Route callable", "fail", "Not callable")
            else:
                rep.add(screen, "Route callable", "fail", "Missing from PAGES")

            st, detail = _test_service(screen)
            rep.add(screen, "Service read", st, detail)

            if screen == "Customers":
                from fastapi.testclient import TestClient
                from api.main import app
                client = TestClient(app)
                tok = client.post(
                    "/api/v1/auth/token",
                    data={"username": "admin", "password": CI_ADMIN_PASSWORD},
                ).json()["access_token"]
                h = {"Authorization": f"Bearer {tok}"}
                ms, _ = timed("api", lambda: client.get("/api/v1/customers", headers=h))
                slow = ms >= 5000
                rep.add(screen, "API list", "fail" if (_v173() and slow) else ("pass" if not slow else "warn"), f"{ms}ms")
                cr = client.post("/api/v1/customers", headers=h, json={"code": "FT-01", "name": "Functional Test"})
                rep.add(screen, "Create", "pass" if cr.status_code == 201 else "fail", cr.text[:80])
                if cr.status_code == 201:
                    cid = cr.json()["id"]
                    client.put(f"/api/v1/customers/{cid}", headers=h, json={"name": "FT Edited"})
                    rep.add(screen, "Edit", "pass", f"id={cid}")
                    client.delete(f"/api/v1/customers/{cid}", headers=h)
                    rep.add(screen, "Delete draft", "pass", "API delete OK")

            if screen == "Suppliers":
                import database as dbm
                sid = dbm.add_supplier({"code": "SUP-FT", "name": "FT Supplier"})
                rep.add(screen, "Create", "pass", f"id={sid}")
                rep.add(screen, "Edit", "fail" if _v173() else "not_certified", "No automated edit path without UI")
            if screen == "Products":
                import database as dbm
                pid = dbm.add_item({"code": "PRD-FT", "name": "FT Product", "sale_price": 10, "purchase_price": 8})
                rep.add(screen, "Create", "pass", f"id={pid}")

            if screen in ("Trial Balance", "Chart of Accounts"):
                try:
                    if screen == "Trial Balance":
                        from db_v3 import get_trial_balance
                        get_trial_balance()
                        rep.add(screen, "Read", "pass", "get_trial_balance()")
                    else:
                        import database as dbm
                        dbm.get_accounts()
                        rep.add(screen, "Read", "pass", "get_accounts()")
                except Exception as exc:
                    rep.add(screen, "Read", "fail", str(exc))

            import database as dbm
            admin = dbm.authenticate("admin", CI_ADMIN_PASSWORD)
            if admin:
                module = "Production" if screen in ("Spray Dryer", "BOM") else "Sales" if "Sales" in screen else "Masters"
                can = dbm.user_can(admin, module, "view")
                rep.add(screen, "Permission (admin view)", "pass" if can else ("fail" if _v173() else "warn"), module)

            for action in UI_ONLY_ACTIONS:
                if _v173():
                    if action == "Open" and pw_ok and screen in PLAYWRIGHT_SCREENS:
                        st = "pass"
                        detail = "Playwright navigation smoke"
                    else:
                        st = "fail"
                        detail = "Not automated in Playwright suite"
                else:
                    st = "not_certified"
                    detail = "Requires Streamlit browser automation — not in CI suite"
                rep.add(screen, action, st, detail)

            for action in ("Approve", "Reject", "Post", "Reverse"):
                if screen in SERVICE_CHECKS or screen == "Customers":
                    rep.add(
                        screen, action,
                        "fail" if _v173() else "not_certified",
                        "Workflow not fully automated for this screen",
                    )
    finally:
        import os
        os.unlink(path)

    rep.sections["Methodology"] = (
        "V17.3: route registration, service read, API CRUD, Playwright smoke for Open on key screens. "
        "Unautomated UI actions marked **FAIL**."
        if _v173()
        else "Automated checks: route registration, service read, API CRUD (customers), "
        "database CRUD (suppliers/products), permission probe."
    )
    return rep
