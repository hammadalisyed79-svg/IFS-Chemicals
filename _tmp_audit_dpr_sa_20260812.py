"""Audit FMYE DPR/SA from 2026-01-01 to today vs ERP import coverage."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from import_fmye_from_dat import FMYEExport, _d, _f

ROOT = Path(r"c:\MY ERPS")
OUT = ROOT / "reports"
OUT.mkdir(exist_ok=True)
TODAY = date(2026, 8, 12)
FROM_D = date(2026, 1, 1)


def parse_d(val):
    s = (_d(val) or "")[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def in_range(d):
    return d is not None and FROM_D <= d <= TODAY


def status_bucket(st):
    s = str(st or "").strip()
    if s == "1":
        return "posted/approved (1)"
    if s == "0":
        return "pending (0)"
    if s == "":
        return "pending (blank)"
    return f"other ({s})"


def write_csv(path, rows, cols):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})


def main():
    candidates = []
    for name in ["full", "full_live", "full_old_20260808_094509", "_live_delta"]:
        p = ROOT / "import" / "fmye" / name
        if not (p / "reload.sql").exists():
            continue
        e = FMYEExport(p)
        dates = []
        for r in e.rows("DPRHeader"):
            d = _d(r.get("DPRDate"))
            if d:
                dates.append(d[:10])
        mx = max(dates) if dates else ""
        n2026 = sum(1 for x in dates if x >= "2026-01-01")
        candidates.append((mx, n2026, name, p, len(dates)))
    candidates.sort(reverse=True)
    print("Export candidates:")
    for c in candidates:
        print(f"  max={c[0]} n2026={c[1]} name={c[2]} total={c[4]}")

    best = candidates[0]
    export = best[3]
    print("USING", export)
    e = FMYEExport(export)

    dpr_all = e.rows("DPRHeader")
    dpr_det = e.rows("DPRDetail")
    sa_all = e.rows("SAHeader")
    sa_det = e.rows("SADetail")

    dpr_h = []
    for r in dpr_all:
        d = parse_d(r.get("DPRDate"))
        if in_range(d):
            rr = dict(r)
            rr["_date"] = d.isoformat()
            dpr_h.append(rr)

    sa_h = []
    for r in sa_all:
        d = parse_d(r.get("SaDate"))
        if in_range(d):
            rr = dict(r)
            rr["_date"] = d.isoformat()
            sa_h.append(rr)

    dpr_keys = {(r.get("DPRCode") or "").strip() for r in dpr_h}
    sa_keys = {(r.get("SaCode") or "").strip() for r in sa_h}
    dpr_lines = [r for r in dpr_det if (r.get("DPRCode") or "").strip() in dpr_keys]
    sa_lines = [r for r in sa_det if (r.get("SaCode") or "").strip() in sa_keys]

    dpr_status = Counter(status_bucket(r.get("Status")) for r in dpr_h)
    sa_status = Counter(status_bucket(r.get("Status")) for r in sa_h)
    dpr_pending = [r for r in dpr_h if str(r.get("Status") or "").strip() != "1"]
    sa_pending = [r for r in sa_h if str(r.get("Status") or "").strip() != "1"]

    dpr_pending_all = []
    for r in dpr_all:
        if str(r.get("Status") or "").strip() != "1":
            d = parse_d(r.get("DPRDate"))
            rr = dict(r)
            rr["_date"] = d.isoformat() if d else ""
            dpr_pending_all.append(rr)

    sa_pending_all = []
    for r in sa_all:
        if str(r.get("Status") or "").strip() != "1":
            d = parse_d(r.get("SaDate"))
            rr = dict(r)
            rr["_date"] = d.isoformat() if d else ""
            sa_pending_all.append(rr)

    dpr_month = Counter(r["_date"][:7] for r in dpr_h)
    sa_month = Counter(r["_date"][:7] for r in sa_h)
    dpr_qty = sum(_f(r.get("Quantity")) for r in dpr_lines)
    sa_qty = sum(_f(r.get("Quantity")) for r in sa_lines)
    dpr_items = {
        (r.get("ItemCode") or "").strip().upper()
        for r in dpr_lines
        if (r.get("ItemCode") or "").strip()
    }
    sa_items = {
        (r.get("ItemCode") or "").strip().upper()
        for r in sa_lines
        if (r.get("ItemCode") or "").strip()
    }

    hit_12018 = [dict(r) for r in dpr_all if str(r.get("DPRCode") or "").strip() == "12018"]
    det_12018 = [r for r in dpr_det if str(r.get("DPRCode") or "").strip() == "12018"]

    dpr_dates = sorted(r["_date"] for r in dpr_h)
    sa_dates = sorted(r["_date"] for r in sa_h)

    conn = sqlite3.connect(str(ROOT / "ifs_erp.db"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    po_n = None
    if "production_orders" in tables:
        po_n = conn.execute(
            "SELECT COUNT(*) FROM production_orders WHERE order_date>='2026-01-01'"
        ).fetchone()[0]
    mov_n, mov_qty = None, None
    if "inventory_movements" in tables:
        mov_n, mov_qty = conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(quantity),0)
               FROM inventory_movements
               WHERE reference_type='production' AND movement_date>='2026-01-01'"""
        ).fetchone()

    dpr_hits = 0
    for code in list(dpr_keys)[:100]:
        c = conn.execute(
            """SELECT COUNT(*) FROM inventory_movements
               WHERE reference_no LIKE ? OR IFNULL(reason,'') LIKE ?""",
            (f"%{code}%", f"%{code}%"),
        ).fetchone()[0]
        dpr_hits += 1 if c else 0

    sa_hits = 0
    for code in sa_keys:
        c = conn.execute(
            """SELECT COUNT(*) FROM inventory_movements
               WHERE reference_no LIKE ? OR IFNULL(reason,'') LIKE ?""",
            (f"%{code}%", f"%{code}%"),
        ).fetchone()[0]
        sa_hits += 1 if c else 0

    adj_n = 0
    if "inventory_movements" in tables:
        adj_n = conn.execute(
            """SELECT COUNT(*) FROM inventory_movements
               WHERE movement_date>='2026-01-01'
                 AND (lower(COALESCE(reference_type,'')) LIKE '%adjust%'
                      OR lower(COALESCE(reason,'')) LIKE '%stock adj%'
                      OR lower(COALESCE(reference_no,'')) LIKE 'sa%')"""
        ).fetchone()[0]
    conn.close()

    dpr_cols = [
        "DPRCode", "DPRDate", "Status", "UserCode", "ShiftCode",
        "DEPTID", "AccountCode", "AccountName", "Doc",
    ]
    sa_cols = ["SaCode", "SaDate", "Status", "Remarks", "Usercode", "DEPTID", "Doc"]
    write_csv(OUT / "fmye_dpr_2026_range.csv", dpr_h, dpr_cols)
    write_csv(OUT / "fmye_sa_2026_range.csv", sa_h, sa_cols)
    write_csv(OUT / "fmye_dpr_pending_auth.csv", dpr_pending_all, dpr_cols)
    write_csv(OUT / "fmye_sa_pending_auth.csv", sa_pending_all, sa_cols)

    months = sorted(set(dpr_month) | set(sa_month))
    monthly = [
        {"month": m, "dpr_docs": dpr_month.get(m, 0), "sa_docs": sa_month.get(m, 0)}
        for m in months
    ]

    summary = {
        "source": str(export),
        "source_note": (
            "Live path C:\\IFS\\DataBase\\FMYE11 is NOT present on this PC. "
            "Audited latest dbunload export originally from that database."
        ),
        "live_db_missing": True,
        "local_FMYE11_db": str(ROOT / "import" / "fmye" / "FMYE11.db"),
        "local_FMYE11_db_dated": "2026-06-01 (stale vs screenshot Jul/Aug 2026)",
        "range": f"{FROM_D.isoformat()} to {TODAY.isoformat()}",
        "export_max_dpr_date": best[0],
        "table_totals_all_years": {
            "DPRHeader": len(dpr_all),
            "DPRDetail": len(dpr_det),
            "SAHeader": len(sa_all),
            "SADetail": len(sa_det),
        },
        "dpr_headers_in_range": len(dpr_h),
        "dpr_detail_lines": len(dpr_lines),
        "dpr_qty_sum": round(dpr_qty, 3),
        "dpr_distinct_items": len(dpr_items),
        "dpr_status": dict(dpr_status),
        "dpr_pending_in_range": len(dpr_pending),
        "dpr_pending_all_years": len(dpr_pending_all),
        "dpr_date_min": dpr_dates[0] if dpr_dates else None,
        "dpr_date_max": dpr_dates[-1] if dpr_dates else None,
        "sa_headers_in_range": len(sa_h),
        "sa_detail_lines": len(sa_lines),
        "sa_qty_sum": round(sa_qty, 3),
        "sa_distinct_items": len(sa_items),
        "sa_status": dict(sa_status),
        "sa_pending_in_range": len(sa_pending),
        "sa_pending_all_years": len(sa_pending_all),
        "sa_date_min": sa_dates[0] if sa_dates else None,
        "sa_date_max": sa_dates[-1] if sa_dates else None,
        "dpr_12018_header": hit_12018,
        "dpr_12018_detail_lines": len(det_12018),
        "erp_production_orders_2026": po_n,
        "erp_production_movements_2026": {"n": mov_n, "qty": mov_qty},
        "erp_dpr_code_hits_of_100_sample": dpr_hits,
        "erp_sa_code_hits": sa_hits,
        "erp_adjustment_like_movements_2026": adj_n,
        "erp_imported_dpr_sa": False,
        "monthly": monthly,
        "dpr_pending_sample": [
            {
                "DPRCode": r.get("DPRCode"),
                "DPRDate": (_d(r.get("DPRDate")) or "")[:10],
                "Status": r.get("Status"),
                "UserCode": r.get("UserCode"),
            }
            for r in sorted(dpr_pending_all, key=lambda x: x.get("_date") or "", reverse=True)[:25]
        ],
        "sa_pending_sample": [
            {
                "SaCode": r.get("SaCode"),
                "SaDate": (_d(r.get("SaDate")) or "")[:10],
                "Status": r.get("Status"),
                "Remarks": (r.get("Remarks") or "")[:80],
            }
            for r in sorted(sa_pending_all, key=lambda x: x.get("_date") or "", reverse=True)[:25]
        ],
        "dpr_latest_15": [
            {
                "DPRCode": r.get("DPRCode"),
                "DPRDate": r["_date"],
                "Status": r.get("Status"),
                "AccountName": r.get("AccountName"),
            }
            for r in sorted(dpr_h, key=lambda x: x["_date"], reverse=True)[:15]
        ],
        "sa_all_in_range": [
            {
                "SaCode": r.get("SaCode"),
                "SaDate": r["_date"],
                "Status": r.get("Status"),
                "Remarks": (r.get("Remarks") or "")[:80],
            }
            for r in sorted(sa_h, key=lambda x: x["_date"])
        ],
    }
    out_json = OUT / "fmye_dpr_sa_audit_20260812.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print("Wrote", out_json)


if __name__ == "__main__":
    main()
