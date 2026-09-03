"""Add Maqsood Shah Aug-29 Rs 21,095 so Aug-26 ADV issued = Rs 2,312,395."""
from datetime import datetime, timedelta
from pathlib import Path
import shutil

from database import DB_PATH, get_connection, ensure_document_no
import db_hr as hr

UID = 1
ADV_DATE = "2026-08-26"
TARGET = 2_312_395.0
# Only the net gap to target (keeps Gulfam as advance; Aug-20 5k stays offset by Gulfam +5k in the bridge)
AID, D, PAID, REM = 411, "2026-08-29", 21_095.0, "Chq. , Salary August 26 to"


def main():
    backup = Path("backups") / f"pre_maqsood_21095_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    Path("backups").mkdir(exist_ok=True)
    shutil.copy2(DB_PATH, backup)
    print("Backup:", backup)

    with get_connection() as conn:
        before = float(conn.execute(
            """SELECT ROUND(SUM(amount),2) FROM employee_advances
               WHERE reason LIKE 'Salary advance Aug 26 [ACC:%'"""
        ).fetchone()[0] or 0)
        print("Before:", before)

        eid = conn.execute("SELECT id FROM employees WHERE code='EMP-A0411'").fetchone()[0]
        fp = f"{AID}:{D}:{PAID:.2f}"
        exists = conn.execute(
            "SELECT document_no FROM employee_advances WHERE reason LIKE ?",
            (f"%[ACC:{fp}]%",),
        ).fetchone()
        if exists:
            print("Already exists", exists[0])
        else:
            reason = f"Salary advance Aug 26 [ACC:{fp}] paid {D}; {REM[:60]}"
            doc = ensure_document_no("ADV", None, conn)
            conn.execute(
                """INSERT INTO employee_advances(
                       document_no, employee_id, request_date, amount, reason,
                       recovery_months, monthly_recovery, outstanding_amount, recovered_amount,
                       status, approved_by, approved_at, issued_by, issued_at,
                       created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, eid, ADV_DATE, PAID, reason,
                    1, PAID, PAID, 0.0,
                    "issued", UID, hr.now(), UID, hr.now(), UID, hr.now(),
                ),
            )
            rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            due = (datetime.strptime(ADV_DATE, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO advance_recovery_schedule(advance_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                (rowid, 1, due, PAID),
            )
            print(f"Created {doc} EMP-A0411 Maqsood Shah {PAID:,.2f}")

        # Also add Aug-20 5,000 if we need both for Access completeness — check target first
        after = float(conn.execute(
            """SELECT ROUND(SUM(amount),2) FROM employee_advances
               WHERE reason LIKE 'Salary advance Aug 26 [ACC:%'"""
        ).fetchone()[0] or 0)
        print("After Aug29 only:", after, "target", TARGET)

        # Access full ADVANCE also had Aug20 5k; adding it would overshoot unless we skip Gulfam.
        # User target 2312395 = before + 21095. Done.
        if abs(after - TARGET) > 0.01:
            raise SystemExit(f"Expected {TARGET}, got {after}. Restore {backup}")
        print("OK: Aug-26 salary advance issued =", after)

        # Note: Maqsood Aug20 5k still not issued (offset by Gulfam 5k vs Access-only total)
        n = conn.execute(
            """SELECT COUNT(*) FROM employee_advances
               WHERE reason LIKE 'Salary advance Aug 26 [ACC:%'"""
        ).fetchone()[0]
        print("Count:", n)


if __name__ == "__main__":
    main()
