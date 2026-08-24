"""Enrich FMYE 2026 prod/cons/SA audit with qty totals and ERP adjustment storage."""
import sqlite3
from collections import Counter
from pathlib import Path
from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _d, _f

OUT = Path(r"c:\MY ERPS\reports\fmye_prod_cons_sa_2026_audit.txt")
e = FMYEExport(EXPORT_DIR)
YEAR = "2026"

dpr_h = {(r.get("DPRCode") or "").strip(): r for r in e.rows("DPRHeader") if (_d(r.get("DPRDate")) or "")[:4] == YEAR}
cons_h = {(r.get("ConsNoteCode") or "").strip(): r for r in e.rows("ConsumptionNoteHeader") if (_d(r.get("ConsNoteDate")) or "")[:4] == YEAR}
sa_h = {(r.get("SaCode") or "").strip(): r for r in e.rows("SAHeader") if (_d(r.get("SaDate")) or "")[:4] == YEAR}

dn = dq = cn = cq = wn = wq = sn = sq = 0
dpr_items = set(); cons_items = set(); sa_items = set()
for r in e.rows("DPRDetail"):
    if (r.get("DPRCode") or "").strip() in dpr_h:
        dn += 1
        dq += _f(r.get("Quantity"))
        dpr_items.add((r.get("ItemCode") or "").strip().upper())
for r in e.rows("ConsumptionNoteDetail"):
    if (r.get("ConsNoteCode") or "").strip() in cons_h:
        cn += 1
        cq += _f(r.get("Quantity"))
        wq += _f(r.get("WastageQuantity"))
        cons_items.add((r.get("ItemCode") or "").strip().upper())
for r in e.rows("SADetail"):
    if (r.get("SaCode") or "").strip() in sa_h:
        sn += 1
        sq += _f(r.get("Quantity"))
        sa_items.add((r.get("ItemCode") or "").strip().upper())

# All-year pending (any year) for context
def pending_any(rows, date_key, status_key="Status"):
    p2026 = p_other = 0
    for r in rows:
        st = str(r.get(status_key) or "").strip()
        if st == "1":
            continue
        y = (_d(r.get(date_key)) or "")[:4]
        if y == YEAR:
            p2026 += 1
        else:
            p_other += 1
    return p2026, p_other

p_dpr = pending_any(e.rows("DPRHeader"), "DPRDate")
p_cons = pending_any(e.rows("ConsumptionNoteHeader"), "ConsNoteDate")
p_sa = pending_any(e.rows("SAHeader"), "SaDate")

c = sqlite3.connect(r"c:\MY ERPS\ifs_erp.db")
tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
extra = []
extra.append("")
extra.append("=== FMYE 2026 line totals ===")
extra.append(f"DPR lines={dn} qty={dq:,.3f} distinct_items={len(dpr_items)}")
extra.append(f"Consumption lines={cn} qty={cq:,.3f} wastage_qty={wq:,.3f} distinct_items={len(cons_items)}")
extra.append(f"Stock Adj lines={sn} qty={sq:,.3f} distinct_items={len(sa_items)}")
extra.append("")
extra.append("=== Pending approval (Status != 1) ===")
extra.append(f"DPR pending 2026={p_dpr[0]} other_years={p_dpr[1]}")
extra.append(f"Consumption pending 2026={p_cons[0]} other_years={p_cons[1]}")
extra.append(f"Stock Adj pending 2026={p_sa[0]} other_years={p_sa[1]}")
extra.append("")
extra.append("=== ERP inventory adjustment storage ===")
extra.append(f"stock_adjustments table present: {'stock_adjustments' in tables}")
# adjustments often live as inventory_movements reason
adj_mov = c.execute(
    """SELECT COUNT(*), COALESCE(SUM(quantity),0)
       FROM inventory_movements
       WHERE substr(movement_date,1,4)=?
         AND (reference_type LIKE '%adjust%' OR lower(COALESCE(reason,'')) LIKE '%adjust%'
              OR lower(COALESCE(reason,'')) LIKE 'sa-%' OR lower(COALESCE(reason,'')) LIKE 'sa %')""",
    (YEAR,),
).fetchone()
extra.append(f"inventory_movements 2026 looking like adjustments: n={adj_mov[0]} qty={adj_mov[1]}")
# any movement referencing FMYE SA codes
sa_hits = 0
for code in sa_h:
    n = c.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE reason LIKE ? OR reference_no LIKE ?",
        (f"%{code}%", f"%{code}%"),
    ).fetchone()[0]
    sa_hits += n
extra.append(f"inventory_movements mentioning FMYE SaCodes: {sa_hits}")
# DPR refs
dpr_hits = 0
sample_dpr = list(dpr_h)[:50]
for code in sample_dpr:
    dpr_hits += c.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE reason LIKE ? OR reference_no LIKE ?",
        (f"%{code}%", f"%{code}%"),
    ).fetchone()[0]
extra.append(f"inventory_movements mentioning sample DPR codes (first 50): {dpr_hits}")
cons_hits = 0
for code in list(cons_h)[:50]:
    cons_hits += c.execute(
        "SELECT COUNT(*) FROM inventory_movements WHERE reason LIKE ? OR reference_no LIKE ?",
        (f"%{code}%", f"%{code}%"),
    ).fetchone()[0]
extra.append(f"inventory_movements mentioning sample Cons codes (first 50): {cons_hits}")
po = c.execute("SELECT id, document_no, order_date, status, planned_qty, actual_qty, notes FROM production_orders").fetchall()
extra.append(f"ERP production_orders all: {po}")
# get_inventory_adjustments path
try:
    import database as db
    hist = db.get_inventory_adjustments() if hasattr(db, "get_inventory_adjustments") else []
    hist26 = [h for h in (hist or []) if str(h.get("movement_date") or h.get("adjustment_date") or "")[:4] == YEAR]
    extra.append(f"get_inventory_adjustments total={len(hist or [])} in_2026={len(hist26)}")
except Exception as ex:
    extra.append(f"get_inventory_adjustments error: {ex}")

text = OUT.read_text(encoding="utf-8")
OUT.write_text(text + "\n" + "\n".join(extra), encoding="utf-8")
print("\n".join(extra))
c.close()
