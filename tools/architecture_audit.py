"""Architecture audit — forbidden direct database imports in UI layer."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(r"\bimport\s+database\b"),
    re.compile(r"\bfrom\s+database\s+import"),
    re.compile(r"\bimport\s+db_v3\b"),
    re.compile(r"\bfrom\s+db_v3\s+import"),
)


def scan_forbidden_ui_imports() -> dict:
    violations = []
    paths = [ROOT / "erp_ui", ROOT / "app.py", ROOT / "portal_app.py"]
    for base in paths:
        files = base.rglob("*.py") if base.is_dir() else [base]
        for p in files:
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for pat in PATTERNS:
                if pat.search(text):
                    violations.append(str(p.relative_to(ROOT)))
                    break
    return {"violation_count": len(violations), "violations": violations, "target": 0}


if __name__ == "__main__":
    print(scan_forbidden_ui_imports())
