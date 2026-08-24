"""Live FMYE11 dates + weight missing slips + cash/bank column names + payroll advances."""
from __future__ import annotations

import datetime
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))
from import_fmye_from_dat import FMYEExport, _d  # noqa: E402

IFS = sqlite3.connect(str(ROOT / "ifs_erp.db"))
IFS.row_factory = sqlite3.Row
WDB = sqlite3.connect(r"C:\modern_weight_scale_final\database\weight_scale.db")
WDB.row_factory = sqlite3.Row
EXP = FMYEExport(ROOT / "import" / "fmye" / "full")


def main():
    for t in ("cash_receipts", "cash_payments", "bank_receipts", "bank_payments", "journal_vouchers"):
        cols = [x[1] for x in IFS.execute(f"PRAGMA table_info({t})")]
        print(t, cols)

    print("\n=== Weight missing on 2026-08-06 ===")
    ifs_docs = {(r[0] or "").strip().upper() for r in IFS.execute(
        "SELECT document_no FROM weight_slips WHERE slip_date='2026-08-06'")}
    miss = []
    for r in WDB.execute("SELECT * FROM weights WHERE substr(entry_date,1,10)='2026-08-06' ORDER BY id"):
        sn = (r["slip_no"] or "").strip().upper()
        flag = sn not in ifs_docs
        print(f"  slip={sn} status={r['status']} net={r['net_weight']} first={r['first_weight']} second={r['second_weight']} missing={flag}")
        if flag:
            miss.append(sn)
    print("MISSING SLIPS:", miss)
    print("scale Aug7/8:", list(WDB.execute(
        "SELECT substr(entry_date,1,10), status, COUNT(*) FROM weights WHERE entry_date>='2026-08-07' GROUP BY 1,2")))
    print("all scale by day >=08-01:", list(WDB.execute(
        "SELECT substr(entry_date,1,10), COUNT(*) FROM weights WHERE entry_date>='2026-08-01' GROUP BY 1 ORDER BY 1")))

    # Journal: compare JVR distinct TransactionNO
    print("\n=== JVR headers export vs journal_vouchers ===")
    j_docs = {(r[0] or "").strip().upper() for r in IFS.execute("SELECT document_no FROM journal_vouchers")}
    jvr_headers = {}
    for r in EXP.rows("Voucher"):
        if (r.get("VoucherType") or "").strip().upper() != "JVR":
            continue
        d = _d(r.get("VoucherDate"))
        if d < "2026-08-01":
            continue
        tno = (r.get("TransactionNO") or "").strip()
        jvr_headers[(tno, d)] = jvr_headers.get((tno, d), 0) + 1
    print(f"FMYE JVR distinct (TransactionNO,date) Aug+: {len(jvr_headers)}")
    # guess doc pattern
    sample_ifs = list(IFS.execute(
        "SELECT document_no, voucher_date FROM journal_vouchers WHERE voucher_date>='2026-08-01' ORDER BY voucher_date LIMIT 20"))
    print("IFS JV sample:", [dict(r) for r in sample_ifs])
    # count ifs JV by day
    print("IFS JV by day:", list(IFS.execute(
        "SELECT voucher_date, COUNT(*) FROM journal_vouchers WHERE voucher_date>='2026-08-01' GROUP BY 1 ORDER BY 1")))
    print("FMYE JVR headers by day:", Counter(d for _, d in jvr_headers))

    # How many JVR headers missing? try common doc patterns
    patterns_tried = []
    for (tno, d), n in list(jvr_headers.items())[:5]:
        patterns_tried.append((tno, d, f"JV-{tno}", f"JVR-{tno}", tno, f"JV-{tno}-{d}"))
    print("pattern probe:", patterns_tried)
    missing_by_day = Counter()
    for tno, d in jvr_headers:
        cands = {f"JV-{tno}".upper(), f"JVR-{tno}".upper(), tno.upper(), f"JV{tno}".upper()}
        if not (cands & j_docs):
            # also check contains
            hit = any(tno.upper() in doc for doc in j_docs if doc)
            if not hit:
                missing_by_day[d] += 1
    print("Approx missing JVR headers (no doc containing TransactionNO):", dict(missing_by_day))

    # Live FMYE
    print("\n=== LIVE FMYE11 ===")
    import pyodbc
    print("drivers:", pyodbc.drivers())
    for drv in [d for d in pyodbc.drivers() if "Anywhere" in d] or ["SQL Anywhere 11"]:
        cs = f"Driver={{{drv}}};DBF=C:\\IFS\\DataBase\\FMYE11.db;UID=DBA;PWD=sql;"
        try:
            con = pyodbc.connect(cs, timeout=8)
        except Exception as e:
            print("fail", drv, e)
            continue
        print("OPENED", drv)
        cur = con.cursor()
        queries = [
            ("max sale", "SELECT MAX(InvoiceDate) FROM saller.SaleInvoiceHeader"),
            ("max purch", "SELECT MAX(PurchaseInvoiceDate) FROM saller.PurchaseHeader"),
            ("max voucher", "SELECT MAX(VoucherDate) FROM saller.Voucher"),
            ("max sr", "SELECT MAX(SrDate) FROM saller.SrHeader"),
            ("max pr", "SELECT MAX(PrDate) FROM saller.PrHeader"),
        ]
        # try without schema too
        for label, sql in queries:
            for s in (sql, sql.replace("saller.", "")):
                try:
                    print(f"  {label}: {cur.execute(s).fetchone()} via {s}")
                    break
                except Exception as e:
                    err = e
            else:
                print(f"  {label} FAIL: {err}")
        for sql in [
            "SELECT CAST(InvoiceDate AS DATE), COUNT(*) FROM SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-06' GROUP BY CAST(InvoiceDate AS DATE) ORDER BY 1",
            "SELECT CAST(PurchaseInvoiceDate AS DATE), COUNT(*) FROM PurchaseHeader WHERE PurchaseInvoiceDate >= '2026-08-05' GROUP BY CAST(PurchaseInvoiceDate AS DATE) ORDER BY 1",
            "SELECT CAST(VoucherDate AS DATE), COUNT(*) FROM Voucher WHERE VoucherDate >= '2026-08-06' GROUP BY CAST(VoucherDate AS DATE) ORDER BY 1",
            "SELECT CAST(SrDate AS DATE), COUNT(*) FROM SrHeader WHERE SrDate >= '2026-07-28' GROUP BY CAST(SrDate AS DATE) ORDER BY 1",
            "SELECT CAST(PrDate AS DATE), COUNT(*) FROM PrHeader WHERE PrDate >= '2026-07-15' GROUP BY CAST(PrDate AS DATE) ORDER BY 1",
        ]:
            try:
                rows = cur.execute(sql).fetchall()
                print(f"  {sql[:60]}... => {rows}")
            except Exception as e:
                print(f"  FAIL: {e}")
                # try date string compare
        con.close()
        break

    # Payroll advances vs Access Balance Aug
    print("\n=== Payroll advances Aug vs Access ===")
    print("IFS advances Aug+:", list(IFS.execute(
        """SELECT request_date, COUNT(*), ROUND(SUM(amount),2)
           FROM employee_advances WHERE request_date>='2026-08-01' GROUP BY 1 ORDER BY 1""")))
    print("IFS advances max:", IFS.execute("SELECT MAX(request_date), COUNT(*) FROM employee_advances").fetchone())
    try:
        cs = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb;"
        ac = pyodbc.connect(cs)
        cur = ac.cursor()
        print("Access Balance Aug days:")
        for r in cur.execute(
            """SELECT Format(Dated,'yyyy-mm-dd'), COUNT(*), ROUND(SUM(PaidAmt),2), ROUND(SUM(Balance),2)
               FROM Balance WHERE Dated>=#2026-08-01# GROUP BY Format(Dated,'yyyy-mm-dd') ORDER BY 1"""
        ):
            print(" ", r)
        print("Access Payments Aug:")
        for r in cur.execute(
            """SELECT Format(y.Dated,'yyyy-mm-dd'), COUNT(*), ROUND(SUM(p.PaidAmt),2)
               FROM Payments p INNER JOIN Pay y ON p.ID=y.ID
               WHERE y.Dated>=#2026-08-01# GROUP BY Format(y.Dated,'yyyy-mm-dd') ORDER BY 1"""
        ):
            print(" ", r)
        ac.close()
    except Exception as e:
        print("access", e)

    # File timestamps summary
    print("\n=== FILE MTIMES ===")
    for p in [
        Path(r"C:\IFS\DataBase\FMYE11.db"),
        Path(r"C:\IFS\DataBase\FMYE11New.log"),
        ROOT / "import/fmye/full/715.dat",
        ROOT / "import/fmye/full/714.dat",
        ROOT / "import/fmye/full/732.dat",
        ROOT / "import/fmye/full/reload.sql",
        ROOT / "ifs_erp.db",
        Path(r"C:\modern_weight_scale_final\database\weight_scale.db"),
        Path(r"C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb"),
    ]:
        st = p.stat()
        print(f"  {p}: {datetime.datetime.fromtimestamp(st.st_mtime)} ({st.st_size:,} bytes)")

    # List sync scripts with one-liner usage
    print("\n=== SYNC SCRIPTS ===")
    for name in [
        "migrate_fmye.py", "import_fmye_from_dat.py", "import_fmye_vouchers_gl.py",
        "import_fmye_sl_sales.py", "import_fmye_from_csv.py", "sync_fmye_auth_status.py",
        "sync_fmye_gl_openings.py", "sync_fmye_inventory.py", "import_weight_scale.py",
        "import_payroll_hr.py", "import_product_weights.py",
    ]:
        p = ROOT / name
        print(f"  {'OK' if p.exists() else 'MISSING'}: {p}")


if __name__ == "__main__":
    main()
