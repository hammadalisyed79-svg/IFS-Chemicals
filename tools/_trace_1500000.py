"""Find 1.5M cash book / GL entries and audit trail."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

AMT = 1500000.0
DATE = "2026-08-23"
EXPECTED_OPEN = 1058010.0
CURRENT_OPEN = 2558010.0

with db.get_connection() as conn:
    print("=== 1.5M cash receipts (any date) ===")
    for r in conn.execute(
        """SELECT id, document_no, receipt_date, amount, description, reference_no
           FROM cash_receipts WHERE ABS(amount-?)<1 ORDER BY receipt_date""",
        (AMT,),
    ).fetchall():
        print(dict(r))

    print("\n=== 1.5M cash payments (any date) ===")
    for r in conn.execute(
        """SELECT id, document_no, payment_date, amount, description, reference_no
           FROM cash_payments WHERE ABS(amount-?)<1 ORDER BY payment_date""",
        (AMT,),
    ).fetchall():
        print(dict(r))

    print("\n=== GL cash 1.5M ===")
    aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code='000000'").fetchone()[0]
    for r in conn.execute(
        """SELECT id, entry_date, debit, credit, reference_type, reference_no, description
           FROM general_ledger WHERE account_id=? AND (ABS(debit-?)<1 OR ABS(credit-?)<1)
           ORDER BY entry_date""",
        (aid, AMT, AMT),
    ).fetchall():
        print(dict(r))

    print("\n=== CR-126929 / CP-126909 ===")
    for ref in ("CR-126929", "CP-126909"):
        for tbl, dc in (("cash_receipts", "receipt_date"), ("cash_payments", "payment_date")):
            rows = conn.execute(
                f"SELECT * FROM {tbl} WHERE document_no=? OR reference_no=?", (ref, ref)
            ).fetchall()
            if rows:
                print(tbl, [dict(x) for x in rows])
        gl = conn.execute(
            "SELECT * FROM general_ledger WHERE reference_no=?", (ref,)
        ).fetchall()
        print("GL", len(gl), "rows")
        for g in gl:
            print(dict(g))

    print("\n=== Receipts 1.4M-1.6M before 2026-08-23 ===")
    for r in conn.execute(
        """SELECT id, document_no, receipt_date, amount, description, reference_no
           FROM cash_receipts WHERE receipt_date<? AND amount BETWEEN 1400000 AND 1600000
           ORDER BY receipt_date""",
        (DATE,),
    ).fetchall():
        print(dict(r))

    print("\n=== Opening math ===")
    coa = conn.execute(
        "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE code='000000'"
    ).fetchone()[0]
    rec = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM cash_receipts WHERE receipt_date<?", (DATE,)
    ).fetchone()[0]
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM cash_payments WHERE payment_date<?", (DATE,)
    ).fetchone()[0]
    print(f"COA OB: {float(coa):,.2f}")
    print(f"Receipts before {DATE}: {float(rec):,.2f}")
    print(f"Payments before {DATE}: {float(pay):,.2f}")
    print(f"Opening: {float(coa)+float(rec)-float(pay):,.2f}")
    print(f"Expected: {EXPECTED_OPEN:,.2f}")
    print(f"Gap: {float(coa)+float(rec)-float(pay)-EXPECTED_OPEN:,.2f}")
    print(f"If remove 1.5M receipt from before 23-08: {float(coa)+float(rec)-float(pay)-AMT:,.2f}")

    print("\n=== Audit log deletes (cash / 1.5M / CA) ===")
    try:
        for r in conn.execute(
            """SELECT id, created_at, action, entity_type, document_no, summary
               FROM audit_log
               WHERE (summary LIKE '%1500000%' OR summary LIKE '%1,500,000%'
                      OR summary LIKE '%CR-126929%' OR summary LIKE '%cash_advance%'
                      OR summary LIKE '%delete%' OR entity_type LIKE '%cash%')
               ORDER BY id DESC LIMIT 40"""
        ).fetchall():
            print(dict(r))
    except Exception as e:
        print("audit_log:", e)

    print("\n=== Cash receipts on 2026-08-09 around 1.5M ===")
    for r in conn.execute(
        """SELECT id, document_no, receipt_date, amount, description, reference_no
           FROM cash_receipts WHERE receipt_date='2026-08-09' AND amount>1000000
           ORDER BY amount DESC"""
    ).fetchall():
        print(dict(r))
