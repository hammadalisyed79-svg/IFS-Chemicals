"""Smoke-test cash advance flow: issue shadow, settle bill, cash return."""
import sys
sys.path.insert(0, ".")

import database as db
from db_v3 import issue_cash_advance, settle_cash_advance

TEST_DATE = "2099-01-15"
user_id = 1

with db.get_connection() as conn:
    before_cp = conn.execute(
        "SELECT COUNT(*) FROM cash_payments WHERE payment_date=?", (TEST_DATE,)
    ).fetchone()[0]
    before_cr = conn.execute(
        "SELECT COUNT(*) FROM cash_receipts WHERE receipt_date=?", (TEST_DATE,)
    ).fetchone()[0]

issued = issue_cash_advance(
    TEST_DATE, 1000.0, "Test Rider",
    purpose="flow test", user_id=user_id,
)
print("issued", issued["document_no"], "out", issued["outstanding_amount"])

with db.get_connection() as conn:
    after_issue_cp = conn.execute(
        "SELECT COUNT(*) FROM cash_payments WHERE payment_date=?", (TEST_DATE,)
    ).fetchone()[0]
assert after_issue_cp == before_cp, "issue must not create cash payment"

inv = db.resolve_cash_advance_account_id()
with db.get_connection() as conn:
    exp = conn.execute(
        """SELECT id FROM chart_of_accounts
           WHERE is_active=1 AND id!=?
             AND code NOT IN ('000000','1000','100000')
             AND UPPER(name) NOT LIKE '%CASH%'
           LIMIT 1""",
        (inv,),
    ).fetchone()
    exp_id = exp[0]

settled = settle_cash_advance(
    issued["id"], TEST_DATE,
    [{"expense_account_id": exp_id, "narration": "test bill", "amount": 600.0}],
    cash_returned=200.0,
    user_id=user_id,
)
print("settled", settled["document_no"], "out", settled["outstanding_amount"], "cp", settled.get("cash_doc_nos"))

with db.get_connection() as conn:
    after_settle_cp = conn.execute(
        "SELECT COUNT(*) FROM cash_payments WHERE payment_date=?", (TEST_DATE,)
    ).fetchone()[0]
    after_settle_cr = conn.execute(
        "SELECT COUNT(*) FROM cash_receipts WHERE receipt_date=?", (TEST_DATE,)
    ).fetchone()[0]
assert after_settle_cp == before_cp + 1, "settle bill must create one CP"
assert after_settle_cr == before_cr, "cash return must not create CR"

# cleanup
with db.get_connection() as conn:
    adv_id = issued["id"]
    settle_id = settled["id"]
    for cp in settled.get("cash_doc_nos") or []:
        conn.execute("DELETE FROM cash_payments WHERE document_no=?", (cp,))
    conn.execute("DELETE FROM cash_advance_settlement_lines WHERE settlement_id=?", (settle_id,))
    conn.execute("DELETE FROM cash_advance_settlements WHERE id=?", (settle_id,))
    conn.execute("DELETE FROM cash_advances WHERE id=?", (adv_id,))
    conn.execute(
        "DELETE FROM general_ledger WHERE entry_source IN ('cash_advance','cash_advance_settlement') "
        "AND entry_source_id IN (?, ?)",
        (adv_id, settle_id),
    )
    conn.commit()

print("OK")
