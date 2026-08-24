"""Remove WS-C / WS-S / WS-P masters created by weighbridge import; keep FMYE codes only.

Also clear those FKs on weight_slips (optionally rematch party by name to FMYE).

Usage:
  python cleanup_ws_parties.py           # preview
  python cleanup_ws_parties.py --apply   # delete
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db


def _norm(s: str | None) -> str:
    s = (s or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^A-Z0-9 &./\-]", "", s)
    return s


def run(*, apply: bool) -> dict:
    stats = {
        "ws_c": 0,
        "ws_s": 0,
        "ws_p": 0,
        "slips_cleared_cust": 0,
        "slips_cleared_sup": 0,
        "slips_rematched_cust": 0,
        "slips_rematched_sup": 0,
        "prod_links_cleared": 0,
    }
    db.init_db()
    with db.get_connection() as conn:
        # Build FMYE-only party maps (exclude WS-*)
        fmye_cust = {}
        for r in conn.execute(
            "SELECT id, name FROM customers WHERE code NOT LIKE 'WS-C-%' AND is_active=1"
        ):
            fmye_cust.setdefault(_norm(r["name"]), r["id"])
        fmye_sup = {}
        for r in conn.execute(
            "SELECT id, name FROM suppliers WHERE code NOT LIKE 'WS-S-%' AND is_active=1"
        ):
            fmye_sup.setdefault(_norm(r["name"]), r["id"])

        # Rematch / clear weight_slips customer links
        for r in conn.execute(
            """SELECT ws.id, c.name FROM weight_slips ws
               JOIN customers c ON c.id = ws.customer_id
               WHERE c.code LIKE 'WS-C-%'"""
        ).fetchall():
            fid = fmye_cust.get(_norm(r["name"]))
            if apply:
                if fid:
                    conn.execute(
                        "UPDATE weight_slips SET customer_id=?, party_type='customer' WHERE id=?",
                        (fid, r["id"]),
                    )
                    stats["slips_rematched_cust"] += 1
                else:
                    conn.execute(
                        "UPDATE weight_slips SET customer_id=NULL WHERE id=?", (r["id"],)
                    )
                    stats["slips_cleared_cust"] += 1
            else:
                if fid:
                    stats["slips_rematched_cust"] += 1
                else:
                    stats["slips_cleared_cust"] += 1

        for r in conn.execute(
            """SELECT ws.id, s.name FROM weight_slips ws
               JOIN suppliers s ON s.id = ws.supplier_id
               WHERE s.code LIKE 'WS-S-%'"""
        ).fetchall():
            fid = fmye_sup.get(_norm(r["name"]))
            if apply:
                if fid:
                    conn.execute(
                        "UPDATE weight_slips SET supplier_id=?, party_type='supplier' WHERE id=?",
                        (fid, r["id"]),
                    )
                    stats["slips_rematched_sup"] += 1
                else:
                    conn.execute(
                        "UPDATE weight_slips SET supplier_id=NULL WHERE id=?", (r["id"],)
                    )
                    stats["slips_cleared_sup"] += 1
            else:
                if fid:
                    stats["slips_rematched_sup"] += 1
                else:
                    stats["slips_cleared_sup"] += 1

        # Clear product FK on slips pointing at WS-P products
        n = conn.execute(
            """SELECT COUNT(*) FROM weight_slips ws
               JOIN products p ON p.id = ws.product_id WHERE p.code LIKE 'WS-P-%'"""
        ).fetchone()[0]
        stats["prod_links_cleared"] = n
        if apply and n:
            conn.execute(
                """UPDATE weight_slips SET product_id=NULL
                   WHERE product_id IN (SELECT id FROM products WHERE code LIKE 'WS-P-%')"""
            )

        stats["ws_c"] = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE code LIKE 'WS-C-%'"
        ).fetchone()[0]
        stats["ws_s"] = conn.execute(
            "SELECT COUNT(*) FROM suppliers WHERE code LIKE 'WS-S-%'"
        ).fetchone()[0]
        stats["ws_p"] = conn.execute(
            "SELECT COUNT(*) FROM products WHERE code LIKE 'WS-P-%'"
        ).fetchone()[0]

        if apply:
            conn.execute("DELETE FROM customers WHERE code LIKE 'WS-C-%'")
            conn.execute("DELETE FROM suppliers WHERE code LIKE 'WS-S-%'")
            conn.execute("DELETE FROM products WHERE code LIKE 'WS-P-%'")

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    st = run(apply=args.apply)
    mode = "APPLIED" if args.apply else "PREVIEW"
    print(f"[{mode}] Remove weighbridge-created WS-* masters (keep FMYE codes)")
    print(f"  WS-C customers: {st['ws_c']}")
    print(f"  WS-S suppliers: {st['ws_s']}")
    print(f"  WS-P products:  {st['ws_p']}")
    print(f"  Slips rematch customer->FMYE: {st['slips_rematched_cust']}")
    print(f"  Slips clear customer:        {st['slips_cleared_cust']}")
    print(f"  Slips rematch supplier->FMYE: {st['slips_rematched_sup']}")
    print(f"  Slips clear supplier:        {st['slips_cleared_sup']}")
    print(f"  Slips clear WS-P product:    {st['prod_links_cleared']}")
    if not args.apply:
        print("Run with --apply to delete.")


if __name__ == "__main__":
    main()
