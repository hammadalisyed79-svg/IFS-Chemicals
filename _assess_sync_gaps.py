"""One-shot assessment: FMYE .dat vs ifs_erp.db vs weight/payroll sources through 2026-08-08."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))

from import_fmye_from_dat import FMYEExport, _d, _year  # noqa: E402

CUTOFF = date(2026, 8, 6)
TODAY_DATES = {"2026-08-07", "2026-08-08"}
TARGET_DATES = {d.isoformat() for d in (
    date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4),
    date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 7), date(2026, 8, 8),
)}

IFS_DB = ROOT / "ifs_erp.db"
FMYE11 = Path(r"C:\IFS\DataBase\FMYE11.db")
FMYE11_LOG = Path(r"C:\IFS\DataBase\FMYE11New.log")
WEIGHT_DB = Path(r"C:\modern_weight_scale_final\database\weight_scale.db")
PAYROLL = Path(r"C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb")
EXPORTS = {
    "full": ROOT / "import" / "fmye" / "full",
    "full_live": ROOT / "import" / "fmye" / "full_live",
    "full_old_20260806_1144": ROOT / "import" / "fmye" / "full_old_20260806_1144",
}

# FMYE table -> date field
FMYE_DOCS = [
    ("SaleInvoiceHeader", "InvoiceDate", "sales"),
    ("PurchaseHeader", "PurchaseInvoiceDate", "purchases"),
    ("SaleReturnHeader", "SaleReturnDate", "sales_returns"),
    ("PurchaseReturnHeader", "PurchaseReturnDate", "purchase_returns"),
    ("Voucher", "VoucherDate", "vouchers"),
]

# Try alternate return table names if needed
ALT_RETURN_TABLES = {
    "SaleReturnHeader": ["SaleReturn", "SalesReturnHeader", "SRHeader"],
    "PurchaseReturnHeader": ["PurchaseReturn", "PRHeader"],
}


def file_info(p: Path) -> str:
    if not p.exists():
        return f"MISSING: {p}"
    st = p.stat()
    return f"{p} size={st.st_size:,} mtime={date.fromtimestamp(st.st_mtime)} {__import__('datetime').datetime.fromtimestamp(st.st_mtime)}"


def max_and_counts(rows, date_field):
    by_day = Counter()
    mx = None
    for r in rows:
        d = _d(r.get(date_field))
        if not d or d.startswith("20") is False:
            continue
        by_day[d] += 1
        if mx is None or d > mx:
            mx = d
    return mx, by_day


def resolve_table(exp: FMYEExport, name: str) -> str | None:
    tm = exp.table_map()
    if name in tm:
        return name
    for alt in ALT_RETURN_TABLES.get(name, []):
        if alt in tm:
            return alt
    # fuzzy
    low = name.lower()
    for t in tm:
        if low in t.lower() or t.lower() in low:
            return t
    return None


def assess_export(label: str, path: Path):
    print(f"\n===== FMYE EXPORT: {label} ({path}) =====")
    if not path.exists():
        print("MISSING")
        return {}
    reload = path / "reload.sql"
    print(f"reload.sql: {file_info(reload)}")
    dats = list(path.glob("*.dat"))
    print(f"dat files: {len(dats)} total_bytes={sum(d.stat().st_size for d in dats):,}")
    exp = FMYEExport(path)
    tm = exp.table_map()
    print(f"tables mapped: {len(tm)}")
    interesting = [t for t in tm if any(x in t.lower() for x in ("sale", "purch", "voucher", "return", "cash", "bank"))]
    print("interesting tables:", ", ".join(sorted(interesting)[:40]))

    result = {}
    for table, dfield, key in FMYE_DOCS:
        real = resolve_table(exp, table)
        if not real:
            print(f"  {key}: table {table} NOT FOUND")
            result[key] = {"max": None, "by_day": Counter(), "table": None}
            continue
        info = tm[real]
        print(f"  loading {real} from {info['dat'].name} cols_has_{dfield}={dfield in info['columns']}")
        # find date col if alternate
        cols = info["columns"]
        df = dfield if dfield in cols else next((c for c in cols if "date" in c.lower()), None)
        rows = exp.rows(real)
        mx, by_day = max_and_counts(rows, df)
        aug = {d: by_day[d] for d in sorted(by_day) if d >= "2026-08-01"}
        result[key] = {"max": mx, "by_day": by_day, "table": real, "date_field": df, "rows": len(rows)}
        print(f"  {key}: table={real} date_field={df} rows={len(rows)} max={mx}")
        print(f"    Aug2026+ day counts: {aug}")
        for td in sorted(TODAY_DATES | {"2026-08-06"}):
            print(f"    {td}: {by_day.get(td, 0)}")
    return result


def assess_ifs():
    print(f"\n===== IFS ERP DB =====")
    print(file_info(IFS_DB))
    if not IFS_DB.exists():
        return {}
    con = sqlite3.connect(str(IFS_DB))
    con.row_factory = sqlite3.Row
    out = {}
    queries = [
        ("sales", "SELECT invoice_date d, COUNT(*) c FROM sales_invoices GROUP BY invoice_date"),
        ("purchases", "SELECT invoice_date d, COUNT(*) c FROM purchase_invoices GROUP BY invoice_date"),
        ("sales_returns", "SELECT return_date d, COUNT(*) c FROM sales_returns GROUP BY return_date"),
        ("purchase_returns", "SELECT return_date d, COUNT(*) c FROM purchase_returns GROUP BY return_date"),
        ("cash_book", "SELECT voucher_date d, COUNT(*) c FROM cash_book GROUP BY voucher_date"),
        ("bank_book", "SELECT voucher_date d, COUNT(*) c FROM bank_book GROUP BY voucher_date"),
        ("journal", "SELECT voucher_date d, COUNT(*) c FROM journal_vouchers GROUP BY voucher_date"),
        ("weight_slips", "SELECT slip_date d, COUNT(*) c FROM weight_slips GROUP BY slip_date"),
        ("payroll_runs", "SELECT period_end d, COUNT(*) c FROM payroll_runs GROUP BY period_end"),
    ]
    # discover actual date columns
    for name, sql in list(queries):
        try:
            rows = con.execute(sql).fetchall()
        except Exception as e:
            # try alternate column names
            print(f"  {name}: query failed ({e}); probing schema...")
            try:
                cols = [r[1] for r in con.execute(f"PRAGMA table_info({name if name != 'journal' else 'journal_vouchers'})")]
                print(f"    cols: {cols}")
            except Exception as e2:
                print(f"    no table: {e2}")
            out[name] = {"max": None, "by_day": Counter()}
            continue
        by_day = Counter({str(r["d"])[:10]: r["c"] for r in rows if r["d"]})
        mx = max(by_day) if by_day else None
        aug = {d: by_day[d] for d in sorted(by_day) if d >= "2026-08-01"}
        out[name] = {"max": mx, "by_day": by_day}
        print(f"  {name}: max={mx} Aug2026+={aug}")
        for td in sorted(TODAY_DATES | {"2026-08-06"}):
            print(f"    {td}: {by_day.get(td, 0)}")

    # also try salary-related HR tables
    for t in ("employees", "payroll_lines", "employee_advances", "salary_structures"):
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  table {t}: {n} rows")
        except Exception:
            pass
    # max payroll date variants
    for col in ("period_end", "period_start", "pay_date", "run_date"):
        try:
            mx = con.execute(f"SELECT MAX({col}) FROM payroll_runs").fetchone()[0]
            print(f"  payroll_runs.MAX({col})={mx}")
        except Exception:
            pass
    con.close()
    return out


def assess_weight():
    print(f"\n===== WEIGHT SCALE =====")
    print(file_info(WEIGHT_DB))
    if not WEIGHT_DB.exists():
        # search alternates
        for p in [
            Path(r"C:\modern_weight_scale_final\database\weight_scale.db"),
            Path(r"C:\WeightScale\database\weight_scale.db"),
            ROOT / "weight_scale.db",
        ]:
            print(file_info(p))
        return {}
    con = sqlite3.connect(str(WEIGHT_DB))
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("tables:", tables)
    by_day = Counter()
    mx = None
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        date_cols = [c for c in cols if "date" in c.lower() or c.lower() in ("created_at", "timestamp")]
        if not date_cols:
            continue
        dc = date_cols[0]
        try:
            rows = con.execute(f"SELECT substr({dc},1,10) d, COUNT(*) c FROM {t} GROUP BY 1").fetchall()
        except Exception as e:
            print(f"  {t}.{dc} fail: {e}")
            continue
        print(f"  {t} datecol={dc} days={len(rows)} max={max((r[0] for r in rows if r[0]), default=None)}")
        if t.lower() in ("transactions", "weighments", "slips", "weight_slips", "records") or "txn" in t.lower() or "slip" in t.lower() or "weigh" in t.lower():
            for d, c in rows:
                if d:
                    by_day[d] += c
                    if mx is None or d > mx:
                        mx = d
    # if still empty, use first table with dates
    if not by_day:
        for t in tables:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            for dc in cols:
                if "date" not in dc.lower():
                    continue
                rows = con.execute(f"SELECT substr({dc},1,10) d, COUNT(*) c FROM {t} GROUP BY 1").fetchall()
                for d, c in rows:
                    if d:
                        by_day[d] += c
                        if mx is None or d > mx:
                            mx = d
                print(f"  fallback {t}.{dc} max={mx}")
                break
            if by_day:
                break
    aug = {d: by_day[d] for d in sorted(by_day) if d >= "2026-08-01"}
    print(f"  combined max={mx} Aug2026+={aug}")
    con.close()
    return {"max": mx, "by_day": by_day}


def assess_payroll():
    print(f"\n===== PAYROLL ACCESS =====")
    print(file_info(PAYROLL))
    if not PAYROLL.exists():
        pay_dir = Path(r"C:\IFS\DataBase\PAYROLL")
        if pay_dir.exists():
            for p in pay_dir.iterdir():
                print(" ", file_info(p))
        return {}
    try:
        import pyodbc
    except ImportError:
        print("pyodbc missing")
        return {}
    cs = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(PAYROLL) + ";"
    try:
        con = pyodbc.connect(cs)
    except Exception as e:
        print(f"connect fail: {e}")
        return {}
    cur = con.cursor()
    out = {}
    for label, sql in [
        ("Salary", "SELECT Format(Dated,'yyyy-mm-dd') AS d, COUNT(*) AS c FROM Salary GROUP BY Format(Dated,'yyyy-mm-dd')"),
        ("Balance", "SELECT Format(Dated,'yyyy-mm-dd') AS d, COUNT(*) AS c FROM Balance GROUP BY Format(Dated,'yyyy-mm-dd')"),
        ("Payments", """SELECT Format(y.Dated,'yyyy-mm-dd') AS d, COUNT(*) AS c
                       FROM Payments p INNER JOIN Pay y ON p.ID=y.ID
                       GROUP BY Format(y.Dated,'yyyy-mm-dd')"""),
    ]:
        try:
            rows = cur.execute(sql).fetchall()
            by_day = Counter({str(r.d)[:10]: r.c for r in rows if r.d})
            mx = max(by_day) if by_day else None
            aug = {d: by_day[d] for d in sorted(by_day) if d >= "2026-07-01"}
            print(f"  {label}: max={mx} from Jul2026={aug}")
            out[label] = {"max": mx, "by_day": by_day}
        except Exception as e:
            print(f"  {label} fail: {e}")
            # simpler
            try:
                mx = cur.execute(f"SELECT MAX(Dated) FROM {label if label != 'Payments' else 'Pay'}").fetchone()[0]
                print(f"  {label} MAX(Dated)={mx}")
                out[label] = {"max": str(mx)[:10] if mx else None, "by_day": Counter()}
            except Exception as e2:
                print(f"  {label} MAX fail: {e2}")
    con.close()
    return out


def gap_report(src, ifs, src_key, ifs_key, label):
    s = src.get(src_key, {})
    i = ifs.get(ifs_key, {})
    sb, ib = s.get("by_day", Counter()), i.get("by_day", Counter())
    print(f"\n--- GAP {label} (export max={s.get('max')} vs ifs max={i.get('max')}) ---")
    all_days = sorted(set(list(sb) + list(ib)))
    focus = [d for d in all_days if d >= "2026-08-01"]
    missing_total = 0
    for d in focus:
        sc, ic = sb.get(d, 0), ib.get(d, 0)
        gap = sc - ic
        if gap != 0 or d in TODAY_DATES or d >= "2026-08-06":
            flag = " MISSING" if gap > 0 else (" EXTRA_IN_IFS" if gap < 0 else " OK")
            print(f"  {d}: export={sc} ifs={ic} gap={gap}{flag}")
            if gap > 0:
                missing_total += gap
    print(f"  total missing docs (export-ifs, Aug1+ where export>ifs): {missing_total}")


def main():
    print("ASSESS SYNC GAPS —", date.today().isoformat())
    print(file_info(FMYE11))
    print(file_info(FMYE11_LOG))

    exports = {}
    for label, path in EXPORTS.items():
        exports[label] = assess_export(label, path)

    # compare full vs full_live freshness
    print("\n===== full vs full_live freshness =====")
    for key in ("sales", "purchases", "vouchers", "sales_returns", "purchase_returns"):
        a = exports.get("full", {}).get(key, {}).get("max")
        b = exports.get("full_live", {}).get(key, {}).get("max")
        print(f"  {key}: full={a} full_live={b}")

    ifs = assess_ifs()
    # Prefer newest export for gap (full_live if newer)
    best_label = "full_live"
    best = exports.get("full_live") or {}
    if not best or not any(v.get("max") for v in best.values()):
        best_label = "full"
        best = exports.get("full") or {}
    # pick export with latest sales max
    for label, data in exports.items():
        sm = (data.get("sales") or {}).get("max") or ""
        bm = (best.get("sales") or {}).get("max") or ""
        if sm > bm:
            best, best_label = data, label
    print(f"\n===== USING EXPORT FOR GAPS: {best_label} =====")
    gap_report(best, ifs, "sales", "sales", "sales_invoices")
    gap_report(best, ifs, "purchases", "purchases", "purchase_invoices")
    gap_report(best, ifs, "sales_returns", "sales_returns", "sales_returns")
    gap_report(best, ifs, "purchase_returns", "purchase_returns", "purchase_returns")

    # vouchers vs cash+bank+journal combined roughly by day
    print("\n--- GAP vouchers (FMYE Voucher rows vs cash+bank+journal IFS counts) ---")
    vb = (best.get("vouchers") or {}).get("by_day", Counter())
    ib = Counter()
    for k in ("cash_book", "bank_book", "journal"):
        for d, c in (ifs.get(k) or {}).get("by_day", {}).items():
            ib[d] += c
    for d in sorted(set(list(vb) + list(ib))):
        if d < "2026-08-01":
            continue
        print(f"  {d}: fmye_voucher_lines/rows={vb.get(d,0)} ifs_cash+bank+jv={ib.get(d,0)}")

    w = assess_weight()
    if w and ifs.get("weight_slips"):
        print("\n--- GAP weight_slips ---")
        sb, ib2 = w.get("by_day", Counter()), ifs["weight_slips"].get("by_day", Counter())
        for d in sorted(set(list(sb) + list(ib2))):
            if d < "2026-08-01":
                continue
            gap = sb.get(d, 0) - ib2.get(d, 0)
            print(f"  {d}: scale={sb.get(d,0)} ifs={ib2.get(d,0)} gap={gap}")

    pay = assess_payroll()
    if pay and ifs.get("payroll_runs"):
        print("\n--- GAP payroll (Salary dated vs payroll_runs) ---")
        sb = (pay.get("Salary") or {}).get("by_day", Counter())
        ib2 = ifs["payroll_runs"].get("by_day", Counter())
        for d in sorted(set(list(sb) + list(ib2))):
            if d < "2026-07-01":
                continue
            print(f"  {d}: access_salary={sb.get(d,0)} ifs_runs={ib2.get(d,0)}")

    print("\n===== DONE =====")


if __name__ == "__main__":
    main()
