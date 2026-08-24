"""Import all FMYE Voucher lines (debit + contra credit) for 2026.

Writes:
  - general_ledger          (every voucher line)
  - cash_receipts / cash_payments   (CRV / CPV)
  - bank_receipts / bank_payments   (BRV / BPV)
  - journal_vouchers + lines        (JVR, excluding SL/PU/SR/PR invoice mirrors optional)

Usage:
  python import_fmye_vouchers_gl.py              # preview
  python import_fmye_vouchers_gl.py --apply      # import year 2026
  python import_fmye_vouchers_gl.py --apply --years 2026
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import database as db
from import_fmye_from_dat import EXPORT_DIR, FMYEExport, _d, _f, _in_years

CASH_CODES = {"000000"}
# Primary bank + any Chart AccountType B / name containing BANK (resolved at runtime)
BANK_TYPE = "B"


def _uid() -> int:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)='admin' AND is_active=1"
        ).fetchone()
    if not row:
        raise SystemExit("No admin user")
    return int(row[0])


def _acct_map(conn) -> dict[str, int]:
    return {
        (r["code"] or "").strip(): r["id"]
        for r in conn.execute("SELECT id, code FROM chart_of_accounts")
    }


def _bank_codes(exp: FMYEExport) -> set[str]:
    codes = set()
    for r in exp.rows("Chart"):
        code = (r.get("AccountCode") or "").strip()
        name = (r.get("AccountName") or "").upper()
        at = (r.get("AccountType") or "").upper()
        cat = (r.get("AccountCategory") or "").upper()
        if at == BANK_TYPE or cat == "B" or ("BANK" in name and "CHARGE" not in name):
            if code and code not in CASH_CODES:
                codes.add(code)
    # Always include Habib A/C seen on BRV/BPV
    codes.add("100068")
    codes.add("100314")
    return codes


def preview(years: set[int]):
    exp = FMYEExport(EXPORT_DIR)
    vouchers = [r for r in exp.rows("Voucher") if _in_years(r.get("VoucherDate"), years)]
    by_type = defaultdict(int)
    for r in vouchers:
        by_type[(r.get("VoucherType") or "").strip().upper()] += 1
    print(f"Voucher lines in years {sorted(years)}: {len(vouchers):,}")
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t or '(blank)'}: {n:,}")
    txns = {(r.get("VoucherType"), r.get("TransactionNO")) for r in vouchers}
    print(f"  Unique vouchers: {len(txns):,}")
    print(f"  Bank codes detected: {len(_bank_codes(exp))}")


def apply(years: set[int], uid: int, *, skip_invoice_jvr: bool = False):
    exp = FMYEExport(EXPORT_DIR)
    vouchers = [r for r in exp.rows("Voucher") if _in_years(r.get("VoucherDate"), years)]
    bank_codes = _bank_codes(exp)
    stats = defaultdict(int)

    with db.get_connection() as conn:
        acct_ids = _acct_map(conn)
        missing_accts = set()

        # Clear previous FMYE voucher imports only
        conn.execute("DELETE FROM general_ledger WHERE reference_type='fmye_voucher'")
        conn.execute("DELETE FROM cash_receipts WHERE reference_no LIKE 'CRV-%' OR reference_no LIKE 'FMYE-CRV-%'")
        conn.execute("DELETE FROM cash_payments WHERE reference_no LIKE 'CPV-%' OR reference_no LIKE 'FMYE-CPV-%'")
        conn.execute("DELETE FROM bank_receipts WHERE reference_no LIKE 'BRV-%' OR reference_no LIKE 'FMYE-BRV-%'")
        conn.execute("DELETE FROM bank_payments WHERE reference_no LIKE 'BPV-%' OR reference_no LIKE 'FMYE-BPV-%'")
        # Remove prior imported journals tagged in description
        old_jv = conn.execute(
            "SELECT id FROM journal_vouchers WHERE description LIKE 'FMYE:%'"
        ).fetchall()
        for (jid,) in old_jv:
            conn.execute("DELETE FROM journal_voucher_lines WHERE voucher_id=?", (jid,))
            conn.execute("DELETE FROM general_ledger WHERE voucher_id=?", (jid,))
            conn.execute("DELETE FROM journal_vouchers WHERE id=?", (jid,))
        stats["cleared_old_jv"] = len(old_jv)

        gl_batch = []
        # Group by voucher for cash/bank/JV documents
        groups: dict[tuple, list] = defaultdict(list)
        for v in vouchers:
            vt = (v.get("VoucherType") or "").strip().upper()
            tno = str(v.get("TransactionNO") or "").strip()
            groups[(vt, tno)].append(v)

        for v in vouchers:
            acode = (v.get("AccountCode") or "").strip()
            aid = acct_ids.get(acode)
            if not aid:
                missing_accts.add(acode)
                stats["gl_skipped_no_account"] += 1
                continue
            vt = (v.get("VoucherType") or "").strip().upper()
            tno = str(v.get("TransactionNO") or "").strip()
            ref = f"{vt}-{tno}"
            narr = (v.get("Narration") or "").strip()[:500]
            doc_name = (v.get("DocumentName") or "").strip().upper()
            if skip_invoice_jvr and vt == "JVR" and doc_name in {"SL", "PU", "SR", "PR"}:
                stats["gl_skipped_invoice_jvr"] += 1
                continue
            gl_batch.append((
                _d(v.get("VoucherDate")),
                aid,
                _f(v.get("Debit")),
                _f(v.get("Credit")),
                narr or ref,
                "fmye_voucher",
                0,
                ref,
                uid,
            ))
            if len(gl_batch) >= 3000:
                conn.executemany(
                    """INSERT INTO general_ledger(entry_date, account_id, debit, credit,
                       description, reference_type, reference_id, reference_no, created_by)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    gl_batch,
                )
                stats["gl_lines"] += len(gl_batch)
                gl_batch.clear()
        if gl_batch:
            conn.executemany(
                """INSERT INTO general_ledger(entry_date, account_id, debit, credit,
                   description, reference_type, reference_id, reference_no, created_by)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                gl_batch,
            )
            stats["gl_lines"] += len(gl_batch)

        cash_id = acct_ids.get("000000")
        # Cash / Bank books — one document per voucher using non-cash/bank contra amount
        for (vt, tno), lines in groups.items():
            if not lines:
                continue
            vdate = _d(lines[0].get("VoucherDate"))
            narr = (lines[0].get("Narration") or vt).strip()[:500]
            ref = f"{vt}-{tno}"

            if vt == "CRV":
                # Cash debit lines = money in; amount = sum of cash Dr (or non-cash Cr)
                amt = sum(_f(L.get("Debit")) for L in lines if (L.get("AccountCode") or "").strip() in CASH_CODES)
                if amt <= 0:
                    amt = sum(_f(L.get("Credit")) for L in lines if (L.get("AccountCode") or "").strip() not in CASH_CODES)
                if amt > 0 and cash_id:
                    conn.execute(
                        """INSERT INTO cash_receipts(document_no, receipt_date, account_id,
                           description, reference_no, amount, created_by)
                           VALUES(?,?,?,?,?,?,?)""",
                        (ref, vdate, cash_id, narr, ref, amt, uid),
                    )
                    stats["cash_receipts"] += 1

            elif vt == "CPV":
                amt = sum(_f(L.get("Credit")) for L in lines if (L.get("AccountCode") or "").strip() in CASH_CODES)
                if amt <= 0:
                    amt = sum(_f(L.get("Debit")) for L in lines if (L.get("AccountCode") or "").strip() not in CASH_CODES)
                if amt > 0 and cash_id:
                    conn.execute(
                        """INSERT INTO cash_payments(document_no, payment_date, account_id,
                           description, reference_no, amount, created_by)
                           VALUES(?,?,?,?,?,?,?)""",
                        (ref, vdate, cash_id, narr, ref, amt, uid),
                    )
                    stats["cash_payments"] += 1

            elif vt == "BRV":
                bank_line = next(
                    (L for L in lines if (L.get("AccountCode") or "").strip() in bank_codes and _f(L.get("Debit")) > 0),
                    None,
                )
                bank_code = (bank_line.get("AccountCode") if bank_line else "").strip()
                bank_aid = acct_ids.get(bank_code) if bank_code else None
                amt = _f(bank_line.get("Debit")) if bank_line else 0
                if amt <= 0:
                    amt = sum(
                        _f(L.get("Credit"))
                        for L in lines
                        if (L.get("AccountCode") or "").strip() not in bank_codes
                    )
                    # pick first bank account on voucher
                    for L in lines:
                        c = (L.get("AccountCode") or "").strip()
                        if c in bank_codes and acct_ids.get(c):
                            bank_aid = acct_ids[c]
                            break
                if amt > 0 and bank_aid:
                    conn.execute(
                        """INSERT INTO bank_receipts(document_no, receipt_date, account_id,
                           description, reference_no, amount, created_by)
                           VALUES(?,?,?,?,?,?,?)""",
                        (ref, vdate, bank_aid, narr, ref, amt, uid),
                    )
                    stats["bank_receipts"] += 1

            elif vt == "BPV":
                bank_line = next(
                    (L for L in lines if (L.get("AccountCode") or "").strip() in bank_codes and _f(L.get("Credit")) > 0),
                    None,
                )
                bank_code = (bank_line.get("AccountCode") if bank_line else "").strip()
                bank_aid = acct_ids.get(bank_code) if bank_code else None
                amt = _f(bank_line.get("Credit")) if bank_line else 0
                if amt <= 0:
                    amt = sum(
                        _f(L.get("Debit"))
                        for L in lines
                        if (L.get("AccountCode") or "").strip() not in bank_codes
                    )
                    for L in lines:
                        c = (L.get("AccountCode") or "").strip()
                        if c in bank_codes and acct_ids.get(c):
                            bank_aid = acct_ids[c]
                            break
                if amt > 0 and bank_aid:
                    conn.execute(
                        """INSERT INTO bank_payments(document_no, payment_date, account_id,
                           description, reference_no, amount, created_by)
                           VALUES(?,?,?,?,?,?,?)""",
                        (ref, vdate, bank_aid, narr, ref, amt, uid),
                    )
                    stats["bank_payments"] += 1

            elif vt == "JVR":
                doc_name = (lines[0].get("DocumentName") or "").strip().upper()
                if skip_invoice_jvr and doc_name in {"SL", "PU", "SR", "PR"}:
                    stats["jv_skipped_invoice"] += 1
                    continue
                total_dr = sum(_f(L.get("Debit")) for L in lines)
                total_cr = sum(_f(L.get("Credit")) for L in lines)
                if total_dr <= 0 and total_cr <= 0:
                    continue
                desc = f"FMYE:{ref} {narr}"[:500]
                cur = conn.execute(
                    """INSERT INTO journal_vouchers(document_no, voucher_date, description,
                       total_debit, total_credit, status, created_by, posted_by, posted_at)
                       VALUES(?,?,?,?,?,'posted',?,?,?)""",
                    (ref, vdate, desc, total_dr, total_cr, uid, uid, db._now()),
                )
                jid = cur.lastrowid
                for L in lines:
                    acode = (L.get("AccountCode") or "").strip()
                    aid = acct_ids.get(acode)
                    if not aid:
                        continue
                    conn.execute(
                        """INSERT INTO journal_voucher_lines(voucher_id, account_id, description, debit, credit)
                           VALUES(?,?,?,?,?)""",
                        (jid, aid, (L.get("Narration") or "")[:500], _f(L.get("Debit")), _f(L.get("Credit"))),
                    )
                stats["journal_vouchers"] += 1

        stats["missing_accounts"] = len(missing_accts)
        if missing_accts:
            print("Missing COA codes (sample):", sorted(missing_accts)[:15])

        # Balance check GL
        row = conn.execute(
            """SELECT ROUND(SUM(debit),2), ROUND(SUM(credit),2)
               FROM general_ledger WHERE reference_type='fmye_voucher'"""
        ).fetchone()
        stats["gl_debit_total"] = float(row[0] or 0)
        stats["gl_credit_total"] = float(row[1] or 0)
        stats["gl_diff"] = round(stats["gl_debit_total"] - stats["gl_credit_total"], 2)

    print("\nImport complete:")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    if abs(stats["gl_diff"]) > 1:
        print("WARNING: GL debit/credit not balanced — check missing accounts.")
    else:
        print("GL debit/credit balanced.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Import FMYE Voucher table into IFS GL + cash/bank")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--years", default="2026")
    ap.add_argument(
        "--skip-invoice-jvr",
        action="store_true",
        help="Skip JVR lines linked to SL/PU/SR/PR documents",
    )
    args = ap.parse_args()
    years = {int(y.strip()) for y in args.years.split(",") if y.strip()}
    print("=" * 60)
    print("FMYE Voucher -> IFS General Ledger + Cash/Bank Book")
    print("=" * 60)
    preview(years)
    if args.apply:
        apply(years, _uid(), skip_invoice_jvr=args.skip_invoice_jvr)
    else:
        print("\nRun with --apply to import.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
