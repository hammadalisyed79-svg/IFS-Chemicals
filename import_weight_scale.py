"""Import modern_weight_scale_final SQLite DB into IFS weighbridge (weight_slips).

Source (default):
  C:\\modern_weight_scale_final\\database\\weight_scale.db

Usage:
  python import_weight_scale.py              # preview
  python import_weight_scale.py --apply     # import all slips
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db

DEFAULT_SRC = Path(r"C:\modern_weight_scale_final\database\weight_scale.db")


def _norm(s: str | None) -> str:
    s = (s or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^A-Z0-9 &./\-]", "", s)
    return s


def _uid() -> int:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1"
        ).fetchone()
    if not row:
        raise SystemExit("No admin user")
    return int(row[0])


def _open_src(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"Source DB not found: {path}")
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def _txn_kind(txn: str | None) -> str:
    t = (txn or "").strip().upper()
    t = re.sub(r"[^A-Z ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if t.startswith("PURCHASE RETURN") or t.startswith("PR"):
        return "purchase_return"
    if t.startswith("SALE RETURN") or t.startswith("SR"):
        return "sale_return"
    if t.startswith("PURCHASE") or t.startswith("PU"):
        return "purchase"
    if t.startswith("SALE") or t.startswith("SAEL") or t.startswith("SA LE"):
        return "sale"
    if t.startswith("TRANSFER"):
        return "transfer"
    return "sale"  # default outward


def _map_status(st: str | None) -> str:
    s = (st or "").strip().upper()
    if s == "COMPLETED":
        return "completed"
    if s == "PENDING":
        return "first_weigh"
    if s == "CANCELLED":
        return "cancelled"
    return "first_weigh"


def preview(src: Path):
    con = _open_src(src)
    n = con.execute("SELECT COUNT(*) FROM weights").fetchone()[0]
    print(f"Source: {src}")
    print(f"  weights: {n}")
    print(f"  parties: {con.execute('SELECT COUNT(*) FROM parties').fetchone()[0]}")
    print(f"  items:   {con.execute('SELECT COUNT(*) FROM items').fetchone()[0]}")
    print(f"  vehicles:{con.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0]}")
    print(
        "  date range:",
        tuple(con.execute("SELECT MIN(entry_date), MAX(entry_date) FROM weights").fetchone()),
    )
    print(
        "  status:",
        dict(con.execute("SELECT status, COUNT(*) FROM weights GROUP BY 1").fetchall()),
    )
    con.close()
    with db.get_connection() as conn:
        print(f"IFS weight_slips now: {conn.execute('SELECT COUNT(*) FROM weight_slips').fetchone()[0]}")


def _ensure_vehicle(conn, vehicle_no: str, driver: str, uid: int) -> int | None:
    vno = (vehicle_no or "").strip().upper()
    if not vno:
        return None
    row = conn.execute(
        "SELECT id FROM vehicles WHERE UPPER(TRIM(registration_no))=?", (vno,)
    ).fetchone()
    if row:
        return row[0]
    code = vno[:20]
    cur = conn.execute(
        """INSERT INTO vehicles(code, registration_no, driver_name, vehicle_type, is_active, created_by)
           VALUES(?,?,?,?,1,?)""",
        (code, vno, (driver or "")[:100], "truck", uid),
    )
    return cur.lastrowid


def _resolve_party(conn, name: str, kind: str, caches: dict, uid: int, stats: dict):
    """Match existing FMYE party by name only — never create WS-C / WS-S accounts."""
    key = _norm(name)
    if not key:
        return None, None, None

    cust_map = caches["cust"]
    sup_map = caches["sup"]

    cid = cust_map.get(key)
    sid = sup_map.get(key)

    want_cust = kind in ("sale", "sale_return", "transfer")
    want_sup = kind in ("purchase", "purchase_return")

    if want_cust:
        if cid:
            return cid, None, "customer"
        stats["party_unmatched"] += 1
        return None, None, None
    if want_sup:
        if sid:
            return None, sid, "supplier"
        stats["party_unmatched"] += 1
        return None, None, None
    if cid:
        return cid, None, "customer"
    if sid:
        return None, sid, "supplier"
    stats["party_unmatched"] += 1
    return None, None, None


def _resolve_product(conn, item_name: str, caches: dict, uid: int, stats: dict) -> int | None:
    """Match existing FMYE product by name/code only — never create WS-P items."""
    key = _norm(item_name)
    if not key:
        return None
    pid = caches["prod"].get(key)
    if pid:
        return pid
    stats["product_unmatched"] += 1
    return None


def apply(src: Path, uid: int, *, replace: bool = False):
    src_con = _open_src(src)
    parties = {r["id"]: dict(r) for r in src_con.execute("SELECT * FROM parties")}
    items = {r["id"]: dict(r) for r in src_con.execute("SELECT * FROM items")}
    vehicles = {r["id"]: dict(r) for r in src_con.execute("SELECT * FROM vehicles")}
    weights = [dict(r) for r in src_con.execute("SELECT * FROM weights ORDER BY id")]
    src_con.close()

    stats = defaultdict(int)

    with db.get_connection() as conn:
        if replace:
            n = conn.execute("DELETE FROM weight_slips").rowcount
            stats["cleared_slips"] = n

        existing = {
            (r[0] or "").strip().upper()
            for r in conn.execute("SELECT document_no FROM weight_slips").fetchall()
        }

        caches = {
            "cust": {
                _norm(r["name"]): r["id"]
                for r in conn.execute(
                    "SELECT id, name FROM customers WHERE code NOT LIKE 'WS-C-%'"
                ).fetchall()
            },
            "sup": {
                _norm(r["name"]): r["id"]
                for r in conn.execute(
                    "SELECT id, name FROM suppliers WHERE code NOT LIKE 'WS-S-%'"
                ).fetchall()
            },
            "prod": {
                _norm(r["name"]): r["id"]
                for r in conn.execute(
                    "SELECT id, name FROM products WHERE code NOT LIKE 'WS-P-%'"
                ).fetchall()
            },
        }
        # also index product codes (FMYE ItemCode)
        for r in conn.execute(
            "SELECT id, code FROM products WHERE code NOT LIKE 'WS-P-%'"
        ).fetchall():
            caches["prod"].setdefault(_norm(r["code"]), r["id"])
        for w in weights:
            slip_no = (w.get("slip_no") or "").strip()
            if not slip_no:
                stats["skipped_no_slip"] += 1
                continue
            if slip_no.upper() in existing:
                stats["skipped_existing"] += 1
                continue

            kind = _txn_kind(w.get("transaction_type"))
            party = parties.get(w.get("party_id")) or {}
            item = items.get(w.get("item_id")) or {}
            veh = vehicles.get(w.get("vehicle_id")) or {}

            vehicle_no = (veh.get("vehicle_no") or "").strip()
            driver = (w.get("driver_name") or veh.get("driver_name") or "").strip()
            vid = _ensure_vehicle(conn, vehicle_no, driver, uid)
            if vid:
                stats["vehicles_linked"] += 1

            cid, sid, party_type = _resolve_party(
                conn, party.get("name") or "", kind, caches, uid, stats
            )
            pid = _resolve_product(conn, item.get("name") or "", caches, uid, stats)

            status = _map_status(w.get("status"))
            first_w = float(w.get("first_weight") or 0)
            second_w = float(w.get("second_weight") or 0)
            gross = float(w.get("gross_weight") or 0)
            tare = float(w.get("tare_weight") or 0)
            net = float(w.get("net_weight") or 0)
            if status == "completed" and (not gross or not tare) and first_w and second_w:
                gross, tare = max(first_w, second_w), min(first_w, second_w)
                if not net:
                    net = round(gross - tare, 3)

            remarks_bits = []
            if w.get("department"):
                remarks_bits.append(f"Dept: {w['department']}")
            if w.get("transaction_type"):
                remarks_bits.append(f"Type: {w['transaction_type']}")
            if w.get("remarks"):
                remarks_bits.append(str(w["remarks"]))
            remarks_bits.append("Imported from modern_weight_scale")
            remarks = " | ".join(remarks_bits)[:500]

            slip_date = (w.get("entry_date") or "")[:10] or db._now()[:10]
            first_t = w.get("first_time")
            second_t = w.get("second_time")
            slip_time = str(first_t)[11:19] if first_t and len(str(first_t)) >= 19 else None

            conn.execute(
                """INSERT INTO weight_slips(
                     document_no, slip_date, slip_time, vehicle_id, vehicle_no, driver_name,
                     customer_id, supplier_id, product_id, party_type,
                     first_weight, second_weight, tare_weight, gross_weight, net_weight,
                     weight_difference, first_weight_time, second_weight_time,
                     print_time, save_time, remarks, status, created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    slip_no,
                    slip_date,
                    slip_time,
                    vid,
                    vehicle_no or None,
                    driver or None,
                    cid,
                    sid,
                    pid,
                    party_type,
                    first_w,
                    second_w,
                    tare,
                    gross,
                    net,
                    0,
                    first_t,
                    second_t,
                    second_t if status == "completed" else None,
                    w.get("updated_at") or w.get("created_at") or db._now(),
                    remarks,
                    status,
                    uid,
                    w.get("created_at") or db._now(),
                ),
            )
            existing.add(slip_no.upper())
            stats["slips_imported"] += 1
            stats[f"status_{status}"] += 1
            stats[f"kind_{kind}"] += 1

    print("\nImport complete:")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    with db.get_connection() as conn:
        print(f"  IFS weight_slips total: {conn.execute('SELECT COUNT(*) FROM weight_slips').fetchone()[0]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Import modern weight scale DB into IFS")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--replace", action="store_true", help="Delete existing IFS weight slips first")
    args = ap.parse_args()
    src = Path(args.src)
    print("=" * 60)
    print("Weighbridge import -> IFS weight_slips")
    print("=" * 60)
    preview(src)
    if args.apply:
        apply(src, _uid(), replace=args.replace)
    else:
        print("\nRun with --apply to import.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
