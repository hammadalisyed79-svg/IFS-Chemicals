"""Playwright UI automation — V17.3 (PASS/FAIL evidence)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STREAMLIT_PORT = 8510
BASE = f"http://localhost:{STREAMLIT_PORT}"


def _prepare_db():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["IFS_DB_PATH"] = path
    db.DB_PATH = Path(path)
    db.reset_runtime_state()
    db.init_db()
    from tests._bootstrap import set_ci_admin, CI_ADMIN_PASSWORD
    set_ci_admin(db)
    return path, CI_ADMIN_PASSWORD


def _login(page, password: str) -> None:
    user = page.locator('input[placeholder="Enter username"]')
    if user.count():
        user.fill("admin")
        page.locator('input[placeholder="Enter password"]').fill(password)
        page.get_by_role("button", name="Sign In").click()
        page.wait_for_timeout(5000)


def test_ui_automation():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL playwright not installed")
        sys.exit(1)

    db_path, password = _prepare_db()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
            "--server.port", str(STREAMLIT_PORT), "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(ROOT),
        env={**os.environ, "IFS_DB_PATH": db_path},
    )
    try:
        time.sleep(14)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE, timeout=90000)
            page.wait_for_timeout(3000)
            _login(page, password)
            content = page.content()
            assert "Dashboard" in content or "Customers" in content or "IFS" in content, "Login/dashboard failed"

            # Search / filter smoke — enterprise search if visible
            search = page.locator('input[placeholder*="Search"], input[aria-label*="Search"]')
            if search.count():
                search.first.fill("SI")
                page.wait_for_timeout(1500)

            # Navigate Customers screen via sidebar text if present
            cust = page.get_by_text("Customers", exact=True)
            if cust.count():
                cust.first.click()
                page.wait_for_timeout(3000)
                assert "Customer" in page.content()

            browser.close()
        print("PASS Playwright login, dashboard, navigation smoke")
    except Exception as exc:
        print(f"FAIL Playwright UI: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.unlink(db_path)


if __name__ == "__main__":
    test_ui_automation()
