"""Settle GP/GK unpaid Jul-2026 via Hafiz Zaman ledger adjustment; inactivate both."""
import shutil
from datetime import datetime
from pathlib import Path

from database import DB_PATH, get_connection
import db_hr as hr

BACKUP = Path("backups") / f"pre_gp_gk_settle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
Path("backups").mkdir(exist_ok=True)
shutil.copy2(DB_PATH, BACKUP)
print("Backup", BACKUP, "from", DB_PATH)

NOTE = "Settled via Hafiz Zaman Contractor ledger — not employees (G.P / G.K)"
LINES = [
    (5776, "EMP-A0242 Abdul Rehman(G.P)"),
    (5642, "EMP-A0539 Nafees Nawaz(G.K)"),
]
EMP_IDS = [223, 499]

for lid, label in LINES:
    try:
        res = hr.settle_payroll_line_adjustment(lid, user_id=1, note=NOTE, payment_date="2026-07-31")
        print("SETTLED", label, res)
    except Exception as e:
        print("SKIP/ERR", label, e)

with get_connection() as conn:
    for eid in EMP_IDS:
        conn.execute(
            """UPDATE employees SET is_active=0, employment_status='inactive',
               modified_by=1, modified_at=? WHERE id=?""",
            (hr.now(), eid),
        )
        e = conn.execute(
            "SELECT code, full_name, is_active, employment_status FROM employees WHERE id=?",
            (eid,),
        ).fetchone()
        print("INACTIVE", dict(e))

    for r in conn.execute(
        """SELECT e.code, e.full_name, pl.paid_status, pl.paid_amount, pl.net_salary,
                  pl.payment_mode, pl.payment_document_no
           FROM payroll_lines pl JOIN employees e ON e.id=pl.employee_id
           WHERE pl.id IN (5776, 5642)"""
    ).fetchall():
        print("VERIFY", dict(r))

    left = conn.execute(
        """SELECT COUNT(*) FROM payroll_lines
           WHERE payroll_id=55 AND COALESCE(paid_status,'unpaid')!='paid'"""
    ).fetchone()[0]
    print("PAY-0055 still unpaid lines:", left)
