"""Diagnose cash book vs GL for 2026-08-19."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import database as db
from db_v3 import gl_account_code

TARGET = "2026-08-19"
NEXT = "2026-08-20"


def cash_account(conn):
    for code in ("000000", "1000"):
        row = conn.execute(
            "SELECT id, code, name, COALESCE(opening_balance,0) AS ob FROM chart_of_accounts WHERE code=? AND is_active=1",
            (code,),
        ).fetchone()
        if row:
            return dict(row)
    return None


def book_balance(conn, before_date: str) -> dict:
    ca = cash_account(conn)
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
        "coa_opening": base,
        "prior_receipts": float(rec[0]),
        "prior_payments": float(pay[0]),
        "opening": base + float(rec[0]) - float(pay[0]),
        "prior_receipt_count": int(rec[1]),
        "prior_payment_count": int(pay[1]),
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
        return {"code": code, "error": "cash GL account not found"}
    aid = row["id"]
    gl = conn.execute(
        """SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0), COUNT(*)
           FROM general_ledger WHERE account_id=? AND entry_date<=?""",
        (aid, through_date),
    ).fetchone()
    ob = float(row["ob"])
    deb = float(gl[0])
    cr = float(gl[1])
    return {
        "code": row["code"],
        "name": row["name"],
        "coa_opening": ob,
        "gl_debit": deb,
        "gl_credit": cr,
        "balance": ob + deb - cr,
        "entry_count": int(gl[2]),
    }


def gl_cash_on_date(conn, d: str) -> dict:
    code = gl_account_code("cash")
    aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()["id"]
    gl = conn.execute(
        """SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0), COUNT(*)
           FROM general_ledger WHERE account_id=? AND entry_date=?""",
        (aid, d),
    ).fetchone()
    return {"debit": float(gl[0]), "credit": float(gl[1]), "net_dr_minus_cr": float(gl[0]) - float(gl[1]), "count": int(gl[2])}


def book_only_entries(conn, through_date: str) -> list:
    """Cash book rows with no matching GL cash movement (rough heuristic)."""
    code = gl_account_code("cash")
    aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()["id"]
    rows = []
    for tbl, dt_col, sign in (
        ("cash_receipts", "receipt_date", 1),
        ("cash_payments", "payment_date", -1),
    ):
        for r in conn.execute(
            f"""SELECT id, document_no, {dt_col} AS dt, amount, description, reference_no
                FROM {tbl} WHERE {dt_col}<=? ORDER BY {dt_col}, id""",
            (through_date,),
        ).fetchall():
            doc = r["document_no"] or ""
            ref = r["reference_no"] or ""
            amt = float(r["amount"])
            gl = conn.execute(
                """SELECT COUNT(*), COALESCE(SUM(debit-credit),0)
                   FROM general_ledger
                   WHERE account_id=? AND entry_date=? AND ABS(debit-credit-?)<0.01""",
                (aid, r["dt"], amt * sign),
            ).fetchone()
            if int(gl[0]) == 0:
                rows.append(
                    {
                        "table": tbl,
                        "id": r["id"],
                        "date": r["dt"],
                        "document_no": doc,
                        "reference_no": ref,
                        "amount": amt,
                        "description": (r["description"] or "")[:80],
                    }
                )
    return rows


def gl_without_book(conn, d: str) -> list:
    code = gl_account_code("cash")
    aid = conn.execute("SELECT id FROM chart_of_accounts WHERE code=?", (code,)).fetchone()["id"]
    rows = conn.execute(
        """SELECT id, entry_date, debit, credit, description, reference_type, reference_id, reference_no
           FROM general_ledger WHERE account_id=? AND entry_date=?
           ORDER BY id""",
        (aid, d),
    ).fetchall()
    out = []
    for r in rows:
        ref = r["reference_no"] or ""
        ref_type = r["reference_type"] or ""
        amt = float(r["debit"] or 0) - float(r["credit"] or 0)
        matched = False
        if ref:
            for tbl, col in (("cash_receipts", "reference_no"), ("cash_payments", "reference_no")):
                if conn.execute(f"SELECT 1 FROM {tbl} WHERE {col}=? AND amount=ABS(?)", (ref, amt)).fetchone():
                    matched = True
                    break
            if not matched:
                for tbl, col in (("cash_receipts", "document_no"), ("cash_payments", "document_no")):
                    if conn.execute(f"SELECT 1 FROM {tbl} WHERE {col}=?", (ref,)).fetchone():
                        matched = True
                        break
        out.append(
            {
                "gl_id": r["id"],
                "debit": float(r["debit"] or 0),
                "credit": float(r["credit"] or 0),
                "net": amt,
                "reference_type": ref_type,
                "reference_no": ref,
                "description": (r["description"] or "")[:60],
                "likely_in_book": matched,
            }
        )
    return out


def duplicate_invoice_cash(conn, d: str) -> list:
    """Cash sales invoice GL + separate customer receipt same day/ref."""
    rows = conn.execute(
        """SELECT s.document_no, s.total, cr.document_no AS cr_doc, cr.amount AS cr_amt
           FROM sales_invoices s
           JOIN cash_receipts cr ON cr.reference_no = s.document_no AND cr.receipt_date=?
           WHERE s.invoice_date=? AND LOWER(COALESCE(s.payment_mode,''))='cash'
             AND EXISTS (
               SELECT 1 FROM general_ledger gl
               JOIN chart_of_accounts coa ON coa.id=gl.account_id
               WHERE gl.reference_type='sales_invoice' AND gl.reference_id=s.id
                 AND coa.code IN (SELECT code FROM chart_of_accounts WHERE code IN ('000000','1000'))
             )""",
        (d, d),
    ).fetchall()
    return [dict(r) for r in rows]


def provisional_on_date(conn, d: str) -> list:
    return db.get_provisional_cash_sale_invoices(d, d)


def main():
    report = {"target": TARGET, "when": datetime.now().isoformat(timespec="seconds")}
    with db.get_connection() as conn:
        ca = cash_account(conn)
        report["cash_coa"] = ca

        open19 = book_balance(conn, TARGET)
        day19 = day_totals(conn, TARGET)
        open20 = book_balance(conn, NEXT)
        close19 = open19["opening"] + day19["net"]

        report["book"] = {
            "opening_19": open19,
            "day_19": day19,
            "closing_19_calc": round(close19, 2),
            "opening_20": open20,
            "carry_forward_gap": round(open20["opening"] - close19, 2),
        }

        report["gl_through_19"] = gl_cash_balance(conn, TARGET)
        report["gl_on_19"] = gl_cash_on_date(conn, TARGET)
        report["book_vs_gl_through_19"] = round(close19 - report["gl_through_19"]["balance"], 2)

        report["book_only_through_19"] = book_only_entries(conn, TARGET)
        report["book_only_on_19"] = [r for r in report["book_only_through_19"] if r["date"] == TARGET]
        report["gl_on_19_detail"] = gl_without_book(conn, TARGET)
        report["gl_on_19_not_in_book"] = [r for r in report["gl_on_19_detail"] if not r["likely_in_book"]]
        report["duplicate_invoice_cash_19"] = duplicate_invoice_cash(conn, TARGET)
        report["provisional_cash_sales_19"] = provisional_on_date(conn, TARGET)

        close_row = conn.execute(
            "SELECT * FROM cash_day_closes WHERE close_date=? AND reopened_at IS NULL",
            (TARGET,),
        ).fetchone()
        report["day_closed"] = dict(close_row) if close_row else None

        # Adjacent day check
        prev = (datetime.strptime(TARGET, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        open_prev_close = book_balance(conn, prev)
        day_prev = day_totals(conn, prev)
        close_prev = open_prev_close["opening"] + day_prev["net"]
        report["prev_day"] = {
            "date": prev,
            "closing": round(close_prev, 2),
            "opening_19": open19["opening"],
            "gap": round(open19["opening"] - close_prev, 2),
        }

    out = ROOT / "reports" / f"cash_diag_{TARGET.replace('-', '')}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    b = report["book"]
    print("=== CASH BOOK", TARGET, "===")
    print(f"COA opening (000000/1000): {b['opening_19']['coa_opening']:,.2f}")
    print(f"Opening {TARGET}: {b['opening_19']['opening']:,.2f}")
    print(f"Receipts: {b['day_19']['receipts']:,.2f} ({b['day_19']['receipt_count']})")
    print(f"Payments: {b['day_19']['payments']:,.2f} ({b['day_19']['payment_count']})")
    print(f"Closing (calc): {b['closing_19_calc']:,.2f}")
    print(f"Opening {NEXT}: {b['opening_20']['opening']:,.2f}")
    print(f"Carry-forward gap: {b['carry_forward_gap']:,.2f}")

    g = report["gl_through_19"]
    print("\n=== GL CASH through", TARGET, "===")
    print(f"Account: {g.get('code')} {g.get('name')}")
    print(f"GL balance: {g.get('balance', 0):,.2f} ({g.get('entry_count', 0)} entries)")
    print(f"Book closing vs GL: {report['book_vs_gl_through_19']:,.2f}")

    pd = report["prev_day"]
    print(f"\n=== Previous day {pd['date']} closing vs {TARGET} opening ===")
    print(f"Close {pd['date']}: {pd['closing']:,.2f}")
    print(f"Open {TARGET}: {pd['opening_19']:,.2f}")
    print(f"Gap: {pd['gap']:,.2f}")

    print(f"\nBook-only entries on {TARGET}: {len(report['book_only_on_19'])}")
    for r in report["book_only_on_19"][:15]:
        print(f"  {r['document_no']} | {r['amount']:,.2f} | {r['description']}")

    print(f"\nGL on {TARGET} not matched to book: {len(report['gl_on_19_not_in_book'])}")
    for r in report["gl_on_19_not_in_book"][:15]:
        print(f"  GL#{r['gl_id']} {r['reference_type']} {r['reference_no']} net={r['net']:,.2f}")

    print(f"\nDuplicate invoice+cash receipt on {TARGET}: {len(report['duplicate_invoice_cash_19'])}")
    for r in report["duplicate_invoice_cash_19"][:10]:
        print(f"  {r['document_no']} total={r['total']} cr={r['cr_amt']}")

    prov = report["provisional_cash_sales_19"]
    print(f"\nProvisional cash sales on {TARGET} (NOT in closing): {len(prov)}")
    for r in prov[:10]:
        print(f"  {r['document_no']} {r['status']} {float(r['amount']):,.2f}")

    print("\nWROTE", out)


if __name__ == "__main__":
    main()
