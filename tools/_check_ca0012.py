import sys
sys.path.insert(0, ".")
import database as db

with db.get_connection() as conn:
    adv = conn.execute(
        "SELECT * FROM cash_advances WHERE document_no='CA-0012'"
    ).fetchone()
    print("ADVANCE:", dict(adv) if adv else "not found")

    if adv:
        settles = conn.execute(
            """SELECT s.* FROM cash_advance_settlements s
               WHERE s.advance_id=? ORDER BY s.id""",
            (adv["id"],),
        ).fetchall()
        for s in settles:
            s = dict(s)
            print("\nSETTLEMENT", s["document_no"], s["settle_date"], "bills", s["bills_total"], "cash_ret", s["cash_returned"])
            print("  cash_entry_id", s.get("cash_entry_id"), "cash_doc_no", s.get("cash_doc_no"))
            lines = conn.execute(
                """SELECT l.*, a.code, a.name
                   FROM cash_advance_settlement_lines l
                   JOIN chart_of_accounts a ON a.id=l.expense_account_id
                   WHERE l.settlement_id=?""",
                (s["id"],),
            ).fetchall()
            for ln in lines:
                ln = dict(ln)
                print("  LINE", ln["line_no"], ln["code"], ln["amount"], "cp", ln.get("cash_doc_no"), "entry", ln.get("cash_entry_id"))
                if ln.get("cash_doc_no"):
                    cp = conn.execute(
                        "SELECT * FROM cash_payments WHERE document_no=?", (ln["cash_doc_no"],)
                    ).fetchone()
                    print("    in cash_payments:", bool(cp))
                elif ln.get("cash_entry_id"):
                    cp = conn.execute(
                        "SELECT * FROM cash_payments WHERE id=?", (ln["cash_entry_id"],)
                    ).fetchone()
                    print("    cp by id:", dict(cp) if cp else None)

        gl = conn.execute(
            """SELECT entry_date, account_code, debit, credit, description, entry_source, reference_no
               FROM general_ledger
               WHERE (entry_source='cash_advance_settlement' AND entry_source_id IN (
                   SELECT id FROM cash_advance_settlements WHERE advance_id=?
               )) OR description LIKE '%CA-0012%' OR reference_no LIKE '%CAS%'
               ORDER BY id""",
            (adv["id"],),
        ).fetchall()
        print("\nGL rows (settlement):", len(gl))
        for g in gl[:20]:
            print(" ", dict(g))

    cps = conn.execute(
        """SELECT * FROM cash_payments
           WHERE description LIKE '%CA-0012%' OR description LIKE '%Raza%'
              OR reference_no GLOB 'CAS-*'
           ORDER BY payment_date DESC LIMIT 20"""
    ).fetchall()
    print("\nRelated CPs:", len(cps))
    for c in cps:
        print(" ", c["document_no"], c["payment_date"], c["amount"], c["description"][:60], c["reference_no"])
