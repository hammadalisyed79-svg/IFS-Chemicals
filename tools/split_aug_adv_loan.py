"""Split Access Aug payments into salary advances (26 Aug) and loans.

Rules (user confirmed):
- All salary advances dated 2026-08-26
- Aug 20-31 PaidAmt = salary advance EXCEPT Nawaz Gulzar 400,000 on 20 Aug = loan
- Aug 13 Aamir Nazir 8,000 = loan; other Aug 13/16 Adv payments = salary advance
- Aug 16 Fazal Abbas Shah 25,000 = loan
- Loans: 3 installments (editable later)
- No Cash Book / GL posts — carve from Access ending-balance advances so ledger total unchanged
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
MARKER_LOAN = "Loan Access split [ACC:"

LOAN_RULES = [
    # (date, amount, name_substr)
    ("2026-08-20", 400000.0, "nawaz gulzar"),
    ("2026-08-16", 25000.0, "fazal abbas"),
    ("2026-08-13", 8000.0, "aamir nazir"),
]

ACC = Path(r"C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb")


def _fp(aid, d, paid):
    return f"{aid}:{d}:{paid:.2f}"


def _is_loan(d, paid, name):
    nm = (name or "").lower()
    for rd, amt, hint in LOAN_RULES:
        if d == rd and abs(float(paid) - amt) < 0.01 and hint in nm:
            return True
    return False


def _ending_adv_available(conn, eid):
    row = conn.execute(
        """SELECT COALESCE(SUM(outstanding_amount),0)
           FROM employee_advances
           WHERE employee_id=? AND reason LIKE '%Access ending balance%'
             AND status='issued'""",
        (eid,),
    ).fetchone()
    return round(float(row[0] or 0), 2)


def _carve_ending_adv(conn, eid, amount, label, allow_partial=False):
    """Reduce Access ending-balance advance(s) by amount. Returns carved total."""
    remain = round(float(amount), 2)
    carved = 0.0
    rows = conn.execute(
        """SELECT id, amount, outstanding_amount, recovered_amount, status
           FROM employee_advances
           WHERE employee_id=? AND reason LIKE '%Access ending balance%'
             AND status='issued'
           ORDER BY id""",
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
        if take <= 0.01:
            continue
        new_out = round(out - take, 2)
        new_amt = round(max(0.0, amt - take), 2)
        new_status = "closed" if new_out <= 0.01 else "issued"
        if new_status == "closed":
            new_out = 0.0
        conn.execute(
            """UPDATE employee_advances
               SET amount=?, outstanding_amount=?, status=?,
                   monthly_recovery=?, modified_by=?, modified_at=?
               WHERE id=?""",
            (
                new_amt,
                new_out,
                new_status,
                new_out if new_status == "issued" else 0.0,
                UID,
                hr.now(),
                r["id"],
            ),
        )
        remain = round(remain - take, 2)
        carved = round(carved + take, 2)
    if remain > 0.01 and not allow_partial:
        raise ValueError(
            f"Cannot carve {amount:,.2f} from Access ending advance for employee_id={eid} "
            f"({label}); short by {remain:,.2f}"
        )
    return carved


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = Path("backups") / f"pre_aug_adv_loan_split_{ts}.db"
    Path("backups").mkdir(exist_ok=True)
    shutil.copy2(DB_PATH, backup)
    print("Backup:", backup)

    cur = pyodbc.connect(
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + str(ACC) + ";"
    ).cursor()

    access_rows = cur.execute(
        """SELECT ID, Dated, PaidAmt, Remark
           FROM Balance
           WHERE (Dated=#2026-08-13# OR Dated=#2026-08-16#
                  OR (Dated>=#2026-08-20# AND Dated<=#2026-08-31#))
             AND PaidAmt <> 0
           ORDER BY Dated, ID"""
    ).fetchall()

    with get_connection() as conn:
        amap = {int(a): int(e) for a, e in conn.execute(
            "SELECT access_eid, employee_id FROM payroll_access_map"
        )}
        emps = {
            int(r[0]): {"id": int(r[0]), "code": r[1], "full_name": r[2]}
            for r in conn.execute("SELECT id, code, full_name FROM employees")
        }

        # Idempotency
        existing_adv = conn.execute(
            "SELECT COUNT(*) FROM employee_advances WHERE reason LIKE ?",
            (MARKER_ADV + "%",),
        ).fetchone()[0]
        existing_loan = conn.execute(
            "SELECT COUNT(*) FROM employee_loans WHERE reason LIKE ?",
            (MARKER_LOAN + "%",),
        ).fetchone()[0]
        if existing_adv or existing_loan:
            raise SystemExit(
                f"Already split? found {existing_adv} advances and {existing_loan} loans "
                f"with Access split markers. Abort."
            )

        classified = []
        for r in access_rows:
            aid = int(r[0])
            d = r[1].strftime("%Y-%m-%d")
            paid = round(float(r[2] or 0), 2)
            remark = (r[3] or "").strip()
            eid = amap.get(aid)
            if not eid:
                print(f"SKIP unmapped Access#{aid} {d} {paid}")
                continue
            emp = emps[eid]
            kind = "loan" if _is_loan(d, paid, emp["full_name"]) else "advance"
            classified.append({
                "aid": aid, "date": d, "paid": paid, "remark": remark,
                "eid": eid, "code": emp["code"], "name": emp["full_name"],
                "kind": kind, "fp": _fp(aid, d, paid),
            })

        loans = [x for x in classified if x["kind"] == "loan"]
        advs = [x for x in classified if x["kind"] == "advance"]
        print(f"Classified: loans={len(loans)} amt={sum(x['paid'] for x in loans):,.2f}")
        print(f"            advances={len(advs)} amt={sum(x['paid'] for x in advs):,.2f}")

        # Snapshot ending ADV+LOAN before
        before = {}
        for eid in {x["eid"] for x in classified}:
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
            before[eid] = round(a + L, 2)

        created_loans = created_advs = 0
        skipped = []

        # --- Loans (must fully carve) ---
        for x in loans:
            reason = f"{MARKER_LOAN}{x['fp']}] {x['remark'][:80]}"
            monthly = round(x["paid"] / INSTALLMENTS, 2)
            doc = ensure_document_no("LON", None, conn)
            cur_ins = conn.execute(
                """INSERT INTO employee_loans(
                       document_no, employee_id, issue_date, amount, installments,
                       monthly_installment, outstanding_amount, recovered_amount,
                       reason, status, approved_by, approved_at, issued_by, issued_at,
                       created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, x["eid"], x["date"], x["paid"], INSTALLMENTS, monthly,
                    x["paid"], 0.0, reason, "issued",
                    UID, hr.now(), UID, hr.now(), UID, hr.now(),
                ),
            )
            lid = cur_ins.lastrowid
            base = datetime.strptime(x["date"], "%Y-%m-%d")
            parts = [monthly] * INSTALLMENTS
            parts[-1] = round(x["paid"] - monthly * (INSTALLMENTS - 1), 2)
            for i, part in enumerate(parts, start=1):
                due = (base + timedelta(days=30 * i)).strftime("%Y-%m-%d")
                conn.execute(
                    "INSERT INTO loan_installments(loan_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                    (lid, i, due, part),
                )
            _carve_ending_adv(conn, x["eid"], x["paid"], f"loan {x['code']}", allow_partial=False)
            created_loans += 1
            print(f"LOAN {doc} {x['code']} {x['name'][:28]} {x['paid']:,.2f} ({x['date']})")

        # --- Advances (all dated Aug 26); skip if Access ending ADV already cleared ---
        advs_sorted = sorted(advs, key=lambda x: (x["date"], x["aid"]))
        for x in advs_sorted:
            avail = _ending_adv_available(conn, x["eid"])
            if avail + 0.01 < x["paid"]:
                skipped.append({
                    **x,
                    "avail": avail,
                    "why": "Access ending ADV outstanding too low (already cleared in ledger)",
                })
                continue
            reason = f"{MARKER_ADV}{x['fp']}] paid {x['date']}; {x['remark'][:60]}"
            monthly = x["paid"]
            doc = ensure_document_no("ADV", None, conn)
            cur_ins = conn.execute(
                """INSERT INTO employee_advances(
                       document_no, employee_id, request_date, amount, reason,
                       recovery_months, monthly_recovery, outstanding_amount, recovered_amount,
                       status, approved_by, approved_at, issued_by, issued_at,
                       created_by, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc, x["eid"], ADV_DATE, x["paid"], reason,
                    1, monthly, x["paid"], 0.0,
                    "issued", UID, hr.now(), UID, hr.now(), UID, hr.now(),
                ),
            )
            aid_new = cur_ins.lastrowid
            due = (datetime.strptime(ADV_DATE, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT INTO advance_recovery_schedule(advance_id,installment_no,due_date,amount) VALUES(?,?,?,?)",
                (aid_new, 1, due, monthly),
            )
            _carve_ending_adv(conn, x["eid"], x["paid"], f"advance {x['code']}", allow_partial=False)
            created_advs += 1

        print(f"Created loans={created_loans} advances={created_advs} skipped={len(skipped)}")
        if skipped:
            print("Skipped (ledger already clear — no double-count):")
            for s in skipped:
                print(
                    f"  {s['code']} {s['name'][:28]} {s['date']} {s['paid']:,.2f} "
                    f"avail={s['avail']:,.2f} | {s['remark'][:50]}"
                )

        # Verify ledger totals unchanged per employee
        mismatches = []
        for eid, b in before.items():
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
            after = round(a + L, 2)
            if abs(after - b) > 0.02:
                emp = emps[eid]
                mismatches.append((emp["code"], emp["full_name"], b, after, a, L))

        # Global Access ending check for touched employees
        print("\nLoan docs:")
        for r in conn.execute(
            """SELECT document_no, e.code, e.full_name, l.amount, l.installments, l.issue_date
               FROM employee_loans l JOIN employees e ON e.id=l.employee_id
               WHERE l.reason LIKE ? ORDER BY l.issue_date""",
            (MARKER_LOAN + "%",),
        ):
            print(" ", dict(r))

        print(f"\nAdvance docs created: {created_advs}")
        sample = conn.execute(
            """SELECT COUNT(*), ROUND(SUM(amount),2) FROM employee_advances
               WHERE reason LIKE ?""",
            (MARKER_ADV + "%",),
        ).fetchone()
        print(" Advance total:", sample)

        if mismatches:
            print("\nMISMATCHES (ADV+LOAN outstanding changed):")
            for m in mismatches:
                print(m)
            raise SystemExit("Aborted verification failed — restore backup")

        print("\nOK: ADV+LOAN outstanding unchanged for all touched employees.")
        # Spot-check three loan targets
        for code in ("EMP-A0516", "EMP-A0034", "EMP-A0041"):
            e = conn.execute(
                "SELECT id, code, full_name FROM employees WHERE code=?", (code,)
            ).fetchone()
            eid = e[0]
            adv_o = conn.execute(
                """SELECT ROUND(SUM(outstanding_amount),2) FROM employee_advances
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0]
            loan_o = conn.execute(
                """SELECT ROUND(SUM(outstanding_amount),2) FROM employee_loans
                   WHERE employee_id=? AND status='issued'""",
                (eid,),
            ).fetchone()[0]
            print(
                f"  {code} {e[2][:28]} ADV_out={adv_o} LOAN_out={loan_o} "
                f"TOTAL={float(adv_o or 0)+float(loan_o or 0):,.2f} (was {before[eid]:,.2f})"
            )


if __name__ == "__main__":
    main()
