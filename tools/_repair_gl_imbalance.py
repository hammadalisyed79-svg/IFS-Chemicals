"""Repair unbalanced GL vouchers and print full transaction details.

Repairs:
  CR-126928 / CR-126932 — add missing Dr CASH A/C (000000)
  JVR-126885 — neutralize orphan Cr SALE A/C (invoice 26080116 already posted in ERP)
"""
from __future__ import annotations

import json
from datetime import datetime

import database as db
from db_v3 import _acct_id, gl_account_code, post_gl_account_id

REFS = ("CR-126928", "CR-126932", "JVR-126885")


def rowd(r):
    return dict(r) if r is not None else None


def ledger_net(conn):
    return rowd(
        conn.execute(
            "SELECT ROUND(SUM(debit),2) dr, ROUND(SUM(credit),2) cr, "
            "ROUND(SUM(debit)-SUM(credit),2) net FROM general_ledger"
        ).fetchone()
    )


def dump_ref(conn, ref: str) -> dict:
    info = {"reference_no": ref, "gl": [], "cash_receipt": None, "customer": None, "journal": None}
    gl = conn.execute(
        """SELECT gl.id, gl.entry_date, gl.account_id, a.code AS account_code, a.name AS account_name,
                  gl.debit, gl.credit, gl.description, gl.reference_type, gl.reference_id,
                  gl.reference_no, gl.voucher_id, gl.created_by, gl.created_at
           FROM general_ledger gl
           LEFT JOIN chart_of_accounts a ON a.id=gl.account_id
           WHERE gl.reference_no=?
           ORDER BY gl.id""",
        (ref,),
    ).fetchall()
    info["gl"] = [rowd(r) for r in gl]
    info["gl_debit"] = round(sum(float(r["debit"] or 0) for r in info["gl"]), 2)
    info["gl_credit"] = round(sum(float(r["credit"] or 0) for r in info["gl"]), 2)
    info["gl_net"] = round(info["gl_debit"] - info["gl_credit"], 2)

    cr = conn.execute("SELECT * FROM cash_receipts WHERE document_no=?", (ref,)).fetchone()
    info["cash_receipt"] = rowd(cr)
    if cr and cr["party_type"] == "customer" and cr["party_id"]:
        info["customer"] = rowd(
            conn.execute(
                "SELECT id, code, name FROM customers WHERE id=?", (cr["party_id"],)
            ).fetchone()
        )

    jv = conn.execute(
        "SELECT * FROM journal_vouchers WHERE document_no=?", (ref,)
    ).fetchone()
    if jv:
        lines = conn.execute(
            """SELECT l.*, a.code AS account_code, a.name AS account_name
               FROM journal_voucher_lines l
               LEFT JOIN chart_of_accounts a ON a.id=l.account_id
               WHERE l.voucher_id=? ORDER BY l.id""",
            (jv["id"],),
        ).fetchall()
        info["journal"] = {"header": rowd(jv), "lines": [rowd(x) for x in lines]}
    return info


def already_has_cash_debit(gl_rows, cash_id: int) -> bool:
    for r in gl_rows:
        if int(r["account_id"]) == int(cash_id) and float(r["debit"] or 0) > 0.05:
            return True
    return False


def repair(conn) -> list:
    actions = []
    cash_id = _acct_id(conn, gl_account_code("cash"))
    if not cash_id:
        raise RuntimeError("Cash GL account not configured")
    cash = rowd(
        conn.execute(
            "SELECT id, code, name FROM chart_of_accounts WHERE id=?", (cash_id,)
        ).fetchone()
    )

    # ---- CR-126928 / CR-126932 ----
    for ref in ("CR-126928", "CR-126932"):
        info = dump_ref(conn, ref)
        cr = info["cash_receipt"]
        if not cr:
            actions.append({"reference_no": ref, "action": "skip", "reason": "cash_receipt missing"})
            continue
        if abs(info["gl_net"]) < 0.05:
            actions.append({"reference_no": ref, "action": "skip", "reason": "already balanced"})
            continue
        if already_has_cash_debit(info["gl"], cash_id):
            actions.append({"reference_no": ref, "action": "skip", "reason": "cash debit already present"})
            continue

        amount = float(cr["amount"])
        label = cr.get("description") or f"Receipt {ref}"
        entry_date = str(cr["receipt_date"])
        ref_type = (info["gl"][0]["reference_type"] if info["gl"] else "customer_receipt")
        # Existing credit posts use reference_id = customer id
        ref_id = info["gl"][0]["reference_id"] if info["gl"] else cr["party_id"]
        user_id = cr.get("created_by")

        post_gl_account_id(
            conn, entry_date, int(cash_id), amount, 0, label,
            ref_type, ref_id, ref, user_id,
        )
        if cr.get("account_id") is None:
            conn.execute(
                "UPDATE cash_receipts SET account_id=?, modified_at=? WHERE id=?",
                (int(cash_id), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(cr["id"])),
            )
        actions.append(
            {
                "reference_no": ref,
                "action": "add_cash_debit",
                "amount": amount,
                "account": cash,
                "entry_date": entry_date,
                "customer": info.get("customer"),
                "narration": label,
            }
        )

    # ---- JVR-126885 ----
    # Incomplete FMYE credit-sale JV. ERP sales invoice 26080116 already posted
    # Dr AR 458,185 / Cr Sales Revenue 458,185. Neutralize orphan Cr SALE A/C.
    ref = "JVR-126885"
    info = dump_ref(conn, ref)
    if abs(info["gl_net"]) < 0.05:
        actions.append({"reference_no": ref, "action": "skip", "reason": "already balanced"})
    elif not info["gl"]:
        actions.append({"reference_no": ref, "action": "skip", "reason": "no GL rows"})
    else:
        credit_line = next(
            (g for g in info["gl"] if float(g["credit"] or 0) > 0.05), None
        )
        if not credit_line:
            actions.append({"reference_no": ref, "action": "skip", "reason": "no credit line found"})
        else:
            amount = float(credit_line["credit"])
            sale_account_id = int(credit_line["account_id"])
            entry_date = str(credit_line["entry_date"])
            label = (
                f"Balance incomplete FMYE {ref} — invoice 26080116 already posted in ERP "
                f"(neutralize orphan credit on SALE A/C)"
            )
            post_gl_account_id(
                conn,
                entry_date,
                sale_account_id,
                amount,
                0,
                label,
                credit_line.get("reference_type") or "fmye_voucher",
                credit_line.get("reference_id") or 0,
                ref,
                credit_line.get("created_by") or 1,
            )
            # Keep journal document lines in sync
            jv = info.get("journal") or {}
            header = jv.get("header")
            if header:
                conn.execute(
                    """INSERT INTO journal_voucher_lines(voucher_id, account_id, description, debit, credit)
                       VALUES (?,?,?,?,0)""",
                    (header["id"], sale_account_id, label, amount),
                )
            sale_acct = rowd(
                conn.execute(
                    "SELECT id, code, name FROM chart_of_accounts WHERE id=?",
                    (sale_account_id,),
                ).fetchone()
            )
            inv = rowd(
                conn.execute(
                    "SELECT id, document_no, customer_id, total, invoice_date, status "
                    "FROM sales_invoices WHERE document_no='26080116'"
                ).fetchone()
            )
            cust = None
            if inv:
                cust = rowd(
                    conn.execute(
                        "SELECT id, code, name FROM customers WHERE id=?",
                        (inv["customer_id"],),
                    ).fetchone()
                )
            actions.append(
                {
                    "reference_no": ref,
                    "action": "neutralize_orphan_sale_credit",
                    "amount": amount,
                    "account": sale_acct,
                    "entry_date": entry_date,
                    "narration": label,
                    "related_sales_invoice": inv,
                    "related_customer": cust,
                    "reason": (
                        "FMYE JV had only Cr SALE A/C; matching ERP sales invoice already "
                        "posted AR/Sales Revenue, so debit same SALE A/C to clear imbalance "
                        "without double-counting receivable."
                    ),
                }
            )
    return actions


def main():
    report = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "before": {},
        "actions": [],
        "after": {},
        "related_invoice_gl": [],
        "ledger_before": None,
        "ledger_after": None,
    }
    with db.get_connection() as conn:
        report["ledger_before"] = ledger_net(conn)
        for ref in REFS:
            report["before"][ref] = dump_ref(conn, ref)

        # Related invoice GL for transparency
        report["related_invoice_gl"] = [
            rowd(r)
            for r in conn.execute(
                """SELECT gl.id, gl.entry_date, a.code AS account_code, a.name AS account_name,
                          gl.debit, gl.credit, gl.reference_type, gl.reference_no, gl.description
                   FROM general_ledger gl
                   JOIN chart_of_accounts a ON a.id=gl.account_id
                   WHERE gl.reference_no='26080116' OR gl.description LIKE '%26080116%'
                   ORDER BY gl.id"""
            ).fetchall()
        ]

        report["actions"] = repair(conn)

        for ref in REFS:
            report["after"][ref] = dump_ref(conn, ref)
        report["ledger_after"] = ledger_net(conn)

    out_path = "reports/gl_imbalance_repair_2026-08-22.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    def print_txn(title, info):
        print(f"\n{'=' * 88}")
        print(f"{title}  |  Dr {info['gl_debit']:,.2f}  Cr {info['gl_credit']:,.2f}  Net {info['gl_net']:,.2f}")
        print("-" * 88)
        if info.get("customer"):
            c = info["customer"]
            print(f"Customer: {c['code']} — {c['name']}")
        if info.get("cash_receipt"):
            cr = info["cash_receipt"]
            print(
                f"Cash receipt: {cr['document_no']}  date={cr['receipt_date']}  "
                f"amount={float(cr['amount']):,.2f}  cash_account_id={cr.get('account_id')}"
            )
        if info.get("journal"):
            h = info["journal"]["header"]
            print(
                f"Journal: {h['document_no']}  date={h['voucher_date']}  "
                f"status={h['status']}  header Dr/Cr={h['total_debit']}/{h['total_credit']}"
            )
        print(f"{'Date':12} {'Account':42} {'Debit':>14} {'Credit':>14}  Narration")
        for g in info["gl"]:
            acct = f"{g['account_code']} {g['account_name']}"[:42]
            print(
                f"{str(g['entry_date'])[:10]:12} {acct:42} "
                f"{float(g['debit'] or 0):14,.2f} {float(g['credit'] or 0):14,.2f}  "
                f"{(g['description'] or '')[:70]}"
            )

    print("LEDGER BEFORE", report["ledger_before"])
    print("\nACTIONS")
    print(json.dumps(report["actions"], indent=2, default=str))

    print("\n\nRELATED INVOICE 26080116 GL (already existed — not modified):")
    for g in report["related_invoice_gl"]:
        print(
            f"  {g['entry_date']} | {g['account_code']} {g['account_name'][:30]:30} | "
            f"Dr {float(g['debit'] or 0):12,.2f} | Cr {float(g['credit'] or 0):12,.2f} | "
            f"{g['reference_type']} {g['reference_no']}"
        )

    for ref in REFS:
        print_txn(f"BEFORE {ref}", report["before"][ref])
        print_txn(f"AFTER  {ref}", report["after"][ref])

    print("\nLEDGER AFTER", report["ledger_after"])
    print("WROTE", out_path)


if __name__ == "__main__":
    main()
