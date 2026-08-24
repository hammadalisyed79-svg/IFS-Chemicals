import sys
sys.path.insert(0, ".")
import database as db

with db.get_connection() as conn:
    adv = conn.execute(
        "SELECT * FROM cash_advances WHERE document_no='CA-0014'"
    ).fetchone()
    if adv:
        print("ADVANCE", dict(adv))
    else:
        print("CA-0014 not found")

    for tbl, dcol, doccol in (
        ("cash_payments", "payment_date", "document_no"),
        ("cash_receipts", "receipt_date", "document_no"),
    ):
        rows = conn.execute(
            f"""SELECT id, {doccol}, {dcol}, description, reference_no, amount
                FROM {tbl}
                WHERE reference_no GLOB 'CA-0014*'
                   OR reference_no='CA-0014'
                   OR description LIKE '%CA-0014%'
                   OR description LIKE '%Yahya Butt%'
                ORDER BY id"""
        ).fetchall()
        print(f"\n{tbl}: {len(rows)}")
        for r in rows:
            print(" ", dict(r))

    if adv:
        doc = adv["issue_doc_no"]
        if doc:
            cp = conn.execute(
                "SELECT * FROM cash_payments WHERE document_no=?", (doc,)
            ).fetchone()
            print("\nissue_doc_no", doc, "in cash_payments:", bool(cp))
            if cp:
                print(" ", dict(cp))

    settles = conn.execute(
        """SELECT s.*, l.cash_doc_no, l.amount
           FROM cash_advance_settlements s
           LEFT JOIN cash_advance_settlement_lines l ON l.settlement_id=s.id
           WHERE s.advance_id=(SELECT id FROM cash_advances WHERE document_no='CA-0014')"""
    ).fetchall()
    print("\nsettlements:", len(settles))
    for s in settles:
        print(" ", dict(s))
