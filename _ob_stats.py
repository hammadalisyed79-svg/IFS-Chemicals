import sys, sqlite3
sys.path.insert(0, r"C:\MY ERPS")
from import_fmye_from_dat import FMYEExport, EXPORT_DIR, _opening_map, _f
exp = FMYEExport(EXPORT_DIR)
ob = _opening_map(exp.rows("OpeningBalances"), period_id="2026")
c=sqlite3.connect("ifs_erp.db"); c.row_factory=sqlite3.Row

# Sign mismatch stats
flip=0; match=0; missing=0; samples_flip=[]; samples_match=[]
for r in c.execute("SELECT id,code,name,opening_balance,current_balance FROM suppliers"):
    f = ob.get(r["code"])
    if f is None:
        missing += 1
        continue
    erp = float(r["opening_balance"] or 0)
    if abs(erp - f) < 0.02:
        match += 1
        if abs(erp)>1000 and len(samples_match)<5:
            samples_match.append((r["code"], erp, f))
    elif abs(erp + f) < 0.02 and abs(erp)>0.02:
        flip += 1
        if len(samples_flip)<8:
            samples_flip.append((r["code"], r["name"][:35], erp, f))
    else:
        # other mismatch
        if abs(erp)>0.02 or abs(f)>0.02:
            if len(samples_flip)<12:
                samples_flip.append((r["code"], "OTHER "+r["name"][:30], erp, f))

print("suppliers match", match, "flipped_sign", flip, "no_fmye", missing)
print("flip samples", samples_flip)
print("match samples", samples_match)

# customers
cf=0; cm=0; co=0
for r in c.execute("SELECT code,opening_balance FROM customers"):
    f = ob.get(r["code"])
    if f is None: continue
    erp=float(r["opening_balance"] or 0)
    if abs(erp-f)<0.02: cm+=1
    elif abs(erp+f)<0.02 and abs(erp)>0.02: cf+=1
    elif abs(erp)>0.02 or abs(f)>0.02: co+=1
print("customers match", cm, "flipped", cf, "other", co)

# WINGS ledger with correct convention preview
print("\nWINGS if +Dr convention: open 76900 Dr, +credits reduce ->", 76900-72000-3600)
