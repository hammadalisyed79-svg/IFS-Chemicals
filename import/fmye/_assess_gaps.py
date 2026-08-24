"""One-off assessment: current export vs Saturday live unload vs ifs_erp.db."""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))

from import_fmye_from_dat import FMYEExport, _d  # noqa: E402

FOCUS = ["2026-08-06", "2026-08-07", "2026-08-08"]


def summarize(label: str, path: Path):
    exp = FMYEExport(path)
    print(f"\n===== {label} =====")
    specs = [
        ("SaleInvoiceHeader", "InvoiceDate"),
        ("PurchaseHeader", "PurchaseInvoiceDate"),
        ("SrHeader", "SrDate"),
        ("PrHeader", "PrDate"),
        ("Voucher", "VoucherDate"),
    ]
    out = {}
    for table, dcol in specs:
        rows = exp.rows(table)
        dates = [_d(r.get(dcol)) for r in rows if r.get(dcol)]
        by = Counter(d for d in dates if d >= "2026-08-01")
        y2026 = sum(1 for d in dates if d.startswith("2026"))
        mx = max(dates) if dates else None
        print(f"{table}: n={len(rows)} y2026={y2026} max={mx} Aug+={dict(sorted(by.items()))}")
        for f in FOCUS:
            print(f"  {f}: {by.get(f, 0)}")
        out[table] = rows
    return out


def main() -> None:
    live_dir = ROOT / "import" / "fmye" / "_live_delta"
    full_dir = ROOT / "import" / "fmye" / "full"
    reload = full_dir / "reload.sql"
    if not (live_dir / "reload.sql").exists():
        (live_dir / "reload.sql").write_bytes(reload.read_bytes())

    old = summarize("CURRENT EXPORT full", full_dir)
    live = summarize("SATURDAY LIVE UNLOAD", live_dir)

    print("\n===== ROW COUNT DELTA (live - export) =====")
    for table in ["SaleInvoiceHeader", "PurchaseHeader", "SrHeader", "PrHeader", "Voucher"]:
        n_old = len(old[table])
        n_live = len(live[table])
        print(f"{table}: export={n_old} live={n_live} delta={n_live - n_old}")

    con = sqlite3.connect(str(ROOT / "ifs_erp.db"))

    def ifs_set(table: str) -> set[str]:
        return {(r[0] or "").strip().upper() for r in con.execute(f"SELECT document_no FROM {table}")}

    maps = [
        ("SaleInvoiceHeader", "sales_invoices", "InvoiceDate", "DocumentNo", None),
        ("PurchaseHeader", "purchase_invoices", "PurchaseInvoiceDate", "PurchaseInvoiceCode", "PI-"),
        ("SrHeader", "sales_returns", "SrDate", "SrNo", "SR-"),
        ("PrHeader", "purchase_returns", "PrDate", "PrNo", "PR-"),
    ]
    print("\n===== LIVE docs missing in IFS =====")
    for table, ifs_t, dcol, doccol, prefix in maps:
        existing = ifs_set(ifs_t)
        miss = Counter()
        have = Counter()
        samples = []
        for r in live[table]:
            d = _d(r.get(dcol))
            if d < "2026-08-01":
                continue
            raw = (r.get(doccol) or "").strip()
            if not raw:
                continue
            doc = ((prefix or "") + raw).upper()
            if doc in existing:
                have[d] += 1
            else:
                miss[d] += 1
                if d >= "2026-08-06" and len(samples) < 20:
                    samples.append((d, doc, (r.get("Name") or "")[:40], r.get("NetAmount"), r.get("Status")))
        print(f"{table}->{ifs_t}: Aug+ HAVE {dict(sorted(have.items()))}")
        print(f"  Aug+ MISS {dict(sorted(miss.items()))}")
        if samples:
            print("  missing samples:", samples)

    print("\n===== Unique voucher headers on/after 2026-08-06 (live) =====")
    seen = set()
    by = defaultdict(Counter)
    for r in live["Voucher"]:
        d = _d(r.get("VoucherDate"))
        if d < "2026-08-06":
            continue
        key = (r.get("VoucherType"), r.get("TransactionNO"), d)
        if key in seen:
            continue
        seen.add(key)
        by[d][r.get("VoucherType") or "?"] += 1
    for d in sorted(by):
        print(f"  {d}: {dict(by[d])} total={sum(by[d].values())}")

    # Compare export vs live missing relative to each other for Aug 7-8
    print("\n===== Docs in LIVE not in EXPORT (new since Aug6 11:44 unload) =====")
    for table, dcol, doccol, prefix in [
        ("SaleInvoiceHeader", "InvoiceDate", "DocumentNo", None),
        ("PurchaseHeader", "PurchaseInvoiceDate", "PurchaseInvoiceCode", "PI-"),
        ("SrHeader", "SrDate", "SrNo", "SR-"),
        ("PrHeader", "PrDate", "PrNo", "PR-"),
    ]:
        old_docs = set()
        for r in old[table]:
            raw = (r.get(doccol) or "").strip()
            if raw:
                old_docs.add(((prefix or "") + raw).upper())
        new_by = Counter()
        new_samples = []
        for r in live[table]:
            raw = (r.get(doccol) or "").strip()
            if not raw:
                continue
            doc = ((prefix or "") + raw).upper()
            if doc in old_docs:
                continue
            d = _d(r.get(dcol))
            new_by[d] += 1
            if len(new_samples) < 15:
                new_samples.append((d, doc, (r.get("Name") or "")[:40], r.get("NetAmount")))
        print(f"{table}: new_docs={sum(new_by.values())} by_date={dict(sorted(new_by.items()))}")
        if new_samples:
            print("  samples:", new_samples)

    # voucher line delta
    old_v = {(_d(r.get("VoucherDate")), r.get("VoucherType"), r.get("TransactionNO"), r.get("SeqNo")) for r in old["Voucher"]}
    new_v_by = Counter()
    new_v_type = defaultdict(Counter)
    for r in live["Voucher"]:
        key = (_d(r.get("VoucherDate")), r.get("VoucherType"), r.get("TransactionNO"), r.get("SeqNo"))
        if key in old_v:
            continue
        d = key[0]
        new_v_by[d] += 1
        new_v_type[d][r.get("VoucherType") or "?"] += 1
    print("\n===== New voucher LINES in live not in export =====")
    print("by_date:", dict(sorted(new_v_by.items())))
    for d in sorted(new_v_type):
        print(f"  {d}: {dict(new_v_type[d])}")

    con.close()


if __name__ == "__main__":
    main()
