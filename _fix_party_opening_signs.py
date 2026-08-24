"""Restore party opening_balance from FMYE OpeningDr-OpeningCr, then recalc current_balance."""
from __future__ import annotations

import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _opening_map
import database as db

ob = _opening_map(FMYEExport(EXPORT_DIR).rows("OpeningBalances"), period_id="2026")
conn = sqlite3.connect(str(ROOT / "ifs_erp.db"))
conn.row_factory = sqlite3.Row

fixed_s = fixed_c = 0
for table, key in (("suppliers", "supplier"), ("customers", "customer")):
    for r in conn.execute(f"SELECT id, code, opening_balance FROM {table}"):
        code = (r["code"] or "").strip()
        if code not in ob:
            continue
        want = float(ob[code])
        have = float(r["opening_balance"] or 0)
        if abs(want - have) < 0.02:
            continue
        conn.execute(
            f"UPDATE {table} SET opening_balance=?, modified_at=? WHERE id=?",
            (want, db._now(), r["id"]),
        )
        fixed_s += 1 if table == "suppliers" else 0
        fixed_c += 1 if table == "customers" else 0
        print(f"{key} {code}: {have} -> {want}")

conn.commit()
print(f"openings fixed suppliers={fixed_s} customers={fixed_c}")

# Recalculate current balances from ledgers (new +Dr math)
print("recalculating party balances...")
stats = db.recalculate_party_balances()
print(stats)

# Verify WINGS TECH
w = conn.execute(
    "SELECT id, code, opening_balance, current_balance FROM suppliers WHERE code='200084'"
).fetchone()
print("WINGS stored", dict(w))
party, entries = db.get_supplier_ledger(w["id"], include_linked=False)
ls = party["ledger_summary"]
print("WINGS ledger open", ls["opening"], "dr", ls["period_debit"], "cr", ls["period_credit"], "close", ls["closing"])
print("opening row", entries[0] if entries else None)
for e in entries[1:4]:
    print(" ", e.get("date"), e.get("ref"), e.get("debit"), e.get("credit"), e.get("balance"))

conn.close()
