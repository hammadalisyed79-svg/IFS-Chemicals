"""UI shell tests — no database required."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_page_shell_status_meta():
    from erp_ui.page_shell import SHELL_STATUS_META, shell_status_badge
    assert "shadow" in SHELL_STATUS_META
    html = shell_status_badge("shadow", kind="shell")
    assert "Shadow" in html


def test_icons_module():
    from erp_ui.icons import icon_for, GROUP_ICONS
    assert icon_for("Finance", GROUP_ICONS) == "₨"


if __name__ == "__main__":
    test_page_shell_status_meta()
    test_icons_module()
    print("OK ui shell")
