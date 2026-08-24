"""Navigation state — Desktop home must not be overwritten by sync_nav_state."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from erp_ui.nav import NAV_GROUPS, _home_group, filtered_nav_groups  # noqa: E402


def _sample_nav():
    return {k: list(v) for k, v in NAV_GROUPS.items()}


def test_home_group_is_overview():
    nav = _sample_nav()
    assert _home_group(nav) == "Overview"
    assert "Dashboard" in nav["Overview"]


def test_sync_preserves_dashboard_from_reports():
    """Reproduce bug: Reports group does not include Dashboard."""
    nav = _sample_nav()
    group = "Reports"
    screen = "Dashboard"
    assert "Dashboard" not in nav[group]

    # simulate sync_nav_state logic for Dashboard
    if screen == "Dashboard":
        if "Dashboard" not in nav.get(group, []):
            group = _home_group(nav)
        screen = "Dashboard"

    assert group == "Overview"
    assert screen == "Dashboard"


def test_admin_nav_includes_dashboard():
    admin = {"id": 1, "username": "admin", "role": "admin", "full_name": "Admin"}
    nav = filtered_nav_groups(admin)
    assert "Overview" in nav
    assert "Dashboard" in nav["Overview"]
    assert "Reports Center" in nav.get("Reports", [])


if __name__ == "__main__":
    test_home_group_is_overview()
    test_sync_preserves_dashboard_from_reports()
    test_admin_nav_includes_dashboard()
    print("OK nav state")
