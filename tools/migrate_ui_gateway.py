"""Migrate erp_ui and app.py to use application.data_gateway (V17.3 architecture)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "erp_ui", ROOT / "app.py", ROOT / "portal_app.py"]


def migrate_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    original = text
    text = re.sub(r"^import database as db\b", "from application import data_gateway as db", text, flags=re.M)
    text = re.sub(r"^import database\b", "from application import data_gateway as database", text, flags=re.M)
    text = re.sub(r"^from database import ", "from application.data_gateway import ", text, flags=re.M)
    text = re.sub(r"^from db_v3 import ", "from application.data_gateway import ", text, flags=re.M)
    text = re.sub(r"^import db_v3\b", "from application import data_gateway as db_v3", text, flags=re.M)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return 1
    return 0


def main():
    changed = 0
    for target in TARGETS:
        if target.is_dir():
            for p in target.rglob("*.py"):
                changed += migrate_file(p)
        elif target.exists():
            changed += migrate_file(target)
    print(f"Migrated {changed} files to data_gateway.")


if __name__ == "__main__":
    main()
