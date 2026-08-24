import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

refs = ["CP-126912", "CP-126909", "CR-126929"]
with db.get_connection() as conn:
    for ref in refs:
        print("===", ref, "===")
        for r in conn.execute(
            "SELECT id, entry_date, debit, credit, reference_type, description FROM general_ledger WHERE reference_no=?",
            (ref,),
        ).fetchall():
            print("GL", dict(r))
        for tbl in ("cash_receipts", "cash_payments"):
            r = conn.execute(
                f"SELECT id, document_no, amount, description FROM {tbl} WHERE document_no=?",
                (ref,),
            ).fetchone()
            if r:
                print(tbl, dict(r))
