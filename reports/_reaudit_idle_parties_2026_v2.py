"""Deep follow-up analysis for idle party reaudit."""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
LIVE = ROOT / "ifs_erp.db"
BAK = ROOT / "ifs_erp_before_idle_party_delete.db"
EXPORT = ROOT / "import" / "fmye" / "full_live"
DELETED = ROOT / "reports" / "idle_party_gl_accounts_2026.csv"
OUT = ROOT / "reports" / "idle_party_reaudit_2026.csv"


def _f(v):
    try:
        return float(str(v or 0).replace(",", ""))
    except Exception:
        return 0.0


def main():
    deleted = defaultdict(set)
    names = {}
    with DELETED.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            deleted[r["code"]].add(r["type"].strip().lower())
            names[r["code"]] = r["name"]
    print("deleted codes", len(deleted))

    reload = (EXPORT / "reload.sql").read_text(encoding="utf-8", errors="replace")
    pat = re.compile(
        r'LOAD TABLE "saller"\."([^"]+)" \(([^)]+)\)\s+FROM \'([^\']*?(\d+)\.dat)\'',
        re.M,
    )
    maps = {}
    for name, cols_raw, _fpth, num in pat.findall(reload):
        maps[name] = {
            "cols": [c.strip('"') for c in cols_raw.split(",")],
            "dat": EXPORT / f"{num}.dat",
        }

    def load_table(t):
        info = maps[t]
        cols = info["cols"]
        out = []
        with info["dat"].open(encoding="windows-1252", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                parts = next(csv.reader(io.StringIO(line), delimiter=",", quotechar="'"))
                out.append(dict(zip(cols, parts)))
        return out

    chart = {r["AccountCode"].strip(): r for r in load_table("Chart")}
    obs = load_table("OpeningBalances")
    print("chart", len(chart), "ob rows", len(obs))

    by_period_nonzero = defaultdict(int)
    hist_nonzero = set()
    ob2026 = {}
    for r in obs:
        code = r["AccountCode"].strip()
        if code not in deleted:
            continue
        net = _f(r["OpeningDr"]) - _f(r["OpeningCr"])
        if abs(net) > 0.009:
            by_period_nonzero[r["PeriodID"]] += 1
            hist_nonzero.add(code)
        if r["PeriodID"] == "2026":
            ob2026[code] = net

    print("Deleted with non-zero OB by period:", dict(sorted(by_period_nonzero.items())))
    print("Deleted with ANY-period non-zero OB:", len(hist_nonzero))
    print("Deleted with non-zero OB 2026:", sum(1 for v in ob2026.values() if abs(v) > 0.009))

    print("Sample hist nonzero (up to 20):")
    for code in sorted(hist_nonzero)[:20]:
        rows = [
            (r["PeriodID"], _f(r["OpeningDr"]), _f(r["OpeningCr"]))
            for r in obs
            if r["AccountCode"].strip() == code
            and abs(_f(r["OpeningDr"]) - _f(r["OpeningCr"])) > 0.009
        ]
        print(code, names.get(code, "")[:40], rows)

    bc = sqlite3.connect(str(BAK))
    bc.row_factory = sqlite3.Row
    lc = sqlite3.connect(str(LIVE))
    lc.row_factory = sqlite3.Row
    bak_c = {r["code"]: dict(r) for r in bc.execute("select id,code,name,opening_balance,current_balance from customers")}
    bak_s = {r["code"]: dict(r) for r in bc.execute("select id,code,name,opening_balance,current_balance from suppliers")}
    live_c = {r["code"]: dict(r) for r in lc.execute("select id,code,name,opening_balance,current_balance from customers")}
    live_s = {r["code"]: dict(r) for r in lc.execute("select id,code,name,opening_balance,current_balance from suppliers")}

    dual_deleted_one_kept = []
    for code, types in deleted.items():
        in_bak_c = code in bak_c
        in_bak_s = code in bak_s
        in_live_c = code in live_c
        in_live_s = code in live_s
        if in_bak_c and in_bak_s and (in_live_c != in_live_s):
            kept = live_c.get(code) or live_s.get(code)
            dual_deleted_one_kept.append(
                (
                    code,
                    names.get(code, ""),
                    "customer" if in_live_c else "supplier",
                    kept.get("opening_balance"),
                    kept.get("current_balance"),
                    sorted(types),
                )
            )
    print("Dual-role: one side deleted one kept:", len(dual_deleted_one_kept))
    for s in dual_deleted_one_kept[:30]:
        print(" ", s)

    cats = defaultdict(int)
    for c in deleted:
        if c in chart:
            cats[chart[c].get("AccountCategory")] += 1
        else:
            cats["MISSING"] += 1
    print("Deleted in FMYE chart cats:", dict(cats))

    for code in ["100773", "200164"]:
        print("DETAIL", code)
        print("  deleted as", deleted.get(code))
        ch = chart.get(code)
        if ch:
            print("  chart cat", ch.get("AccountCategory"), ch.get("AccountName"))
        print("  bak_c", bak_c.get(code))
        print("  bak_s", bak_s.get(code))
        print("  live_c", live_c.get(code))
        print("  live_s", live_s.get(code))
        print(
            "  ob all",
            [
                (r["PeriodID"], r["OpeningDr"], r["OpeningCr"])
                for r in obs
                if r["AccountCode"].strip() == code
            ],
        )

    nz_bak = []
    for code in bak_c:
        if code not in live_c and (
            abs(_f(bak_c[code]["opening_balance"])) > 0.009
            or abs(_f(bak_c[code]["current_balance"])) > 0.009
        ):
            nz_bak.append(("customer", code, bak_c[code]))
    for code in bak_s:
        if code not in live_s and (
            abs(_f(bak_s[code]["opening_balance"])) > 0.009
            or abs(_f(bak_s[code]["current_balance"])) > 0.009
        ):
            nz_bak.append(("supplier", code, bak_s[code]))
    print("Backup missing with nonzero ERP bal:", len(nz_bak))
    for x in nz_bak[:20]:
        print(" ", x)

    # Stream FMYE 2026 txn counts for deleted only (faster focused)
    txn = defaultdict(int)

    def stream(path, cols, code_col, date_col):
        ci, di = cols.index(code_col), cols.index(date_col)
        with path.open(encoding="windows-1252", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                parts = next(csv.reader(io.StringIO(line), delimiter=",", quotechar="'"))
                if len(parts) <= max(ci, di):
                    continue
                if not (parts[di] or "").startswith("2026"):
                    continue
                code = (parts[ci] or "").strip()
                if code in deleted:
                    txn[code] += 1

    for t, cc, dc in [
        ("Voucher", "AccountCode", "VoucherDate"),
        ("SaleInvoiceHeader", "PartyCode", "InvoiceDate"),
        ("PurchaseHeader", "PartyCode", "PurchaseInvoiceDate"),
        ("SrHeader", "PartyCode", "SrDate"),
        ("PrHeader", "PartyCode", "PrDate"),
    ]:
        info = maps[t]
        print("streaming", t)
        stream(info["dat"], info["cols"], cc, dc)

    print("Deleted with FMYE 2026 txns:", len(txn))
    for code, n in sorted(txn.items(), key=lambda x: -x[1])[:30]:
        print(f"  {code} n={n} {names.get(code,'')[:40]} deleted={sorted(deleted[code])}")

    # Rebuild refined CSV with better rules
    # Also load prior fmye_ob from stream of OB 2026
    rows_out = []
    cnt = dict(A=0, B=0, C=0, D=0, E=0, hist=0)

    # never imported party chart S/V with OB/txn
    for code, ch in chart.items():
        cat = (ch.get("AccountCategory") or "").strip()
        if cat not in ("S", "V"):
            continue
        if code in bak_c or code in bak_s or code in live_c or code in live_s:
            continue
        f_ob = None
        for r in obs:
            if r["AccountCode"].strip() == code and r["PeriodID"] == "2026":
                f_ob = _f(r["OpeningDr"]) - _f(r["OpeningCr"])
                break
        # compute txn for this code quickly - only if in voucher map we didn't track non-deleted
        # skip heavy; check OB only + scan txn dict empty
        if f_ob is not None and abs(f_ob) > 0.009:
            cnt["C"] += 1
            rows_out.append(
                {
                    "code": code,
                    "name": ch.get("AccountName") or "",
                    "deleted_as": "never_imported_" + ("customer" if cat == "S" else "supplier"),
                    "erp_ob_backup": "",
                    "erp_current_backup": "",
                    "fmye_ob": round(f_ob, 2),
                    "fmye_2026_txns": 0,
                    "fmye_category": "Customer(S)" if cat == "S" else "Supplier(V)",
                    "should_restore": "YES",
                    "reason": "Never imported to ERP; non-zero FMYE OB 2026",
                    "fmye_hist_ob": "",
                }
            )

    coa = {
        r["code"]: dict(r)
        for r in lc.execute(
            "select code,name,opening_balance,current_balance from chart_of_accounts"
        )
    }

    cat_map = {"S": "Customer(S)", "V": "Supplier(V)", "C": "GL/Cash(C)"}

    for code in sorted(deleted.keys()):
        types = deleted[code]
        has_c = "customer" in types
        has_s = "supplier" in types
        if has_c and has_s:
            deleted_as = "both"
        elif has_c:
            deleted_as = "customer"
        elif has_s:
            deleted_as = "supplier"
        else:
            deleted_as = ",".join(sorted(types))

        name = names.get(code, "")
        erp_ob = erp_cur = 0.0
        if has_c and code in bak_c:
            erp_ob = _f(bak_c[code]["opening_balance"])
            erp_cur = _f(bak_c[code]["current_balance"])
            name = name or bak_c[code]["name"]
        if has_s and code in bak_s and not has_c:
            erp_ob = _f(bak_s[code]["opening_balance"])
            erp_cur = _f(bak_s[code]["current_balance"])
            name = name or bak_s[code]["name"]
        if has_c and has_s:
            erp_ob = _f(bak_c.get(code, {}).get("opening_balance"))
            erp_cur = _f(bak_c.get(code, {}).get("current_balance"))

        f_ob = ob2026.get(code)
        if f_ob is None and code in chart:
            f_ob = 0.0
        f_tx = txn.get(code, 0)
        ch = chart.get(code)
        f_cat = cat_map.get((ch or {}).get("AccountCategory", ""), (ch or {}).get("AccountCategory", ""))
        if ch and not name:
            name = ch.get("AccountName") or ""

        hist_net = None
        if code in hist_nonzero:
            # latest non-zero period before/equal 2026
            best = None
            for r in obs:
                if r["AccountCode"].strip() != code:
                    continue
                net = _f(r["OpeningDr"]) - _f(r["OpeningCr"])
                if abs(net) > 0.009:
                    best = (r["PeriodID"], net)
            hist_net = best
            cnt["hist"] += 1

        dual = False
        dual_note = ""
        if code in bak_c and code in bak_s and ((code in live_c) != (code in live_s)):
            dual = True
            if code in live_c:
                dual_note = (
                    f"supplier deleted; customer kept OB={live_c[code]['opening_balance']} CUR={live_c[code]['current_balance']}"
                )
            else:
                dual_note = (
                    f"customer deleted; supplier kept OB={live_s[code]['opening_balance']} CUR={live_s[code]['current_balance']}"
                )

        coa_row = coa.get(code)
        coa_nz = False
        coa_note = ""
        if coa_row and (
            abs(_f(coa_row["opening_balance"])) > 0.009 or abs(_f(coa_row["current_balance"])) > 0.009
        ):
            coa_nz = True
            coa_note = f"COA OB={coa_row['opening_balance']} CUR={coa_row['current_balance']}"

        A = f_ob is not None and abs(f_ob) > 0.009
        B = f_tx > 0
        D = dual
        E = coa_nz
        if A:
            cnt["A"] += 1
        if B:
            cnt["B"] += 1
        if D:
            cnt["D"] += 1
        if E:
            cnt["E"] += 1

        reasons = []
        if A:
            reasons.append(f"FMYE OB(2026)={f_ob:.2f}")
        if B:
            reasons.append(f"FMYE 2026 txns={f_tx}")
        if hist_net and not A:
            reasons.append(f"FMYE historical OB period {hist_net[0]}={hist_net[1]:.2f} (cleared by 2026)")
        if dual_note:
            reasons.append(dual_note)
        if coa_note:
            reasons.append(coa_note)
        if abs(erp_ob) > 0.009 or abs(erp_cur) > 0.009:
            reasons.append(f"ERP backup OB={erp_ob} CUR={erp_cur}")
        if ch and not A and not B and not hist_net:
            reasons.append("In FMYE chart; nil OB (all periods checked for hist) and no 2026 txn")
        elif ch and not A and not B and hist_net:
            pass
        if not ch:
            reasons.append("Not in FMYE Chart export")

        # Decision:
        # YES: non-zero 2026 FMYE OB, or any 2026 FMYE txn, or ERP backup non-zero (shouldn't happen)
        # REVIEW strong: dual-role with kept balance, COA nonzero, or historical OB
        # REVIEW weak: in chart idle
        # NO: not in chart, nil
        if A or B or abs(erp_ob) > 0.009 or abs(erp_cur) > 0.009:
            should = "YES"
        elif dual and (
            (code in live_c and (abs(_f(live_c[code]["opening_balance"])) > 0.009 or abs(_f(live_c[code]["current_balance"])) > 0.009))
            or (code in live_s and (abs(_f(live_s[code]["opening_balance"])) > 0.009 or abs(_f(live_s[code]["current_balance"])) > 0.009))
            or B
            or A
        ):
            should = "YES"
        elif dual or coa_nz or hist_net:
            should = "REVIEW"
        elif ch:
            should = "NO"  # truly idle master — optional, not recommended
            reasons.append("Truly idle in FMYE 2026; restore only if master list completeness required")
        else:
            should = "NO"
            if not reasons:
                reasons.append("nil everywhere")

        # dual with activity already YES via B; ensure dual+kept balance => YES
        if dual and should != "YES":
            kept_bal = False
            if code in live_c and (
                abs(_f(live_c[code]["opening_balance"])) > 0.009 or abs(_f(live_c[code]["current_balance"])) > 0.009
            ):
                kept_bal = True
            if code in live_s and (
                abs(_f(live_s[code]["opening_balance"])) > 0.009 or abs(_f(live_s[code]["current_balance"])) > 0.009
            ):
                kept_bal = True
            if kept_bal:
                should = "YES"
                reasons.append("Dual-role: restore deleted side to match active counterpart")

        rows_out.append(
            {
                "code": code,
                "name": name,
                "deleted_as": deleted_as,
                "erp_ob_backup": erp_ob if (code in bak_c or code in bak_s) else "",
                "erp_current_backup": erp_cur if (code in bak_c or code in bak_s) else "",
                "fmye_ob": "" if f_ob is None else round(f_ob, 2),
                "fmye_2026_txns": f_tx,
                "fmye_category": f_cat,
                "should_restore": should,
                "reason": "; ".join(reasons),
            }
        )

    fields = [
        "code",
        "name",
        "deleted_as",
        "erp_ob_backup",
        "erp_current_backup",
        "fmye_ob",
        "fmye_2026_txns",
        "fmye_category",
        "should_restore",
        "reason",
    ]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(
            rows_out,
            key=lambda x: (
                0 if x["should_restore"] == "YES" else 1 if x["should_restore"] == "REVIEW" else 2,
                -abs(_f(x["fmye_ob"]) if x["fmye_ob"] != "" else 0),
                -int(x["fmye_2026_txns"] or 0),
                x["code"],
            ),
        ):
            w.writerow(r)

    yes = [r for r in rows_out if r["should_restore"] == "YES"]
    review = [r for r in rows_out if r["should_restore"] == "REVIEW"]
    no = [r for r in rows_out if r["should_restore"] == "NO"]
    print("COUNTS", cnt)
    print("YES", len(yes), "REVIEW", len(review), "NO", len(no))
    print("Wrote", OUT)

    print("\nTop 20 YES:")
    yes_sorted = sorted(
        yes,
        key=lambda x: (-abs(_f(x["fmye_ob"]) if x["fmye_ob"] != "" else 0), -int(x["fmye_2026_txns"] or 0), x["code"]),
    )
    for i, r in enumerate(yes_sorted[:20], 1):
        print(
            f"{i:2}. {r['code']} | {r['name'][:42]:42} | OB={r['fmye_ob']} tx={r['fmye_2026_txns']} | {r['deleted_as']} | {r['reason'][:90]}"
        )

    print("\nREVIEW (all):")
    for i, r in enumerate(review[:40], 1):
        print(f"{i:2}. {r['code']} | {r['name'][:42]:42} | {r['reason'][:100]}")

    # safety
    del_c_ids = [bak_c[c]["id"] for c in bak_c if c not in live_c]
    del_s_ids = [bak_s[c]["id"] for c in bak_s if c not in live_s]
    live_ids_c = {r["id"] for r in live_c.values()}
    live_ids_s = {r["id"] for r in live_s.values()}
    reclaim_c = [i for i in del_c_ids if i in live_ids_c]
    reclaim_s = [i for i in del_s_ids if i in live_ids_s]
    print("\nRestore safety:")
    print("  deleted customer rows", len(del_c_ids), "id reuse", len(reclaim_c))
    print("  deleted supplier rows", len(del_s_ids), "id reuse", len(reclaim_s))
    print("  YES needing insert (code absent on that side):")
    need = []
    for r in yes:
        code = r["code"]
        if "never_imported" in r["deleted_as"]:
            need.append((code, "import_from_fmye"))
            continue
        if r["deleted_as"] in ("supplier", "both") and code not in live_s and code in bak_s:
            need.append((code, "restore_supplier_from_bak"))
        if r["deleted_as"] in ("customer", "both") and code not in live_c and code in bak_c:
            need.append((code, "restore_customer_from_bak"))
    print(" ", len(need), need[:30])

    # 200164 focus sales in live
    print("\n200164 live sales:")
    row = live_c.get("200164")
    if row:
        for s in lc.execute(
            "select invoice_no, invoice_date, total_amount, status from sales_invoices where customer_id=? order by invoice_date",
            (row["id"],),
        ):
            print(" ", dict(s))

    bc.close()
    lc.close()


if __name__ == "__main__":
    main()
