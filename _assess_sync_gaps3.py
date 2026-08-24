"""Finalize gaps: Sr/Pr, cash/bank books, weight tickets, payroll advances/payments."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))
from import_fmye_from_dat import FMYEExport, _d, _f  # noqa: E402
from import_fmye_from_dat import _import_party_vouchers, _resolve_party_for_voucher  # noqa: E402

EXP = FMYEExport(ROOT / "import" / "fmye" / "full")
IFS = sqlite3.connect(str(ROOT / "ifs_erp.db"))
IFS.row_factory = sqlite3.Row
WDB = sqlite3.connect(r"C:\modern_weight_scale_final\database\weight_scale.db")
WDB.row_factory = sqlite3.Row


def day_counts(rows, field):
    c = Counter()
    mx = None
    for r in rows:
        d = _d(r.get(field))
        if not d:
            continue
        c[d] += 1
        mx = d if mx is None or d > mx else mx
    return mx, c


def main():
    print("=== SrHeader / PrHeader ===")
    sr = EXP.rows("SrHeader")
    pr = EXP.rows("PrHeader")
    mx, c = day_counts(sr, "SrDate")
    print(f"SrHeader rows={len(sr)} max={mx}")
    print(" Jul+/Aug:", {d: c[d] for d in sorted(c) if d >= "2026-07-01"})
    mx, c = day_counts(pr, "PrDate")
    print(f"PrHeader rows={len(pr)} max={mx}")
    print(" Jul+/Aug:", {d: c[d] for d in sorted(c) if d >= "2026-07-01"})

    print("\nIFS sales_returns Jul+:", list(IFS.execute(
        "SELECT return_date, COUNT(*) FROM sales_returns WHERE return_date>='2026-07-01' GROUP BY 1 ORDER BY 1")))
    print("IFS purchase_returns Jul+:", list(IFS.execute(
        "SELECT return_date, COUNT(*) FROM purchase_returns WHERE return_date>='2026-07-01' GROUP BY 1 ORDER BY 1")))

    # Compare SR/PR docs
    ifs_sr = {r[0] for r in IFS.execute("SELECT document_no FROM sales_returns")}
    ifs_pr = {r[0] for r in IFS.execute("SELECT document_no FROM purchase_returns")}
    miss_sr = []
    for h in sr:
        d = _d(h.get("SrDate"))
        if d < "2026-01-01":
            continue
        doc = f"SR-{h.get('SrNo','').strip()}"
        if doc not in ifs_sr:
            miss_sr.append((d, doc))
    miss_pr = []
    for h in pr:
        d = _d(h.get("PrDate"))
        if d < "2026-01-01":
            continue
        doc = f"PR-{h.get('PrNo','').strip()}"
        if doc not in ifs_pr:
            miss_pr.append((d, doc))
    print(f"Missing SR 2026+: {len(miss_sr)}", Counter(d for d, _ in miss_sr))
    if miss_sr[-10:]:
        print("  sample last:", miss_sr[-10:])
    print(f"Missing PR 2026+: {len(miss_pr)}", Counter(d for d, _ in miss_pr))
    if miss_pr[-10:]:
        print("  sample last:", miss_pr[-10:])

    # Cash/bank books max dates
    print("\n=== IFS cash/bank/journal max ===")
    for t, dcol in [
        ("cash_receipts", "voucher_date"),
        ("cash_payments", "voucher_date"),
        ("bank_receipts", "voucher_date"),
        ("bank_payments", "voucher_date"),
        ("journal_vouchers", "voucher_date"),
    ]:
        cols = [x[1] for x in IFS.execute(f"PRAGMA table_info({t})")]
        dc = dcol if dcol in cols else next((c for c in cols if "date" in c.lower()), None)
        rows = list(IFS.execute(f"SELECT {dc} d, COUNT(*) c FROM {t} GROUP BY 1"))
        by = {str(r["d"])[:10]: r["c"] for r in rows if r["d"]}
        mx = max(by) if by else None
        aug = {d: by[d] for d in sorted(by) if d >= "2026-08-01"}
        print(f"  {t}: max={mx} Aug+={aug}")

    # How many party vouchers would import for Aug from FMYE (simulate skip existing)
    print("\n=== Simulate voucher import gap (party vouchers) ===")
    # Look at _import_party_vouchers logic - read source briefly via inspecting existing docs
    existing = set()
    for t in ("cash_receipts", "cash_payments", "bank_receipts", "bank_payments"):
        cols = [x[1] for x in IFS.execute(f"PRAGMA table_info({t})")]
        if "document_no" in cols:
            for r in IFS.execute(f"SELECT document_no FROM {t}"):
                existing.add((t, (r[0] or "").strip().upper()))
    print("existing cash/bank docs:", sum(1 for t,_ in existing), "by table", Counter(t for t,_ in existing))

    # Count distinct CRV/CPV/BRV/BPV voucher headers in Aug not in IFS
    # Document key pattern from import - inspect _import_party_vouchers
    vrows = EXP.rows("Voucher")
    # Group by TransactionNO + VoucherType + Date
    headers = {}
    for r in vrows:
        d = _d(r.get("VoucherDate"))
        if d < "2026-08-01":
            continue
        vt = (r.get("VoucherType") or "").strip().upper()
        if vt not in {"CRV", "CPV", "BRV", "BPV", "CR", "CP", "BR", "BP"}:
            continue
        tno = (r.get("TransactionNO") or "").strip()
        key = (vt, tno, d)
        headers.setdefault(key, 0)
        headers[key] += 1
    print("FMYE cash/bank voucher headers Aug+:", len(headers))
    by_day_vt = Counter()
    for (vt, tno, d), n in headers.items():
        by_day_vt[(d, vt)] += 1
    for k in sorted(by_day_vt):
        print(f"  {k[0]} {k[1]}: {by_day_vt[k]} headers")

    # Compare IFS document_nos that look like FMYE
    print("\nIFS cash_receipts Aug sample docs:")
    for r in IFS.execute(
        "SELECT document_no, voucher_date FROM cash_receipts WHERE voucher_date>='2026-08-01' ORDER BY voucher_date LIMIT 15"
    ):
        print(" ", dict(r))
    print("IFS cash_payments Aug sample:")
    for r in IFS.execute(
        "SELECT document_no, voucher_date FROM cash_payments WHERE voucher_date>='2026-08-01' ORDER BY voucher_date LIMIT 15"
    ):
        print(" ", dict(r))
    print("IFS bank Aug:")
    for t in ("bank_receipts", "bank_payments"):
        for r in IFS.execute(
            f"SELECT document_no, voucher_date FROM {t} WHERE voucher_date>='2026-08-01' ORDER BY voucher_date LIMIT 10"
        ):
            print(f"  {t}", dict(r))

    # Weight gap
    print("\n=== WEIGHT Aug 6 detail ===")
    wcols = [x[1] for x in WDB.execute("PRAGMA table_info(weights)")]
    print("cols", wcols)
    scale = list(WDB.execute("SELECT * FROM weights WHERE substr(entry_date,1,10)='2026-08-06' ORDER BY id"))
    ifs_slips = list(IFS.execute("SELECT * FROM weight_slips WHERE slip_date='2026-08-06' ORDER BY id"))
    print(f"scale={len(scale)} ifs={len(ifs_slips)}")
    ifs_docs = {(r["document_no"] or "").strip().upper() for r in ifs_slips}
    for r in scale:
        sn = (r["slip_no"] or "").strip().upper()
        st = r["status"]
        miss = sn not in ifs_docs
        print(f"  scale slip={sn} status={st} entry={r['entry_date']} net={r['net_weight']} missing_in_ifs={miss}")
    for r in ifs_slips:
        print(f"  ifs doc={r['document_no']} status={r['status']} net={r['net_weight']}")

    # All weight dates after Aug 6
    print("scale max entry_date:", WDB.execute("SELECT MAX(entry_date) FROM weights").fetchone()[0])
    print("scale counts Aug7/8:", list(WDB.execute(
        "SELECT substr(entry_date,1,10), COUNT(*) FROM weights WHERE substr(entry_date,1,10) IN ('2026-08-07','2026-08-08') GROUP BY 1")))
    print("ifs max slip_date:", IFS.execute("SELECT MAX(slip_date) FROM weight_slips").fetchone()[0])

    # Payroll advances Aug
    print("\n=== PAYROLL advances / payments Aug ===")
    print("employee_advances Aug+:", list(IFS.execute(
        "SELECT request_date, COUNT(*), SUM(amount) FROM employee_advances WHERE request_date>='2026-08-01' GROUP BY 1 ORDER BY 1")))
    print("payroll_lines paid status sample Jul:")
    cols = [x[1] for x in IFS.execute("PRAGMA table_info(payroll_lines)")]
    print(" payroll_lines cols:", cols)
    # Access Balance/Payments Aug vs advances
    try:
        import pyodbc
        cs = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb;"
        ac = pyodbc.connect(cs)
        cur = ac.cursor()
        print("Access Balance Aug+:")
        for r in cur.execute(
            """SELECT Format(Dated,'yyyy-mm-dd') d, COUNT(*) c, SUM(PaidAmt) paid, SUM(SalaryAmt) sal, SUM(Balance) bal
               FROM Balance WHERE Dated>=#2026-08-01# GROUP BY Format(Dated,'yyyy-mm-dd') ORDER BY 1"""
        ):
            print(" ", r)
        print("Access Payments Aug+:")
        for r in cur.execute(
            """SELECT Format(y.Dated,'yyyy-mm-dd') d, COUNT(*) c, SUM(p.PaidAmt) paid
               FROM Payments p INNER JOIN Pay y ON p.ID=y.ID
               WHERE y.Dated>=#2026-08-01# GROUP BY Format(y.Dated,'yyyy-mm-dd') ORDER BY 1"""
        ):
            print(" ", r)
        print("Access Salary Aug+:", list(cur.execute(
            "SELECT Format(Dated,'yyyy-mm-dd'), COUNT(*) FROM Salary WHERE Dated>=#2026-08-01# GROUP BY Format(Dated,'yyyy-mm-dd')")))
        ac.close()
    except Exception as e:
        print("access err", e)

    # Sales/purchases exact match check for Aug 6 docs
    print("\n=== Sales Aug6 docs export vs IFS ===")
    sales = [r for r in EXP.rows("SaleInvoiceHeader") if _d(r.get("InvoiceDate")) == "2026-08-06"]
    ifs_sales = {r[0] for r in IFS.execute("SELECT document_no FROM sales_invoices WHERE invoice_date='2026-08-06'")}
    for h in sales:
        doc = (h.get("DocumentNo") or "").strip()
        print(f"  export {doc} in_ifs={doc in ifs_sales} status={h.get('Status')}")
    print("ifs only:", ifs_sales - {(h.get('DocumentNo') or '').strip() for h in sales})

    # FMYE11 vs dat - recommend unload
    import datetime
    fmye_m = datetime.datetime.fromtimestamp(Path(r"C:\IFS\DataBase\FMYE11.db").stat().st_mtime)
    dat_m = datetime.datetime.fromtimestamp((ROOT / "import/fmye/full/715.dat").stat().st_mtime)
    print(f"\nFMYE11.db mtime={fmye_m} vs 715.dat mtime={dat_m} newer_db={fmye_m > dat_m} delta_hours={(fmye_m-dat_m).total_seconds()/3600:.1f}")

    # Check if ODBC can query live FMYE for max dates
    print("\n=== Try live FMYE11 max dates via ODBC ===")
    try:
        import pyodbc
        drivers = [d for d in pyodbc.drivers() if "Anywhere" in d or "Adaptive" in d]
        print("drivers:", drivers)
        opened = False
        for drv in drivers or ["SQL Anywhere 11"]:
            cs = f"Driver={{{drv}}};DBF=C:\\IFS\\DataBase\\FMYE11.db;UID=DBA;PWD=sql;"
            try:
                con = pyodbc.connect(cs, timeout=5)
                cur = con.cursor()
                print("OPENED", drv)
                for sql in [
                    "SELECT MAX(InvoiceDate) FROM SaleInvoiceHeader",
                    "SELECT MAX(PurchaseInvoiceDate) FROM PurchaseHeader",
                    "SELECT MAX(VoucherDate) FROM Voucher",
                    "SELECT MAX(SrDate) FROM SrHeader",
                    "SELECT MAX(PrDate) FROM PrHeader",
                    "SELECT COUNT(*) FROM SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-07'",
                    "SELECT COUNT(*) FROM SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-06'",
                    "SELECT InvoiceDate, COUNT(*) FROM SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-06' GROUP BY InvoiceDate",
                    "SELECT PurchaseInvoiceDate, COUNT(*) FROM PurchaseHeader WHERE PurchaseInvoiceDate >= '2026-08-05' GROUP BY PurchaseInvoiceDate",
                    "SELECT VoucherDate, COUNT(*) FROM Voucher WHERE VoucherDate >= '2026-08-06' GROUP BY VoucherDate",
                    "SELECT SrDate, COUNT(*) FROM SrHeader WHERE SrDate >= '2026-07-01' GROUP BY SrDate",
                    "SELECT PrDate, COUNT(*) FROM PrHeader WHERE PrDate >= '2026-07-01' GROUP BY PrDate",
                ]:
                    try:
                        rows = cur.execute(sql).fetchall()
                        print(f"  {sql} => {rows[:20]}")
                    except Exception as e:
                        print(f"  FAIL {sql}: {e}")
                con.close()
                opened = True
                break
            except Exception as e:
                print(f"  fail {drv}: {e}")
        if not opened:
            print("Could not open live FMYE11")
    except Exception as e:
        print("pyodbc issue", e)


if __name__ == "__main__":
    main()
