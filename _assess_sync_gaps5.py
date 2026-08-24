"""Live FMYE11 day counts with saller schema + purchase Aug6 gap + payroll advance totals."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pyodbc

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))
from import_fmye_from_dat import FMYEExport, _d  # noqa: E402

IFS = sqlite3.connect(str(ROOT / "ifs_erp.db"))
IFS.row_factory = sqlite3.Row
EXP = FMYEExport(ROOT / "import" / "fmye" / "full")


def main():
    cs = r"Driver={SQL Anywhere 11};DBF=C:\IFS\DataBase\FMYE11.db;UID=DBA;PWD=sql;"
    con = pyodbc.connect(cs, timeout=10)
    cur = con.cursor()

    print("=== LIVE day counts ===")
    sqls = [
        ("sales", """SELECT CAST(InvoiceDate AS DATE) d, COUNT(*) c
            FROM saller.SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-01'
            GROUP BY CAST(InvoiceDate AS DATE) ORDER BY 1"""),
        ("purchases", """SELECT CAST(PurchaseInvoiceDate AS DATE) d, COUNT(*) c
            FROM saller.PurchaseHeader WHERE PurchaseInvoiceDate >= '2026-08-01'
            GROUP BY CAST(PurchaseInvoiceDate AS DATE) ORDER BY 1"""),
        ("vouchers", """SELECT CAST(VoucherDate AS DATE) d, COUNT(*) c
            FROM saller.Voucher WHERE VoucherDate >= '2026-08-01'
            GROUP BY CAST(VoucherDate AS DATE) ORDER BY 1"""),
        ("sr", """SELECT CAST(SrDate AS DATE) d, COUNT(*) c
            FROM saller.SrHeader WHERE SrDate >= '2026-07-01'
            GROUP BY CAST(SrDate AS DATE) ORDER BY 1"""),
        ("pr", """SELECT CAST(PrDate AS DATE) d, COUNT(*) c
            FROM saller.PrHeader WHERE PrDate >= '2026-07-01'
            GROUP BY CAST(PrDate AS DATE) ORDER BY 1"""),
        ("voucher_types_aug6", """SELECT VoucherType, COUNT(*) c
            FROM saller.Voucher WHERE VoucherDate = '2026-08-06' GROUP BY VoucherType"""),
        ("purch_aug6_docs", """SELECT PurchaseInvoiceCode, DocumentNo, PartyCode, Name, NetAmount, Status
            FROM saller.PurchaseHeader WHERE PurchaseInvoiceDate = '2026-08-06'"""),
        ("sales_aug6", """SELECT DocumentNo, PartyCode, NetAmount, Status
            FROM saller.SaleInvoiceHeader WHERE InvoiceDate = '2026-08-06' ORDER BY DocumentNo"""),
        ("sales_aug7plus", """SELECT COUNT(*) FROM saller.SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-07'"""),
        ("purch_aug7plus", """SELECT COUNT(*) FROM saller.PurchaseHeader WHERE PurchaseInvoiceDate >= '2026-08-07'"""),
        ("vouch_aug7plus", """SELECT COUNT(*) FROM saller.Voucher WHERE VoucherDate >= '2026-08-07'"""),
    ]
    for label, sql in sqls:
        try:
            rows = cur.execute(sql).fetchall()
            print(f"{label}: {rows}")
        except Exception as e:
            print(f"{label} FAIL: {e}")

    # Compare live purchase Aug6 vs IFS
    print("\n=== Purchase Aug6 live vs IFS ===")
    live_pi = cur.execute(
        """SELECT PurchaseInvoiceCode, DocumentNo, NetAmount, Status
           FROM saller.PurchaseHeader WHERE PurchaseInvoiceDate = '2026-08-06'"""
    ).fetchall()
    ifs_pi = {r[0] for r in IFS.execute(
        "SELECT document_no FROM purchase_invoices WHERE invoice_date='2026-08-06'")}
    print("IFS PI Aug6:", ifs_pi)
    for r in live_pi:
        code = str(r[0]).strip()
        doc = f"PI-{code}"
        print(f"  live code={code} doc={doc} amt={r[2]} status={r[3]} in_ifs={doc in ifs_pi}")

    # Compare export purchase max vs live
    exp_purch = EXP.rows("PurchaseHeader")
    exp_by = Counter(_d(r.get("PurchaseInvoiceDate")) for r in exp_purch)
    print("\nExport PurchaseHeader Aug+:", {d: exp_by[d] for d in sorted(exp_by) if d >= "2026-08-01"})
    live_purch_aug = cur.execute(
        """SELECT CAST(PurchaseInvoiceDate AS DATE) d, COUNT(*) c
           FROM saller.PurchaseHeader WHERE PurchaseInvoiceDate >= '2026-08-01'
           GROUP BY CAST(PurchaseInvoiceDate AS DATE) ORDER BY 1"""
    ).fetchall()
    print("Live PurchaseHeader Aug+:", live_purch_aug)

    # Voucher line counts live vs export Aug6
    live_v = cur.execute(
        """SELECT CAST(VoucherDate AS DATE) d, COUNT(*) c
           FROM saller.Voucher WHERE VoucherDate >= '2026-08-01'
           GROUP BY CAST(VoucherDate AS DATE) ORDER BY 1"""
    ).fetchall()
    exp_v = Counter(_d(r.get("VoucherDate")) for r in EXP.rows("Voucher"))
    print("\nVoucher lines Aug+ export vs live:")
    for d, c in live_v:
        ds = str(d)
        print(f"  {ds}: export={exp_v.get(ds,0)} live={c} gap={c - exp_v.get(ds,0)}")

    # Sales same
    live_s = cur.execute(
        """SELECT CAST(InvoiceDate AS DATE) d, COUNT(*) c
           FROM saller.SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-01'
           GROUP BY CAST(InvoiceDate AS DATE) ORDER BY 1"""
    ).fetchall()
    exp_s = Counter(_d(r.get("InvoiceDate")) for r in EXP.rows("SaleInvoiceHeader"))
    print("\nSales Aug+ export vs live:")
    for d, c in live_s:
        ds = str(d)
        print(f"  {ds}: export={exp_s.get(ds,0)} live={c} gap={c - exp_s.get(ds,0)}")

    # Cash/bank header counts live Aug6
    print("\nLive cash/bank/JVR headers Aug6+:")
    rows = cur.execute(
        """SELECT CAST(VoucherDate AS DATE) d, VoucherType, COUNT(DISTINCT TransactionNO) c
           FROM saller.Voucher
           WHERE VoucherDate >= '2026-08-06' AND VoucherType IN ('CRV','CPV','BRV','BPV','JVR')
           GROUP BY CAST(VoucherDate AS DATE), VoucherType ORDER BY 1,2"""
    ).fetchall()
    print(rows)

    # IFS cash using correct date cols
    print("\nIFS cash/bank Aug+ (correct cols):")
    for t, dc in [
        ("cash_receipts", "receipt_date"),
        ("cash_payments", "payment_date"),
        ("bank_receipts", "receipt_date"),
        ("bank_payments", "payment_date"),
        ("journal_vouchers", "voucher_date"),
    ]:
        rows = list(IFS.execute(
            f"SELECT {dc}, COUNT(*) FROM {t} WHERE {dc}>='2026-08-01' GROUP BY 1 ORDER BY 1"
        ))
        print(f"  {t}: {rows}")

    # Payroll: ending balance advances — how many updated today?
    print("\nIFS employee_advances:")
    print("  count", IFS.execute("SELECT COUNT(*) FROM employee_advances").fetchone()[0])
    print("  by request_date Jul+:", list(IFS.execute(
        "SELECT request_date, COUNT(*), ROUND(SUM(amount),2) FROM employee_advances WHERE request_date>='2026-07-01' GROUP BY 1 ORDER BY 1")))
    print("  reason Access ending:", IFS.execute(
        "SELECT COUNT(*), ROUND(SUM(amount),2), MAX(request_date), MAX(modified_at) FROM employee_advances WHERE reason LIKE '%Access ending%'"
    ).fetchone())

    # import_fmye_vouchers_gl skip logic
    from import_fmye_vouchers_gl import apply as gl_apply
    import inspect
    src = inspect.getsource(gl_apply)
    if "existing" in src:
        print("\nimport_fmye_vouchers_gl has existing-skip logic: YES")
    else:
        print("\nimport_fmye_vouchers_gl has existing-skip logic: check manually")
    for line in src.splitlines():
        if "existing" in line or "skip" in line.lower() or "document_no" in line:
            print(" ", line.strip())

    con.close()


if __name__ == "__main__":
    main()
