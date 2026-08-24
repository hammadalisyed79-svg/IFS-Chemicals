"""Full cash book audit — opening, carry-forward, GL gap."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db
from db_v3 import gl_account_code

TODAY = "2026-08-23"


def cash_coa(conn):
    for code in ("000000", "1000"):
        row = conn.execute(
            """SELECT id, code, name, COALESCE(opening_balance,0) AS ob,
                      COALESCE(current_balance,0) AS cb
               FROM chart_of_accounts WHERE code=? AND is_active=1""",
            (code,),
        ).fetchone()
        if row:
            return dict(row)
    return None


def book_opening(conn, before_date: str) -> dict:
    ca = cash_coa(conn)
    base = float(ca["ob"]) if ca else 0.0
    rec = conn.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_receipts WHERE receipt_date<?",
        (before_date,),
    ).fetchone()
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_payments WHERE payment_date<?",
        (before_date,),
    ).fetchone()
    return {
        "coa_code": ca["code"] if ca else None,
        "coa_opening": base,
        "prior_receipts": float(rec[0]),
        "prior_payments": float(pay[0]),
        "opening": base + float(rec[0]) - float(pay[0]),
        "receipt_count": int(rec[1]),
        "payment_count": int(pay[1]),
    }


def day_totals(conn, d: str) -> dict:
    rec = conn.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_receipts WHERE receipt_date=?",
        (d,),
    ).fetchone()
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM cash_payments WHERE payment_date=?",
        (d,),
    ).fetchone()
    return {
        "receipts": float(rec[0]),
        "receipt_count": int(rec[1]),
        "payments": float(pay[0]),
        "payment_count": int(pay[1]),
        "net": float(rec[0]) - float(pay[0]),
    }


def gl_cash_balance(conn, through_date: str) -> dict:
    code = gl_account_code("cash")
    row = conn.execute(
        "SELECT id, code, name, COALESCE(opening_balance,0) AS ob FROM chart_of_accounts WHERE code=?",
        (code,),
    ).fetchone()
    if not row:
        return {"error": "no cash GL"}
    aid = row["id"]
    gl = conn.execute(
        """SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0), COUNT(*)
           FROM general_ledger WHERE account_id=? AND entry_date<=?""",
        (aid, through_date),
    ).fetchone()
    ob = float(row["ob"])
    deb, cr = float(gl[0]), float(gl[1])
    return {
        "code": row["code"],
        "coa_opening": ob,
        "gl_debit": deb,
        "gl_credit": cr,
        "balance": ob + deb - cr,
        "entry_count": int(gl[2]),
    }


def carry_forward_gaps(conn, from_date: str, to_date: str) -> list:
    gaps = []
    d = datetime.strptime(from_date, "%Y-%m-%d")
    end = datetime.strptime(to_date, "%Y-%m-%d")
    prev_close = None
    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        op = book_opening(conn, ds)
        day = day_totals(conn, ds)
        close = op["opening"] + day["net"]
        if prev_close is not None and abs(op["opening"] - prev_close) > 0.01:
            gaps.append({
                "date": ds,
                "prev_close": round(prev_close, 2),
                "opening": round(op["opening"], 2),
                "gap": round(op["opening"] - prev_close, 2),
            })
        prev_close = close
        d += timedelta(days=1)
    return gaps


def main():
    report = {"when": datetime.now().isoformat(timespec="seconds")}
    with db.get_connection() as conn:
        ca = cash_coa(conn)
        report["cash_coa"] = ca

        # Overall
        ob_all = book_opening(conn, "9999-12-31")
        rec_all = conn.execute("SELECT COALESCE(SUM(amount),0) FROM cash_receipts").fetchone()[0]
        pay_all = conn.execute("SELECT COALESCE(SUM(amount),0) FROM cash_payments").fetchone()[0]
        closing_all = ob_all["coa_opening"] + float(rec_all) - float(pay_all)
        report["lifetime"] = {
            "coa_opening": ob_all["coa_opening"],
            "total_receipts": float(rec_all),
            "total_payments": float(pay_all),
            "book_closing": closing_all,
        }
        gl = gl_cash_balance(conn, TODAY)
        report["gl_through_today"] = gl
        report["book_vs_gl"] = round(closing_all - gl["balance"], 2)

        # Today
        ob_today = book_opening(conn, TODAY)
        day_today = day_totals(conn, TODAY)
        close_today = ob_today["opening"] + day_today["net"]
        next_day = (datetime.strptime(TODAY, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        ob_next = book_opening(conn, next_day)
        report["today"] = {
            "date": TODAY,
            "opening": ob_today,
            "day": day_today,
            "closing": close_today,
            "opening_next_day": ob_next["opening"],
            "carry_gap": round(ob_next["opening"] - close_today, 2),
        }

        # Key dates around Aug 2026
        for d in ("2026-08-18", "2026-08-19", "2026-08-20", "2026-08-22", "2026-08-23"):
            op = book_opening(conn, d)
            day = day_totals(conn, d)
            report[f"day_{d}"] = {
                "opening": op["opening"],
                "receipts": day["receipts"],
                "payments": day["payments"],
                "closing": op["opening"] + day["net"],
            }

        # Carry-forward gaps Aug 2026
        report["carry_gaps_aug"] = carry_forward_gaps(conn, "2026-08-01", TODAY)

        # GL orphans (no cash book match) through today
        code = gl_account_code("cash")
        aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()["id"]
        orphans = conn.execute(
            """SELECT gl.id, gl.entry_date, gl.debit, gl.credit, gl.reference_type, gl.reference_no, gl.description
               FROM general_ledger gl
               WHERE gl.account_id=? AND gl.entry_date<=?
                 AND NOT EXISTS (
                   SELECT 1 FROM cash_receipts cr
                   WHERE cr.receipt_date=gl.entry_date AND ABS(cr.amount-gl.debit)<0.01 AND gl.debit>0
                     AND (cr.document_no=gl.reference_no OR cr.reference_no=gl.reference_no
                          OR (gl.reference_no LIKE 'SAL-%' AND cr.reference_no=gl.reference_no))
                 )
                 AND NOT EXISTS (
                   SELECT 1 FROM cash_payments cp
                   WHERE cp.payment_date=gl.entry_date AND ABS(cp.amount-gl.credit)<0.01 AND gl.credit>0
                     AND (cp.document_no=gl.reference_no OR cp.reference_no=gl.reference_no)
                 )
               ORDER BY ABS(gl.debit-gl.credit) DESC
               LIMIT 20""",
            (aid, TODAY),
        ).fetchall()
        orphan_net = sum(float(r["debit"] or 0) - float(r["credit"] or 0) for r in orphans)
        report["gl_orphans_top"] = [dict(r) for r in orphans]
        report["gl_orphans_top_net"] = orphan_net

        # COA opening vs sum of GL before first cash txn
        first = conn.execute(
            """SELECT MIN(dt) FROM (
                 SELECT MIN(receipt_date) AS dt FROM cash_receipts
                 UNION SELECT MIN(payment_date) FROM cash_payments
               )"""
        ).fetchone()[0]
        report["first_cash_activity"] = first

        # Compare COA opening to FMYE expectation
        report["opening_formula_check"] = {
            "coa_opening": ob_all["coa_opening"],
            "plus_all_receipts_minus_payments": closing_all,
            "note": "Opening in UI = COA opening + receipts before date - payments before date",
        }

    out = ROOT / "reports" / f"cash_book_audit_{TODAY.replace('-', '')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=== CASH BOOK AUDIT ===")
    print(f"Cash COA: {ca['code']} {ca['name']}")
    print(f"COA opening balance: {report['lifetime']['coa_opening']:,.2f}")
    print(f"Lifetime receipts:   {report['lifetime']['total_receipts']:,.2f}")
    print(f"Lifetime payments:   {report['lifetime']['total_payments']:,.2f}")
    print(f"Book closing (all):  {report['lifetime']['book_closing']:,.2f}")
    print(f"GL cash through {TODAY}: {gl['balance']:,.2f}")
    print(f"Book vs GL gap:      {report['book_vs_gl']:,.2f}")

    t = report["today"]
    print(f"\n=== {TODAY} ===")
    print(f"Opening:  {t['opening']['opening']:,.2f}")
    print(f"Receipts: {t['day']['receipts']:,.2f} ({t['day']['receipt_count']})")
    print(f"Payments: {t['day']['payments']:,.2f} ({t['day']['payment_count']})")
    print(f"Closing:  {t['closing']:,.2f}")
    print(f"Carry gap to next day: {t['carry_gap']:,.2f}")

    if report["carry_gaps_aug"]:
        print(f"\nCarry-forward gaps in Aug: {len(report['carry_gaps_aug'])}")
        for g in report["carry_gaps_aug"][:10]:
            print(f"  {g['date']}: prev close {g['prev_close']:,.2f} vs open {g['opening']:,.2f} gap {g['gap']:,.2f}")
    else:
        print("\nNo carry-forward gaps Aug 1 - today (internal math OK)")

    if report["gl_orphans_top"]:
        print(f"\nTop GL cash rows without cash book match (net sample: {orphan_net:,.2f}):")
        for r in report["gl_orphans_top"][:8]:
            print(
                f"  {r['entry_date']} {r['reference_no']} {r['reference_type']} "
                f"dr={float(r['debit'] or 0):,.2f} cr={float(r['credit'] or 0):,.2f}"
            )

    print("\nWROTE", out)


if __name__ == "__main__":
    main()
