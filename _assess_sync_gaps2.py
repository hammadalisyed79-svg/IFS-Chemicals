"""Deeper gap checks: returns via vouchers, weight incomplete slips, payroll months, voucher docs."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))
from import_fmye_from_dat import FMYEExport, _d  # noqa: E402

EXP = FMYEExport(ROOT / "import" / "fmye" / "full")
IFS = sqlite3.connect(str(ROOT / "ifs_erp.db"))
IFS.row_factory = sqlite3.Row
WDB = Path(r"C:\modern_weight_scale_final\database\weight_scale.db")


def main():
    print("=== FMYE tables containing Return/SR/PR ===")
    for t in sorted(EXP.table_map()):
        if any(x in t.lower() for x in ("return", "sr", "pr")):
            print(" ", t, EXP.table_map()[t]["dat"].name, EXP.table_map()[t]["columns"][:12])

    # How returns are imported in migrate - SaleReturn?
    print("\n=== migrate step_returns source tables ===")
    # read from migrate via inspection of rows used
    # Check Voucher DocumentName for SR/PR dated Aug
    vrows = EXP.rows("Voucher")
    cols = EXP.table_map()["Voucher"]["columns"]
    print("Voucher cols:", cols)
    by_doc_day = Counter()
    by_type_day = Counter()
    max_by_doc = {}
    for r in vrows:
        d = _d(r.get("VoucherDate"))
        doc = (r.get("DocumentName") or r.get("Document") or "").strip().upper()
        vt = (r.get("VoucherType") or r.get("VType") or "").strip().upper()
        if d >= "2026-08-01":
            by_doc_day[(doc or "?", d)] += 1
            by_type_day[(vt or "?", d)] += 1
        if doc:
            max_by_doc[doc] = max(max_by_doc.get(doc, ""), d)
    print("Max date by DocumentName:")
    for k in sorted(max_by_doc):
        if max_by_doc[k] >= "2026-07-01":
            print(f"  {k}: {max_by_doc[k]}")
    print("Aug DocumentName x day counts (top):")
    for (doc, d), c in sorted(by_doc_day.items()):
        print(f"  {d} {doc}: {c}")
    print("Aug VoucherType x day:")
    for (vt, d), c in sorted(by_type_day.items()):
        print(f"  {d} {vt}: {c}")

    # Distinct voucher headers (DocumentNo+Date+Type) vs lines
    print("\n=== Voucher header-ish distinct keys Aug ===")
    keys_by_day = defaultdict(set)
    for r in vrows:
        d = _d(r.get("VoucherDate"))
        if d < "2026-08-01":
            continue
        key = (
            (r.get("DocumentName") or "").strip(),
            (r.get("DocumentNo") or r.get("VoucherNo") or "").strip(),
            (r.get("VoucherType") or "").strip(),
            d,
        )
        keys_by_day[d].add(key)
    for d in sorted(keys_by_day):
        print(f"  {d}: distinct voucher keys={len(keys_by_day[d])} lines={sum(1 for r in vrows if _d(r.get('VoucherDate'))==d)}")

    # IFS tables
    print("\n=== IFS financial tables ===")
    for r in IFS.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"):
        n = r[0]
        low = n.lower()
        if any(x in low for x in ("voucher", "cash", "bank", "receipt", "payment", "return", "payroll", "gl_")):
            c = IFS.execute(f"SELECT COUNT(*) FROM [{n}]").fetchone()[0]
            print(f"  {n}: {c}")

    print("\n=== payroll_runs latest ===")
    for r in IFS.execute(
        """SELECT document_no, payroll_month, payroll_year, run_date, status,
                  total_gross, total_net FROM payroll_runs
           ORDER BY payroll_year DESC, payroll_month DESC, run_date DESC LIMIT 15"""
    ):
        print(" ", dict(r))
    print(
        "counts by year/month:",
        list(
            IFS.execute(
                """SELECT payroll_year, payroll_month, COUNT(*) c, MAX(run_date)
                   FROM payroll_runs GROUP BY 1,2 ORDER BY 1 DESC,2 DESC LIMIT 12"""
            )
        ),
    )

    # employee_advances recent
    cols = [x[1] for x in IFS.execute("PRAGMA table_info(employee_advances)")]
    print("employee_advances cols:", cols)
    dcol = next((c for c in cols if "date" in c.lower()), None)
    if dcol:
        print(
            "advances max/day Aug+:",
            list(
                IFS.execute(
                    f"SELECT {dcol}, COUNT(*) FROM employee_advances WHERE {dcol}>='2026-08-01' GROUP BY 1 ORDER BY 1"
                )
            ),
            "MAX=",
            IFS.execute(f"SELECT MAX({dcol}) FROM employee_advances").fetchone()[0],
        )

    # Weight detail Aug 6
    print("\n=== IFS weight_slips 2026-08-06 ===")
    for r in IFS.execute(
        """SELECT document_no, slip_date, status, first_weight, second_weight, net_weight, party_name
           FROM weight_slips WHERE slip_date='2026-08-06' ORDER BY document_no"""
    ):
        print(" ", dict(r))

    wcon = sqlite3.connect(str(WDB))
    wcon.row_factory = sqlite3.Row
    wcols = [x[1] for x in wcon.execute("PRAGMA table_info(weights)")]
    print("weights cols:", wcols)
    print("\n=== scale weights 2026-08-06 ===")
    for r in wcon.execute(
        "SELECT * FROM weights WHERE substr(entry_date,1,10)='2026-08-06' ORDER BY id"
    ):
        d = {k: r[k] for k in r.keys() if k in (
            "id", "slip_no", "ticket_no", "entry_date", "status", "first_weight",
            "second_weight", "net_weight", "party_name", "vehicle_no", "transaction_type",
            "txn_type", "is_completed", "second_weight_time",
        ) or "weight" in k or "status" in k or "date" in k or "ticket" in k or "slip" in k or "party" in k or "vehicle" in k or "txn" in k or "trans" in k}
        print(" ", d)

    # Compare ticket numbers
    ifs_docs = {r[0] for r in IFS.execute("SELECT document_no FROM weight_slips WHERE slip_date='2026-08-06'")}
    print("IFS docs:", sorted(ifs_docs))
    # guess ticket column
    for col in ("ticket_no", "slip_no", "id", "serial_no", "token_no"):
        if col in wcols:
            scale_ids = [r[0] for r in wcon.execute(
                f"SELECT {col} FROM weights WHERE substr(entry_date,1,10)='2026-08-06'"
            )]
            print(f"scale {col}:", scale_ids)
            break
    print("scale status counts Aug6:", list(wcon.execute(
        "SELECT status, COUNT(*) FROM weights WHERE substr(entry_date,1,10)='2026-08-06' GROUP BY 1"
    )))
    print("IFS status counts Aug6:", list(IFS.execute(
        "SELECT status, COUNT(*) FROM weight_slips WHERE slip_date='2026-08-06' GROUP BY 1"
    )))

    # Returns in FMYE - check SaleInvoiceHeader for return flags? Or separate
    print("\n=== Looking for return data in SaleInvoice / vouchers SR ===")
    # Sale return might be DocumentName SR in vouchers with unique docs
    sr_docs = set()
    pr_docs = set()
    for r in vrows:
        d = _d(r.get("VoucherDate"))
        docn = (r.get("DocumentName") or "").strip().upper()
        docno = (r.get("DocumentNo") or "").strip()
        if docn == "SR" and d >= "2026-07-01":
            sr_docs.add((d, docno))
        if docn == "PR" and d >= "2026-07-01":
            pr_docs.add((d, docno))
    print("SR voucher docs Jul+:", len(sr_docs), "max", max((d for d, _ in sr_docs), default=None))
    by = Counter(d for d, _ in sr_docs)
    print(" SR by day Jul+:", dict(sorted(by.items())))
    by = Counter(d for d, _ in pr_docs)
    print(" PR by day Jul+:", dict(sorted(by.items())))
    print("PR voucher docs Jul+:", len(pr_docs), "max", max((d for d, _ in pr_docs), default=None))

    # IFS returns Jul+
    print("IFS sales_returns Jul+:", list(IFS.execute(
        "SELECT return_date, COUNT(*) FROM sales_returns WHERE return_date>='2026-07-01' GROUP BY 1 ORDER BY 1"
    )))
    print("IFS purchase_returns Jul+:", list(IFS.execute(
        "SELECT return_date, COUNT(*) FROM purchase_returns WHERE return_date>='2026-07-01' GROUP BY 1 ORDER BY 1"
    )))

    # Check if SaleReturnDetail-like in reload via string
    reload = (ROOT / "import" / "fmye" / "full" / "reload.sql").read_text(encoding="utf-8", errors="replace")
    for needle in ("Return", "SrNo", "PrNo", "SaleReturn", "PurchaseReturn"):
        if needle.lower() in reload.lower():
            # find table names
            pass
    import re
    tables = re.findall(r'LOAD TABLE "saller"\."([^"]+)"', reload)
    ret_tables = [t for t in tables if "return" in t.lower() or t in ("SR", "PR")]
    print("reload tables with return:", ret_tables)
    # Also list all tables
    print("ALL tables:", ", ".join(tables))

    # FMYE11 freshness vs dat
    fmye = Path(r"C:\IFS\DataBase\FMYE11.db")
    dat = ROOT / "import" / "fmye" / "full" / "715.dat"
    print("\n=== freshness ===")
    import datetime
    for p in (fmye, Path(r"C:\IFS\DataBase\FMYE11New.log"), dat, ROOT / "import" / "fmye" / "full" / "reload.sql", ROOT / "ifs_erp.db", WDB, Path(r"C:\IFS\DataBase\PAYROLL\IFS-PayRoll-Final.accdb")):
        st = p.stat()
        print(f"  {p.name}: mtime={datetime.datetime.fromtimestamp(st.st_mtime)} size={st.st_size:,}")

    # journal vouchers Aug detail
    jcols = [x[1] for x in IFS.execute("PRAGMA table_info(journal_vouchers)")]
    print("\njournal_vouchers cols:", jcols)
    # try party vouchers / receipt payment tables
    for t in ("receipt_vouchers", "payment_vouchers", "cash_receipts", "cash_payments",
              "bank_receipts", "bank_payments", "vouchers", "gl_entries", "ledger_entries"):
        try:
            n = IFS.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  found {t}: {n}")
        except Exception:
            pass

    # How migrate maps vouchers - peek document_no patterns in journal
    print("journal Aug docs sample:")
    for r in IFS.execute(
        "SELECT document_no, voucher_date, voucher_type, total_debit, total_credit FROM journal_vouchers WHERE voucher_date>='2026-08-01' ORDER BY voucher_date, document_no LIMIT 30"
    ):
        print(" ", dict(r))

    print("\njournal counts by type Aug:")
    if "voucher_type" in jcols:
        for r in IFS.execute(
            """SELECT voucher_date, voucher_type, COUNT(*) FROM journal_vouchers
               WHERE voucher_date>='2026-08-01' GROUP BY 1,2 ORDER BY 1,2"""
        ):
            print(" ", tuple(r))


if __name__ == "__main__":
    main()
