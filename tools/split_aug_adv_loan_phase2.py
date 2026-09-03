"""Implement remaining Aug-26 advances + residual ending ADV -> loans.

- Missing salary advances dated 2026-08-26 (carve from Access ending ADV)
- Residual Access ending ADV -> loans with 3 installments
- Ledger ADV+LOAN outstanding unchanged per employee
- No Cash Book / GL posts
"""
from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pyodbc

from database import DB_PATH, get_connection, ensure_document_no
import db_hr as hr

ADV_DATE = "2026-08-26"
INSTALLMENTS = 3
UID = 1
MARKER_ADV = "Salary advance Aug 26 [ACC:"
MARKER_LOAN_SPLIT = "Loan Access split [ACC:"
MARKER_LOAN_RES = "Loan from Access ending [EID:"

# Extra advances not in the first 20-31 batch (user confirmed + Gulfam)
EXTRA_ADV_PAYMENTS = [
    # (date, amount, name_substr)
    ("2026-08-08", 5000.0, "rana zahid"),
    ("2026-08-09", 5000.0, "gulfam(bottle"),  # Gulfam Bottle Section
    ("2026-08-11", 12000.0, "abdul hameed(s.k)"),
    ("2026-08-13", 6000.0, "shabab"),
    ("2026-08-16", 1300.0, "hafiz arfan"),
    ("2026-08-16", 8000.0, "sufyan tabassum"),
    ("2026-08-16", 2000.0, "muhammad nadeem"),
    ("2026-08-19", 50000.0, "azeem tariq"),
]

# Explicit loans (already created in first split — skip if marker exists)
EXPLICIT_LOANS = [
    ("2026-08-13", 8000.0, "aamir nazir"),
    ("2026-08-16", 25000.0, "fazal abbas"),
    ("2026-08-20", 400000.0, "nawaz gulzar"),
    # Access remark Loan — include
    ("2026-08-11", 60000.0, "akhtar abbas"),
]

SALARY_SETTLE = [
    ("2026-08-25", 5064.0, "asad ali"),
]

ACC = Path(r"C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb")


def _fp(aid, d, paid):
    return f"{aid}:{d}:{paid:.2f}"


def _match(d, paid, name, rules):
    nm = (name or "").lower()
    for rd, amt, hint in rules:
        if d == rd and abs(float(paid) - amt) < 0.01 and hint in nm:
            return True
    return False


def _ending_avail(conn, eid):
    r = conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0)
           FROM employee_advances
           WHERE employee_id=? AND reason LIKE '%Access ending balance%'
             AND status='issued'""",
        (eid,),
    ).fetchone()
    return round(float(r[0] or 0), 2)


def _carve_ending(conn, eid, amount, label):
    remain = round(float(amount), 2)
    carved = 0.0
    rows = conn.execute(
        """SELECT id, amount, outstanding_amount
           FROM employee_advances
           WHERE employee_id=? AND reason LIKE '%Access ending balance%'
             AND status='issued' ORDER BY id""",
        (eid,),
    ).fetchall()
    for row in rows:
        if remain <= 0.01:
            break
        r = dict(row)
        out = float(r["outstanding_amount"] or 0)
        amt = float(r["amount"] or 0)
        if out <= 0.01:
            continue
        take = min(remain, out)
        new_out = round(out - take, 2)
        new_amt = round(max(0.0, amt - take), 2)
        status = "closed" if new_out <= 0.01 else "issued"
        if status == "closed":
            new_out = 0.0
        conn.execute(
            """UPDATE employee_advances
               SET amount=?, outstanding_amount=?, status=?, monthly_recovery=?,
                   modified_by=?, modified_at=? WHERE id=?""",
            (
                new_amt, new_out, status,
                new_out if status == "issued" else 0.0,
                UID, hr.now(), r["id"],
            ),
        )
        remain = round(remain - take, 2)
        carved = round(carved + take, 2)
    if remain > 0.01:
        raise ValueError(f"Carve short {remain:,.2f} for {label} (eid={eid})")
    return carved


def _adv_exists(conn, fp):
    return conn.execute(
        "SELECT 1 FROM employee_advances WHERE reason LIKE ? LIMIT 1",
        (f"%[ACC:{fp}]%",),
    ).fetchone() is not None


def _loan_exists(conn, fp):
    return conn.execute(
        "SELECT 1 FROM employee_loans WHERE reason LIKE ? LIMIT 1",
        (f"%[ACC:{fp}]%",),
    ).fetchone() is not None


def _create_adv(conn, eid, paid, fp, pay_date, remark):
    reason = f"{MARKER_ADV}{fp}] paid {pay_date}; {(remark or '')[:60]}"
    doc = ensure_document_no("ADV", None, conn)
    cur = conn.execute(
        """INSERT INTO employee_advances(
               document_no, employee_id, request_date, amount, reason,
               recovery_months, monthly_recovery, outstanding_amount, recovered_amount,
               status, approved_by, approved_at, issued_by, issued_at,
               created_by, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc, eid, ADV_DATE, paid, reason,
            1, paid, paid, 0.0,
            "issued", UID, hr.now(), UID, hr.now(), UID, hr.now(),
        ),
    )
    aid = cur.lastrowid
    due = (datetime.strptime(ADV_DATE, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO advance_recovery_schedule(advance_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
        (aid, 1, due, paid),
    )
    _carve_ending(conn, eid, paid, f"ADV {doc}")
    return doc


def _create_loan(conn, eid, paid, issue_date, reason, marker_fp=None):
    monthly = round(paid / INSTALLMENTS, 2)
    doc = ensure_document_no("LON", None, conn)
    cur = conn.execute(
        """INSERT INTO employee_loans(
               document_no, employee_id, issue_date, amount, installments,
               monthly_installment, outstanding_amount, recovered_amount,
               reason, status, approved_by, approved_at, issued_by, issued_at,
               created_by, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc, eid, issue_date, paid, INSTALLMENTS, monthly,
            paid, 0.0, reason, "issued",
            UID, hr.now(), UID, hr.now(), UID, hr.now(),
        ),
    )
    lid = cur.lastrowid
    base = datetime.strptime(issue_date, "%Y-%m-%d")
    parts = [monthly] * INSTALLMENTS
    parts[-1] = round(paid - monthly * (INSTALLMENTS - 1), 2)
    for i, part in enumerate(parts, start=1):
        due = (base + timedelta(days=30 * i)).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO loan_installments(loan_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
            (lid, i, due, part),
        )
    return doc, lid


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = Path("backups") / f"pre_aug_adv_loan_phase2_{ts}.db"
    Path("backups").mkdir(exist_ok=True)
    shutil.copy2(DB_PATH, backup)
    print("Backup:", backup)

    cur = pyodbc.connect(
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(ACC) + ";"
    ).cursor()

    access_rows = cur.execute(
        """SELECT ID, Dated, PaidAmt, Remark FROM Balance
           WHERE Dated >= #2026-08-01# AND Dated <= #2026-08-31# AND PaidAmt <> 0
           ORDER BY Dated, ID"""
    ).fetchall()

    with get_connection() as conn:
        amap = {int(a): int(e) for a, e in conn.execute(
            "SELECT access_eid, employee_id FROM payroll_access_map"
        )}
        emps = {
            int(r[0]): {"id": int(r[0]), "code": r[1], "name": r[2]}
            for r in conn.execute("SELECT id, code, full_name FROM employees")
        }

        def emp_for(aid):
            eid = amap.get(int(aid))
            return emps.get(eid) if eid else None

        # Snapshot totals before
        before_by_eid = {}
        for eid in emps:
            a = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0])
            L = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_loans
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0])
            before_by_eid[eid] = round(a + L, 2)

        created_adv = created_loan = skipped = 0
        skipped_rows = []

        # Classify Aug payments we care about for NEW docs
        to_adv = []
        to_loan = []
        for r in access_rows:
            aid = int(r[0])
            d = r[1].strftime("%Y-%m-%d")
            paid = round(float(r[2] or 0), 2)
            rem = (r[3] or "").strip()
            e = emp_for(aid)
            if not e:
                continue
            name = e["name"]
            # salary settlement — never advance/loan doc
            if _match(d, paid, name, SALARY_SETTLE):
                continue
            if _match(d, paid, name, EXPLICIT_LOANS):
                to_loan.append((aid, d, paid, rem, e))
                continue
            if _match(d, paid, name, EXTRA_ADV_PAYMENTS):
                to_adv.append((aid, d, paid, rem, e))
                continue
            # Aug 20-31 default advance (already mostly done)
            if d >= "2026-08-20" and d <= "2026-08-31":
                to_adv.append((aid, d, paid, rem, e))
                continue
            # Adv August 26 remark on other dates
            if "adv august 26" in rem.lower():
                to_adv.append((aid, d, paid, rem, e))

        # Special: Gulfam bottle — name match "gulfam(bottle" 
        # EXTRA already has it; also catch if name is Gulfam(Bottle Section)
        # Ensure Gulfam 09 Aug 5000 in list
        for r in access_rows:
            aid = int(r[0])
            d = r[1].strftime("%Y-%m-%d")
            paid = round(float(r[2] or 0), 2)
            rem = (r[3] or "").strip()
            e = emp_for(aid)
            if not e:
                continue
            if (
                d == "2026-08-09"
                and abs(paid - 5000) < 0.01
                and "gulfam" in e["name"].lower()
                and "bottle" in e["name"].lower()
            ):
                item = (aid, d, paid, rem, e)
                if item not in to_adv:
                    to_adv.append(item)

        print(f"Candidates ADV={len(to_adv)} LOAN={len(to_loan)}")

        # Create missing loans first (Akhtar etc.)
        for aid, d, paid, rem, e in to_loan:
            fp = _fp(aid, d, paid)
            if _loan_exists(conn, fp):
                skipped += 1
                continue
            avail = _ending_avail(conn, e["id"])
            if avail + 0.01 < paid:
                skipped_rows.append((e["code"], d, paid, "loan", avail, rem))
                skipped += 1
                continue
            reason = f"{MARKER_LOAN_SPLIT}{fp}] {rem[:80]}"
            doc, _lid = _create_loan(conn, e["id"], paid, d, reason)
            _carve_ending(conn, e["id"], paid, f"LOAN {doc}")
            created_loan += 1
            print(f"LOAN {doc} {e['code']} {e['name'][:28]} {paid:,.2f} ({d})")

        # Create missing advances
        for aid, d, paid, rem, e in sorted(to_adv, key=lambda x: (x[1], x[0])):
            fp = _fp(aid, d, paid)
            if _adv_exists(conn, fp):
                skipped += 1
                continue
            avail = _ending_avail(conn, e["id"])
            if avail + 0.01 < paid:
                skipped_rows.append((e["code"], d, paid, "advance", avail, rem))
                skipped += 1
                continue
            doc = _create_adv(conn, e["id"], paid, fp, d, rem)
            created_adv += 1
            print(f"ADV  {doc} {e['code']} {e['name'][:28]} {paid:,.2f} (paid {d})")

        print(f"\nCreated ADV={created_adv} LOAN={created_loan} skipped_existing_or_short={skipped}")
        if skipped_rows:
            print("Skipped (short / already cleared):")
            for s in skipped_rows:
                print(f"  {s}")

        # Convert residual Access ending ADV -> loans
        residual_rows = conn.execute(
            """SELECT id, employee_id, document_no, outstanding_amount, request_date
               FROM employee_advances
               WHERE reason LIKE '%Access ending balance%'
                 AND status='issued' AND outstanding_amount > 0.01
               ORDER BY employee_id, id"""
        ).fetchall()

        converted = 0
        for row in residual_rows:
            r = dict(row)
            eid = int(r["employee_id"])
            amt = round(float(r["outstanding_amount"]), 2)
            issue_date = str(r["request_date"] or ADV_DATE)[:10]
            # Close ending ADV to zero first (same amount becomes loan)
            conn.execute(
                """UPDATE employee_advances
                   SET amount=0, outstanding_amount=0, status='closed', monthly_recovery=0,
                       modified_by=?, modified_at=? WHERE id=?""",
                (UID, hr.now(), r["id"]),
            )
            reason = (
                f"{MARKER_LOAN_RES}{eid}] from {r['document_no']} "
                f"Access ending residual {amt:.2f}"
            )
            doc, _lid = _create_loan(conn, eid, amt, issue_date, reason)
            converted += 1
            emp = emps[eid]
            print(f"RES->LOAN {doc} {emp['code']} {emp['name'][:28]} {amt:,.2f} (was {r['document_no']})")

        print(f"\nConverted residual ending ADV -> LOAN: {converted}")

        # Verify totals
        mismatches = []
        for eid, b in before_by_eid.items():
            a = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0])
            L = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),2) FROM employee_loans
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0])
            # Fix typo - ROUND not in SQL that way for COALESCE SUM
            after = round(a + L, 2)
            if abs(after - b) > 0.05:
                mismatches.append((emps[eid]["code"], b, after, a, L))

        # Re-query properly
        mismatches = []
        for eid, b in before_by_eid.items():
            a = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0] or 0)
            L = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_loans
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0] or 0)
            after = round(a + L, 2)
            if abs(after - b) > 0.05:
                mismatches.append((emps[eid]["code"], emps[eid]["name"], b, after, a, L))

        tot_adv = conn.execute(
            "SELECT COUNT(*), ROUND(SUM(outstanding_amount),2) FROM employee_advances WHERE status='issued'"
        ).fetchone()
        tot_loan = conn.execute(
            "SELECT COUNT(*), ROUND(SUM(outstanding_amount),2) FROM employee_loans WHERE status='issued'"
        ).fetchone()
        ending_left = conn.execute(
            """SELECT COUNT(*), ROUND(SUM(outstanding_amount),2) FROM employee_advances
               WHERE reason LIKE '%Access ending%' AND status='issued'"""
        ).fetchone()

        print("\n=== TOTALS ===")
        print("Issued ADV:", tot_adv)
        print("Issued LOAN:", tot_loan)
        print("Ending ADV left:", ending_left)

        # Spot checks
        for code in ("EMP-A0434", "EMP-A0548", "EMP-A0435", "EMP-A0366", "EMP-A0395",
                     "EMP-A0516", "EMP-A0309", "EMP-A0041"):
            e = conn.execute(
                "SELECT id, code, full_name FROM employees WHERE code=?", (code,)
            ).fetchone()
            if not e:
                continue
            eid = e[0]
            a = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_advances
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0] or 0)
            L = float(conn.execute(
                """SELECT COALESCE(SUM(outstanding_amount),0) FROM employee_loans
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0] or 0)
            print(f"  {code} {e[2][:28]} ADV={a:,.2f} LOAN={L:,.2f} TOT={a+L:,.2f} was={before_by_eid[eid]:,.2f}")

        if mismatches:
            print("\nMISMATCHES:")
            for m in mismatches[:20]:
                print(m)
            raise SystemExit("Verification failed — restore " + str(backup))

        print("\nOK: ADV+LOAN outstanding unchanged for all employees.")


if __name__ == "__main__":
    main()
