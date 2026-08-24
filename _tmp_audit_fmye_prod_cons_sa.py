"""Audit FMYE 2026 Daily Production (DPR), Consumption, Stock Adjustment vs ERP."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _d, _f

ROOT = Path(r"c:\MY ERPS")
LIVE = ROOT / "ifs_erp.db"
OUT = ROOT / "reports"
YEAR = "2026"


def year_of(val) -> str:
    s = (_d(val) or "")[:10]
    return s[:4] if len(s) >= 4 else ""


def main():
    OUT.mkdir(exist_ok=True)
    exp = FMYEExport(EXPORT_DIR)
    lines = []
    lines.append(f"FMYE export: {EXPORT_DIR}")
    lines.append(f"Tables available: {len(exp.table_map())}")

    # --- FMYE schemas ---
    for t in [
        "DPRHeader", "DPRDetail", "ConsumptionNoteHeader", "ConsumptionNoteDetail",
        "SAHeader", "SADetail", "MaterialIssueNoteHeader", "MaterIssueNoteDetail",
    ]:
        rows = exp.rows(t)
        cols = list(rows[0].keys()) if rows else []
        lines.append(f"FMYE {t}: n={len(rows)} cols={cols}")

    # --- FMYE 2026 headers ---
    dpr_h = [r for r in exp.rows("DPRHeader") if year_of(r.get("DPRDate") or r.get("Date")) == YEAR]
    # discover date col
    if not dpr_h and exp.rows("DPRHeader"):
        sample = exp.rows("DPRHeader")[0]
        date_cols = [k for k in sample if "date" in k.lower() or k.lower().endswith("dt")]
        lines.append(f"DPRHeader sample keys/date candidates: {date_cols} sample={dict(list(sample.items())[:8])}")
        # try all date-like
        for dc in date_cols or list(sample.keys()):
            cand = [r for r in exp.rows("DPRHeader") if year_of(r.get(dc)) == YEAR]
            if cand:
                dpr_h = cand
                lines.append(f"DPR date col used: {dc} count={len(cand)}")
                break

    cons_h = [r for r in exp.rows("ConsumptionNoteHeader") if year_of(r.get("ConsNoteDate")) == YEAR]
    sa_h = [r for r in exp.rows("SAHeader") if year_of(r.get("SaDate")) == YEAR]
    mir_h = [r for r in exp.rows("MaterialIssueNoteHeader") if year_of(r.get("MINDate")) == YEAR]

    # Status / approval breakdown
    def status_counts(rows, *keys):
        c = Counter()
        for r in rows:
            st = None
            for k in keys:
                if k in r and str(r.get(k) or "").strip() != "":
                    st = str(r.get(k)).strip()
                    break
            c[st if st is not None else "(blank)"] += 1
        return dict(c)

    lines.append("")
    lines.append("=== FMYE 2026 document counts ===")
    lines.append(f"DPR headers 2026: {len(dpr_h)} status={status_counts(dpr_h, 'Status', 'Approved', 'Approve')}")
    lines.append(f"Consumption headers 2026: {len(cons_h)} status={status_counts(cons_h, 'Status', 'Approved')}")
    lines.append(f"Stock Adj headers 2026: {len(sa_h)} status={status_counts(sa_h, 'Status', 'Approved')}")
    lines.append(f"Material Issue headers 2026: {len(mir_h)} status={status_counts(mir_h, 'Status', 'Approved')}")

    # Pending = Status not '1' (FMYE approved flag)
    def pending(rows, status_key="Status"):
        out = []
        for r in rows:
            st = str(r.get(status_key) or "").strip()
            if st != "1":
                out.append(r)
        return out

    dpr_pending = pending(dpr_h)
    cons_pending = pending(cons_h)
    sa_pending = pending(sa_h)
    mir_pending = pending(mir_h)
    lines.append("")
    lines.append("=== FMYE 2026 pending / not Status=1 ===")
    lines.append(f"DPR pending: {len(dpr_pending)}")
    lines.append(f"Consumption pending: {len(cons_pending)}")
    lines.append(f"Stock Adj pending: {len(sa_pending)}")
    lines.append(f"MIR pending: {len(mir_pending)}")

    # Detail line counts 2026
    def detail_for(header_rows, detail_table, h_key, d_key, date_key_on_header):
        hdrs = {(r.get(h_key) or "").strip(): r for r in header_rows}
        # also index all headers for year filter via detail join
        all_h = {(r.get(h_key) or "").strip(): r for r in exp.rows(detail_table.replace("Detail", "Header") if False else [])}
        n_lines = 0
        qty = 0.0
        items = set()
        # use provided header_rows already filtered
        keys = set(hdrs)
        for r in exp.rows(detail_table):
            k = (r.get(d_key) or "").strip()
            if k not in keys:
                continue
            n_lines += 1
            qty += abs(_f(r.get("Quantity")))
            code = (r.get("ItemCode") or "").strip().upper()
            if code:
                items.add(code)
        return n_lines, qty, len(items)

    # Discover DPR keys
    if exp.rows("DPRHeader"):
        dh = exp.rows("DPRHeader")[0]
        dd = exp.rows("DPRDetail")[0] if exp.rows("DPRDetail") else {}
        lines.append(f"DPRHeader cols: {list(dh.keys())}")
        lines.append(f"DPRDetail cols: {list(dd.keys()) if dd else None}")

    conn = sqlite3.connect(str(LIVE))
    conn.row_factory = sqlite3.Row
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    lines.append("")
    lines.append("=== ERP tables present ===")
    for t in sorted(tables):
        if any(x in t.lower() for x in (
            "prod", "consum", "adjust", "batch", "formula", "job", "inventory_mov"
        )):
            n = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            lines.append(f"  {t}: {n}")

    # ERP stock adjustments 2026
    lines.append("")
    lines.append("=== ERP 2026 stock / production / movements ===")
    if "stock_adjustments" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stock_adjustments)")]
        lines.append(f"stock_adjustments cols: {cols}")
        date_col = "adjustment_date" if "adjustment_date" in cols else (
            "document_date" if "document_date" in cols else None
        )
        if date_col:
            rows = conn.execute(
                f"SELECT * FROM stock_adjustments WHERE substr({date_col},1,4)=?", (YEAR,)
            ).fetchall()
            lines.append(f"ERP stock_adjustments 2026: {len(rows)}")
            if "status" in cols:
                lines.append(f"  by status: {dict(Counter(r['status'] for r in rows))}")
            # sample doc nos
            doc_col = next((c for c in ("document_no", "adjustment_no", "doc_no") if c in cols), None)
            if doc_col and rows:
                lines.append(f"  sample: {[r[doc_col] for r in rows[:10]]}")
        else:
            lines.append(f"ERP stock_adjustments total: {conn.execute('SELECT COUNT(*) FROM stock_adjustments').fetchone()[0]}")

    for t in ("production_orders", "production_batches", "job_cards", "daily_production"):
        if t in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            date_col = next((c for c in cols if "date" in c.lower()), None)
            if date_col:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {t} WHERE substr({date_col},1,4)=?", (YEAR,)
                ).fetchone()[0]
                lines.append(f"ERP {t} 2026 ({date_col}): {n}")
            else:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                lines.append(f"ERP {t} total: {n} cols={cols}")

    if "inventory_movements" in tables:
        mov = conn.execute(
            """SELECT reference_type, COUNT(*) n, COALESCE(SUM(quantity),0) qty
               FROM inventory_movements
               WHERE substr(movement_date,1,4)=?
               GROUP BY reference_type ORDER BY n DESC""",
            (YEAR,),
        ).fetchall()
        lines.append("ERP inventory_movements 2026 by reference_type:")
        for r in mov:
            lines.append(f"  {r['reference_type']}: n={r['n']} qty={r['qty']}")

    # Compare SA doc numbers FMYE vs ERP
    fmye_sa_codes = sorted({(r.get("SaCode") or "").strip() for r in sa_h if (r.get("SaCode") or "").strip()})
    erp_sa_docs = set()
    if "stock_adjustments" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stock_adjustments)")]
        doc_col = next((c for c in ("document_no", "adjustment_no", "doc_no") if c in cols), None)
        date_col = next((c for c in ("adjustment_date", "document_date", "entry_date") if c in cols), None)
        if doc_col and date_col:
            erp_sa_docs = {
                (r[0] or "").strip()
                for r in conn.execute(
                    f"SELECT {doc_col} FROM stock_adjustments WHERE substr({date_col},1,4)=?",
                    (YEAR,),
                )
            }
    missing_sa = [c for c in fmye_sa_codes if c not in erp_sa_docs and f"SA-{c}" not in erp_sa_docs and f"ADJ-{c}" not in erp_sa_docs]
    # also check remarks/reason containing SaCode
    lines.append("")
    lines.append(f"FMYE SA 2026 docs: {len(fmye_sa_codes)}")
    lines.append(f"ERP SA 2026 docs: {len(erp_sa_docs)}")
    lines.append(f"FMYE SA missing in ERP (by code): {len(missing_sa)}")

    # DPR codes
    dpr_key = None
    if exp.rows("DPRHeader"):
        sample = exp.rows("DPRHeader")[0]
        dpr_key = next((k for k in ("DPRCode", "DprCode", "DocumentNo", "DPRNo") if k in sample), None)
        date_key = next((k for k in ("DPRDate", "DprDate", "Date", "DocumentDate") if k in sample), None)
        if dpr_key and date_key and not dpr_h:
            dpr_h = [r for r in exp.rows("DPRHeader") if year_of(r.get(date_key)) == YEAR]
            lines.append(f"DPR recount with {date_key}: {len(dpr_h)}")
        fmye_dpr = sorted({(r.get(dpr_key) or "").strip() for r in dpr_h if dpr_key})
        lines.append(f"FMYE DPR 2026 docs: {len(fmye_dpr)} key={dpr_key}")
        # pending list sample
        if dpr_pending and dpr_key:
            lines.append("DPR pending sample:")
            for r in dpr_pending[:15]:
                lines.append(
                    f"  {r.get(dpr_key)} date={r.get(date_key)} status={r.get('Status')} "
                    f"other={ {k:r.get(k) for k in r if k in ('Approved','UserCode','CompCode','DEPTID')} }"
                )

    # Consumption
    fmye_cons = sorted({(r.get("ConsNoteCode") or "").strip() for r in cons_h})
    lines.append(f"FMYE Consumption 2026 docs: {len(fmye_cons)}")
    if cons_pending:
        lines.append("Consumption pending sample:")
        for r in cons_pending[:15]:
            lines.append(
                f"  {r.get('ConsNoteCode')} date={r.get('ConsNoteDate')} status={r.get('Status')} "
                f"DPR={r.get('DPRCode')} dept={r.get('DEPTID')}"
            )

    if sa_pending:
        lines.append("Stock Adj pending sample:")
        for r in sa_pending[:15]:
            lines.append(
                f"  {r.get('SaCode')} date={r.get('SaDate')} status={r.get('Status')} "
                f"remarks={r.get('Remarks')}"
            )

    # Write CSVs
    def write_csv(name, rows, fields):
        path = OUT / name
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fields})
        return path

    if dpr_h and dpr_key:
        date_key = next(
            (k for k in ("DPRDate", "DprDate", "Date", "DocumentDate") if k in dpr_h[0]),
            None,
        )
        fields = [dpr_key, date_key, "Status", "UserCode", "CompCode", "DEPTID"]
        fields = [f for f in fields if f]
        write_csv("fmye_dpr_2026.csv", dpr_h, fields)
        write_csv("fmye_dpr_2026_pending.csv", dpr_pending, fields)

    write_csv(
        "fmye_consumption_2026.csv",
        cons_h,
        ["ConsNoteCode", "ConsNoteDate", "Status", "DPRCode", "CompCode", "DEPTID", "UserCode"],
    )
    write_csv(
        "fmye_consumption_2026_pending.csv",
        cons_pending,
        ["ConsNoteCode", "ConsNoteDate", "Status", "DPRCode", "CompCode", "DEPTID", "UserCode"],
    )
    write_csv(
        "fmye_stock_adj_2026.csv",
        sa_h,
        ["SaCode", "SaDate", "Status", "Remarks", "Usercode", "DEPTID"],
    )
    write_csv(
        "fmye_stock_adj_2026_pending.csv",
        sa_pending,
        ["SaCode", "SaDate", "Status", "Remarks", "Usercode", "DEPTID"],
    )
    write_csv(
        "fmye_stock_adj_2026_missing_in_erp.csv",
        [{"SaCode": c} for c in missing_sa],
        ["SaCode"],
    )

    # Check if import module ever mentions these
    lines.append("")
    lines.append("=== Import coverage ===")
    lines.append(
        "import_fmye_from_dat.py imports: Chart/Items/Sales/Purchases/Vouchers only — "
        "NO DPR, Consumption, or Stock Adjustment import path found."
    )

    summary_path = OUT / "fmye_prod_cons_sa_2026_audit.txt"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(summary_path)
    print("\n".join(lines))
    conn.close()


if __name__ == "__main__":
    main()
