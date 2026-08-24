import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database as db

REFS = ("CR-126929", "CP-126909")

with db.get_connection() as conn:
    for ref in REFS:
        print("===", ref, "===")
        for tbl in ("bank_receipts", "bank_payments", "cash_receipts", "cash_payments"):
            rows = conn.execute(
                f"SELECT id, document_no, amount FROM {tbl} WHERE document_no=? OR reference_no=?",
                (ref, ref),
            ).fetchall()
            if rows:
                print(tbl, [dict(r) for r in rows])

    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%audit%'"
        ).fetchall()
    ]
    print("audit tables:", tables)
    for ref in REFS:
        for tbl in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
            qparts, params = [], []
            for c in ("summary", "document_no", "details", "payload", "action", "entity_type"):
                if c in cols:
                    qparts.append(f"{c} LIKE ?")
                    params.append(f"%{ref}%")
            if not qparts:
                continue
            rows = conn.execute(
                f"SELECT * FROM {tbl} WHERE {' OR '.join(qparts)} ORDER BY id DESC LIMIT 8",
                params,
            ).fetchall()
            if rows:
                print(f"\n{tbl} / {ref}:")
                for r in rows:
                    d = dict(r)
                    for k, v in list(d.items()):
                        if isinstance(v, str) and len(v) > 100:
                            d[k] = v[:100] + "..."
                    print(d)

    # customer for CR-126929
    gl = conn.execute(
        "SELECT * FROM general_ledger WHERE reference_no='CR-126929'"
    ).fetchall()
    print("\nCustomer id from GL:", gl[1]["reference_id"] if len(gl) > 1 else "?")
    cust = conn.execute(
        "SELECT id, code, name, current_balance FROM customers WHERE id=679"
    ).fetchone()
    print("Customer 679:", dict(cust) if cust else None)
