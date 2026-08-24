"""Ensure every sidebar screen is routable and permission-mapped."""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from erp_ui.nav import NAV_GROUPS, SCREEN_PERMISSION  # noqa: E402


def _pages_keys_from_app() -> set[str]:
    path = os.path.join(ROOT, "app.py")
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "PAGES" and isinstance(node.value, ast.Dict):
                keys = []
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.append(key.value)
                return set(keys)
    raise AssertionError("PAGES dict not found in app.py")


def test_nav_screens_have_handlers():
    pages = _pages_keys_from_app()
    missing = []
    for group, screens in NAV_GROUPS.items():
        for screen in screens:
            if screen not in pages:
                missing.append(f"{group} → {screen}")
    assert not missing, "PAGES missing:\n" + "\n".join(missing)


def test_screen_permission_coverage():
    missing_perm = []
    for _group, screens in NAV_GROUPS.items():
        for screen in screens:
            if screen not in SCREEN_PERMISSION:
                missing_perm.append(screen)
    assert not missing_perm, "SCREEN_PERMISSION missing:\n" + "\n".join(missing_perm)


if __name__ == "__main__":
    test_nav_screens_have_handlers()
    test_screen_permission_coverage()
    print("OK nav wiring")
