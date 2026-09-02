"""
Import FMYE11 account/customer groups (Groups + ChartGroup) into ERP master_groups.

Source: import/fmye/full_live/731.dat (Groups) + 728.dat (ChartGroup)

Usage:
  python import_fmye_groups.py                  # preview
  python import_fmye_groups.py --apply          # import all active user groups (Type U)
  python import_fmye_groups.py --apply --only "ZAIDI SB"
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
DEFAULT_EXPORT = ROOT / "import" / "fmye" / "full_live"

# FMYE batches used on chart / GL reports (cash, expense heads, etc.)
ACCOUNT_BATCHES = frozenset({
    "ADVANCES", "CASHBANK", "CHARITY", "EXPENSE", "INCOME", "MACHINERY", "VEHICLES",
})


def _active(flag) -> bool:
    return str(flag or "1").strip().upper() in ("1", "Y", "YES", "T", "TRUE")


def load_fmye_groups(export_dir: Path):
    from import_fmye_from_dat import FMYEExport

    exp = FMYEExport(export_dir)
    headers = [
        g for g in exp.rows("Groups")
        if _active(g.get("Active")) and (g.get("Type") or "").strip().upper() == "U"
    ]
    members: dict[str, list[str]] = defaultdict(list)
    for row in exp.rows("ChartGroup"):
        gcode = (row.get("GroupCode") or "").strip()
        acode = (row.get("AccountCode") or "").strip()
        if gcode and acode:
            members[gcode].append(acode)
    return headers, members


def import_groups(
    export_dir: Path,
    *,
    apply: bool = False,
    only: list[str] | None = None,
    user_id: int = 1,
) -> dict:
    from database import get_connection
    import db_groups
    from db_groups import assign_entities_to_group, resolve_entity_ids_by_codes

    headers, members = load_fmye_groups(export_dir)
    only_set = {s.strip() for s in (only or []) if s and s.strip()} or None
    summary = {"groups": [], "skipped": [], "missing_codes": {}}

    with get_connection() as conn:
        db_groups.apply_master_groups(conn)

    for g in headers:
        gcode = (g.get("GroupCode") or "").strip()
        if not gcode:
            continue
        if only_set and gcode not in only_set:
            continue
        codes = members.get(gcode) or []
        if not codes:
            summary["skipped"].append((gcode, "no ChartGroup members"))
            continue

        entity_type = "account" if gcode in ACCOUNT_BATCHES else "customer"
        name = (g.get("GroupName") or "").strip() or gcode
        tab = "Chart Account Groups" if entity_type == "account" else "Customer Account Groups"

        row = {
            "code": gcode,
            "name": name,
            "entity_type": entity_type,
            "member_codes": codes,
            "tab": tab,
        }
        if not apply:
            found, missing = resolve_entity_ids_by_codes(entity_type, codes)
            row["found"] = len(found)
            row["missing"] = len(missing)
            summary["groups"].append(row)
            if missing:
                summary["missing_codes"][gcode] = missing[:20]
            continue

        with get_connection() as conn:
            db_groups.apply_master_groups(conn)
            existing = conn.execute(
                "SELECT id FROM master_groups WHERE entity_type=? AND code=?",
                (entity_type, gcode),
            ).fetchone()
            if existing:
                group_id = existing["id"]
                conn.execute(
                    """UPDATE master_groups SET name=?, is_active=1, modified_at=datetime('now')
                       WHERE id=?""",
                    (name, group_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO master_groups(entity_type, code, name, sort_order, is_active, created_by)
                       VALUES(?,?,?,?,1,?)""",
                    (entity_type, gcode, name, 0, user_id),
                )
                group_id = cur.lastrowid

        found_ids, missing = resolve_entity_ids_by_codes(entity_type, codes)
        assigned = assign_entities_to_group(entity_type, found_ids, group_id, user_id)
        row["group_id"] = group_id
        row["assigned"] = assigned
        row["missing"] = len(missing)
        summary["groups"].append(row)
        if missing:
            summary["missing_codes"][gcode] = missing[:20]

    return summary


def main():
    p = argparse.ArgumentParser(description="Import FMYE11 groups into ERP master_groups")
    p.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--only", action="append", help='Group code, e.g. "ZAIDI SB"')
    args = p.parse_args()

    if not args.export_dir.exists():
        raise SystemExit(f"Export folder not found: {args.export_dir}")

    summary = import_groups(args.export_dir, apply=args.apply, only=args.only)
    mode = "APPLIED" if args.apply else "PREVIEW"
    print(f"\n=== {mode} ===")
    for g in summary["groups"]:
        if args.apply:
            print(
                f"  {g['code']} ({g['entity_type']}) — {g['assigned']} assigned, "
                f"{g['missing']} missing -> {g['tab']}"
            )
        else:
            print(
                f"  {g['code']} ({g['entity_type']}) — {g['found']}/{len(g['member_codes'])} "
                f"codes in ERP -> {g['tab']}"
            )
    for gcode, reason in summary["skipped"]:
        print(f"  SKIP {gcode}: {reason}")
    if summary["missing_codes"]:
        print("\nMissing account/customer codes (first 20 per group):")
        for gcode, miss in summary["missing_codes"].items():
            print(f"  {gcode}: {', '.join(miss)}")


if __name__ == "__main__":
    main()
