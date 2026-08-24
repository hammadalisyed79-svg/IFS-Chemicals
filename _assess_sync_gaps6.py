"""Final concrete missing-doc lists for the report."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pyodbc

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))
from import_fmye_from_dat import FMYEExport, _d  # noqa: E402

IFS = sqlite3.connect(str(ROOT / "ifs_erp.db"))
IFS.row_factory = sqlite3.Row
EXP = FMYEExport(ROOT / "import" / "fmye" / "full")

cs = r"Driver={SQL Anywhere 11};DBF=C:\IFS\DataBase\FMYE11.db;UID=DBA;PWD=sql;"
con = pyodbc.connect(cs, timeout=10)
cur = con.cursor()

ifs_sales = {r[0] for r in IFS.execute("SELECT document_no FROM sales_invoices")}
live_sales = cur.execute(
    """SELECT DocumentNo, InvoiceDate, PartyCode, NetAmount, Status
       FROM saller.SaleInvoiceHeader WHERE InvoiceDate >= '2026-08-06' ORDER BY InvoiceDate, DocumentNo"""
).fetchall()
print("=== Missing sales (live FMYE not in IFS) ===")
miss_s = []
for r in live_sales:
    doc = str(r[0]).strip()
    if doc not in ifs_sales:
        miss_s.append(r)
        print(f"  {r[1]} {doc} party={r[2]} amt={r[3]} status={r[4]}")
print(f"TOTAL missing sales: {len(miss_s)}")

ifs_pi = {r[0] for r in IFS.execute("SELECT document_no FROM purchase_invoices")}
live_pi = cur.execute(
    """SELECT PurchaseInvoiceCode, PurchaseInvoiceDate, PartyCode, NetAmount, Status
       FROM saller.PurchaseHeader WHERE PurchaseInvoiceDate >= '2026-08-06' ORDER BY 2,1"""
).fetchall()
print("\n=== Missing purchases ===")
for r in live_pi:
    doc = f"PI-{str(r[0]).strip()}"
    if doc not in ifs_pi:
        print(f"  {r[1]} {doc} party={r[2]} amt={r[3]} status={r[4]}")

print("\n=== Cash/bank/JV Aug6 IFS vs live headers ===")
for t, dc in [
    ("cash_receipts", "receipt_date"),
    ("cash_payments", "payment_date"),
    ("bank_receipts", "receipt_date"),
    ("bank_payments", "payment_date"),
    ("journal_vouchers", "voucher_date"),
]:
    for d in ("2026-08-05", "2026-08-06"):
        n = IFS.execute(f"SELECT COUNT(*) FROM {t} WHERE {dc}=?", (d,)).fetchone()[0]
        print(f"  IFS {t} {d}: {n}")

live_h = cur.execute(
    """SELECT CAST(VoucherDate AS DATE) d, VoucherType, COUNT(DISTINCT TransactionNO)
       FROM saller.Voucher
       WHERE VoucherDate >= '2026-08-05' AND VoucherType IN ('CRV','CPV','BRV','BPV','JVR')
       GROUP BY CAST(VoucherDate AS DATE), VoucherType ORDER BY 1,2"""
).fetchall()
print("Live headers Aug5+:", live_h)

# export headers Aug5-6
from collections import Counter
exp_h = Counter()
for r in EXP.rows("Voucher"):
    d = _d(r.get("VoucherDate"))
    if d < "2026-08-05":
        continue
    vt = (r.get("VoucherType") or "").strip().upper()
    if vt in {"CRV", "CPV", "BRV", "BPV", "JVR"}:
        exp_h[(d, vt, str(r.get("TransactionNO") or "").strip())] = 1
exp_counts = Counter()
for d, vt, tno in exp_h:
    exp_counts[(d, vt)] += 1
print("Export headers Aug5+:", dict(sorted(exp_counts.items())))

print("\n=== IFS sales Aug6 ===", IFS.execute(
    "SELECT COUNT(*) FROM sales_invoices WHERE invoice_date='2026-08-06'").fetchone()[0])
print("IFS sales docs Aug6:", sorted(r[0] for r in IFS.execute(
    "SELECT document_no FROM sales_invoices WHERE invoice_date='2026-08-06'")))

print("\nPayroll Access ending vs IFS advances (Access ending reason):")
row = IFS.execute(
    """SELECT COUNT(*), ROUND(SUM(amount),2), MAX(request_date), MAX(COALESCE(modified_at, created_at))
       FROM employee_advances WHERE reason LIKE '%Access ending%'"""
).fetchone()
print(" ", row)
# Sum of negative balances in Access
neg = cur_ac = None
acs = r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb;"
ac = pyodbc.connect(acs)
acur = ac.cursor()
# latest balance per ID
rows = acur.execute("SELECT ID, Dated, Balance FROM Balance ORDER BY ID, Dated").fetchall()
last = {}
for r in rows:
    last[int(r[0])] = (_d(r[1]) if hasattr(r[1], 'strftime') else str(r[1])[:10], float(r[2] or 0))
neg_n = sum(1 for _, (d, b) in last.items() if b < -0.01)
neg_sum = sum(abs(b) for _, (d, b) in last.items() if b < -0.01)
print(f"Access latest Balance negative employees: {neg_n} sum={neg_sum:.2f}")
print(f"Access latest balance dates max: {max(d for d,_ in last.values())}")
ac.close()
con.close()
