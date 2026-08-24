"""Deep dive on cash book opening balance."""
import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

def opening_before(conn, d):
    coa = conn.execute(
        "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE code='000000'"
    ).fetchone()[0]
    rec = conn.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_receipts WHERE receipt_date<?", (d,)
    ).fetchone()
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_payments WHERE payment_date<?", (d,)
    ).fetchone()
    return {
        "date": d,
        "coa_ob": float(coa),
        "rec": float(rec[0]),
        "pay": float(pay[0]),
        "rec_n": rec[1],
        "pay_n": pay[1],
        "opening": float(coa) + float(rec[0]) - float(pay[0]),
        "opening_without_coa": float(rec[0]) - float(pay[0]),
    }

with db.get_connection() as conn:
    print("=== COA CASH 000000 ===")
    row = conn.execute(
        "SELECT code, name, opening_balance, current_balance FROM chart_of_accounts WHERE code='000000'"
    ).fetchone()
    print(dict(row))

    first_rec = conn.execute("SELECT MIN(receipt_date), MAX(receipt_date) FROM cash_receipts").fetchone()
    first_pay = conn.execute("SELECT MIN(payment_date), MAX(payment_date) FROM cash_payments").fetchone()
    print("Receipts range:", first_rec)
    print("Payments range:", first_pay)

    for d in ("2026-01-01", "2026-08-01", "2026-08-18", "2026-08-19", "2026-08-22", "2026-08-23", "2026-08-24"):
        o = opening_before(conn, d)
        print(f"\nOpening before {d}:")
        print(f"  COA base:     {o['coa_ob']:>15,.2f}")
        print(f"  Prior rec:    {o['rec']:>15,.2f} ({o['rec_n']} rows)")
        print(f"  Prior pay:    {o['pay']:>15,.2f} ({o['pay_n']} rows)")
        print(f"  = Opening:    {o['opening']:>15,.2f}")
        print(f"  (Vouchers only, no COA OB): {o['opening_without_coa']:>15,.2f}")

    # If COA opening were zero, what would opening be today?
    print("\n=== HYPOTHETICAL: COA opening = 0 ===")
    coa = float(row["opening_balance"])
    for d in ("2026-08-19", "2026-08-23"):
        o = opening_before(conn, d)
        print(f"  {d}: current {o['opening']:,.2f} -> without COA OB {o['opening_without_coa']:,.2f} (diff -{coa:,.2f})")

    # Day chain 18-24
    print("\n=== DAY CHAIN 18-24 Aug ===")
    d = datetime.strptime("2026-08-18", "%Y-%m-%d")
    prev_close = None
    while d <= datetime.strptime("2026-08-24", "%Y-%m-%d"):
        ds = d.strftime("%Y-%m-%d")
        o = opening_before(conn, ds)
        rec = conn.execute(
            "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_receipts WHERE receipt_date=?", (ds,)
        ).fetchone()
        pay = conn.execute(
            "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_payments WHERE payment_date=?", (ds,)
        ).fetchone()
        close = o["opening"] + float(rec[0]) - float(pay[0])
        gap = "" if prev_close is None else f" gap={o['opening']-prev_close:,.2f}"
        print(
            f"{ds} open={o['opening']:,.2f} +rec={float(rec[0]):,.2f}({rec[1]}) "
            f"-pay={float(pay[0]):,.2f}({pay[1]}) =close={close:,.2f}{gap}"
        )
        prev_close = close
        d += timedelta(days=1)

    # GL opening vs book
    aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code='000000'").fetchone()[0]
    gl_before_23 = conn.execute(
        "SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) FROM general_ledger WHERE account_id=? AND entry_date<'2026-08-23'",
        (aid,),
    ).fetchone()[0]
    print(f"\nGL movement before 2026-08-23 (excl COA OB): {float(gl_before_23):,.2f}")
    print(f"Book opening 2026-08-23 should be COA {coa:,.2f} + GL movement = {coa + float(gl_before_23):,.2f}")
