"""Re-audit Aug 8 idle-deleted parties vs FMYE export + ERP backups."""
from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\MY ERPS")
sys.path.insert(0, str(ROOT))

LIVE = ROOT / "ifs_erp.db"
BAK_PARTY = ROOT / "ifs_erp_before_idle_party_delete.db"
BAK_ITEM = ROOT / "ifs_erp_before_idle_item_delete_20260808_173900.db"
DELETED_CSV = ROOT / "reports" / "idle_party_gl_accounts_2026.csv"
OUT_CSV = ROOT / "reports" / "idle_party_reaudit_2026.csv"
EXPORT_CANDIDATES = [
    ROOT / "import" / "fmye" / "full_live",
    ROOT / "import" / "fmye" / "full",
    ROOT / "import" / "fmye" / "full_old_20260808_094509",
]

YEAR_FROM, YEAR_TO = "2026-01-01", "2026-12-31"
FOCUS = "200164"


def _f(val, default=0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(str(val).replace(",", ""))
    except ValueError:
        return default


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


class FMYEExport:
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.reload_sql = (export_dir / "reload.sql").read_text(encoding="utf-8", errors="replace")
        self._maps: dict[str, dict] = {}

    def table_map(self) -> dict[str, dict]:
        if self._maps:
            return self._maps
        pat = re.compile(
            r'LOAD TABLE "saller"\."([^"]+)" \(([^)]+)\)\s+FROM \'([^\']*?(\d+)\.dat)\'',
            re.MULTILINE,
        )
        for name, cols_raw, _full, num in pat.findall(self.reload_sql):
            self._maps[name] = {
                "columns": [c.strip('"') for c in cols_raw.split(",")],
                "dat": self.export_dir / f"{num}.dat",
            }
        return self._maps

    def rows(self, table: str):
        info = self.table_map().get(table)
        if not info:
            return []
        path = info["dat"]
        cols = info["columns"]
        if not path.exists() or path.stat().st_size == 0:
            print(f"  MISSING/EMPTY {table}: {path}")
            return []
        print(f"  Loading {table} from {path.name} ({path.stat().st_size:,} bytes)...")
        out = []
        with path.open(encoding="windows-1252", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                reader = csv.reader(io.StringIO(line), delimiter=",", quotechar="'")
                out.append(dict(zip(cols, next(reader))))
        return out


def pick_export() -> Path:
    for p in EXPORT_CANDIDATES:
        if (p / "reload.sql").exists():
            return p
    raise SystemExit("No FMYE export folder found")


def party_2026_activity(conn, party_type: str, party_id: int) -> dict:
    """Count 2026 activity across ERP tables for a party id."""
    counts = {}
    if party_type == "customer":
        checks = {
            "sales_invoices": (
                "SELECT COUNT(*) c FROM sales_invoices WHERE customer_id=? AND invoice_date>=? AND invoice_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "sales_returns": (
                "SELECT COUNT(*) c FROM sales_returns WHERE customer_id=? AND return_date>=? AND return_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "cash_receipts": (
                "SELECT COUNT(*) c FROM cash_receipts WHERE party_type='customer' AND party_id=? AND receipt_date>=? AND receipt_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "bank_receipts": (
                "SELECT COUNT(*) c FROM bank_receipts WHERE party_type='customer' AND party_id=? AND receipt_date>=? AND receipt_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "fmye_party_entries": (
                "SELECT COUNT(*) c FROM fmye_party_entries WHERE party_type='customer' AND party_id=? AND entry_date>=? AND entry_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "party_transfers": (
                """SELECT COUNT(*) c FROM party_transfers
                   WHERE ((from_party_type='customer' AND from_party_id=?) OR (to_party_type='customer' AND to_party_id=?))
                     AND transfer_date>=? AND transfer_date<=?""",
                (party_id, party_id, YEAR_FROM, YEAR_TO),
            ),
            "weight_slips": (
                "SELECT COUNT(*) c FROM weight_slips WHERE customer_id=? AND slip_date>=? AND slip_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
        }
    else:
        checks = {
            "purchase_invoices": (
                "SELECT COUNT(*) c FROM purchase_invoices WHERE supplier_id=? AND invoice_date>=? AND invoice_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "purchase_returns": (
                "SELECT COUNT(*) c FROM purchase_returns WHERE supplier_id=? AND return_date>=? AND return_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "cash_payments": (
                "SELECT COUNT(*) c FROM cash_payments WHERE party_type='supplier' AND party_id=? AND payment_date>=? AND payment_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "bank_payments": (
                "SELECT COUNT(*) c FROM bank_payments WHERE party_type='supplier' AND party_id=? AND payment_date>=? AND payment_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "fmye_party_entries": (
                "SELECT COUNT(*) c FROM fmye_party_entries WHERE party_type='supplier' AND party_id=? AND entry_date>=? AND entry_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
            "party_transfers": (
                """SELECT COUNT(*) c FROM party_transfers
                   WHERE ((from_party_type='supplier' AND from_party_id=?) OR (to_party_type='supplier' AND to_party_id=?))
                     AND transfer_date>=? AND transfer_date<=?""",
                (party_id, party_id, YEAR_FROM, YEAR_TO),
            ),
            "weight_slips": (
                "SELECT COUNT(*) c FROM weight_slips WHERE supplier_id=? AND slip_date>=? AND slip_date<=?",
                (party_id, YEAR_FROM, YEAR_TO),
            ),
        }
    for name, (sql, params) in checks.items():
        try:
            n = conn.execute(sql, params).fetchone()[0]
            if n:
                counts[name] = n
        except Exception:
            pass
    # general_ledger by party code via account_code match later
    return counts


def gl_2026_for_code(conn, code: str) -> int:
    try:
        row = conn.execute(
            """SELECT COUNT(*) FROM general_ledger
               WHERE (account_code=? OR CAST(account_id AS TEXT)=?)
                 AND entry_date>=? AND entry_date<=?""",
            (code, code, YEAR_FROM, YEAR_TO),
        ).fetchone()
        return int(row[0] or 0)
    except Exception:
        try:
            # alternate schema: join chart_of_accounts
            row = conn.execute(
                """SELECT COUNT(*) FROM general_ledger g
                   JOIN chart_of_accounts c ON c.id=g.account_id
                   WHERE c.code=? AND g.entry_date>=? AND g.entry_date<=?""",
                (code, YEAR_FROM, YEAR_TO),
            ).fetchone()
            return int(row[0] or 0)
        except Exception:
            return 0


def lookup_party(conn, code: str) -> dict:
    out = {"customers": [], "suppliers": [], "coa": []}
    for table, key in (("customers", "customers"), ("suppliers", "suppliers")):
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            bal_cols = [c for c in ("opening_balance", "current_balance", "is_active", "name", "code", "id") if c in cols]
            sel = ", ".join(bal_cols)
            rows = conn.execute(
                f"SELECT {sel} FROM {table} WHERE code=? OR code LIKE ? OR name LIKE ?",
                (code, f"%{code}%", f"%{code}%"),
            ).fetchall()
            out[key] = [dict(r) for r in rows]
        except Exception as e:
            out[key] = [{"error": str(e)}]
    try:
        rows = conn.execute(
            """SELECT id, code, name, account_type, opening_balance, current_balance, is_active
               FROM chart_of_accounts
               WHERE code=? OR code LIKE ? OR name LIKE ?""",
            (code, f"%{code}%", f"%{code}%"),
        ).fetchall()
        out["coa"] = [dict(r) for r in rows]
    except Exception as e:
        # try minimal
        try:
            rows = conn.execute(
                "SELECT * FROM chart_of_accounts WHERE code=? LIMIT 5", (code,)
            ).fetchall()
            out["coa"] = [dict(r) for r in rows]
        except Exception as e2:
            out["coa"] = [{"error": f"{e} / {e2}"}]
    return out


def try_sqlanywhere():
    """Attempt pyodbc to FMYE11.db; return dict or None."""
    paths = [
        r"C:\IFS\DataBase\FMYE11.db",
        r"C:\Backup\IFSbackup\Saturday\FMYE11.db",
    ]
    try:
        import pyodbc
    except ImportError:
        print("pyodbc not installed — skipping SQL Anywhere")
        return None
    drivers = [d for d in pyodbc.drivers() if "anywhere" in d.lower() or "sql anywhere" in d.lower()]
    print("ODBC drivers (anywhere):", drivers)
    if not drivers:
        print("No SQL Anywhere ODBC driver — skipping live FMYE DB")
        return None
    driver = drivers[0]
    for dbpath in paths:
        if not os.path.exists(dbpath):
            print(f"  missing {dbpath}")
            continue
        for uid, pwd in (("DBA", "sql"), ("dba", "sql"), ("DBA", "")):
            try:
                conn_str = f"DRIVER={{{driver}}};DBF={dbpath};UID={uid};PWD={pwd};"
                cn = pyodbc.connect(conn_str, timeout=5)
                cur = cn.cursor()
                cur.execute(
                    """SELECT AccountCode, AccountName, AccountCategory, OpeningDr, OpeningCr, Active
                       FROM saller.Chart WHERE AccountCode=?""",
                    (FOCUS,),
                )
                chart = cur.fetchone()
                cur.execute(
                    """SELECT PeriodID, OpeningDr, OpeningCr, AccountType
                       FROM saller.OpeningBalances WHERE AccountCode=? ORDER BY PeriodID""",
                    (FOCUS,),
                )
                obs = cur.fetchall()
                cur.execute(
                    """SELECT COUNT(*) FROM saller.Voucher
                       WHERE AccountCode=? AND VoucherDate >= '2026-01-01' AND VoucherDate < '2027-01-01'""",
                    (FOCUS,),
                )
                vcnt = cur.fetchone()[0]
                cn.close()
                print(f"SQL Anywhere OK via {dbpath}")
                return {"chart": chart, "obs": obs, "voucher_2026": vcnt, "path": dbpath}
            except Exception as e:
                print(f"  fail {dbpath} uid={uid}: {e}")
    return None


def main():
    print("=" * 70)
    print("FOCUS ACCOUNT", FOCUS)
    print("=" * 70)

    # --- Live / backups for 200164 ---
    for label, path in (("LIVE", LIVE), ("BAK_PARTY", BAK_PARTY), ("BAK_ITEM", BAK_ITEM)):
        print(f"\n--- {label}: {path.name} exists={path.exists()} ---")
        if not path.exists():
            continue
        conn = connect(path)
        info = lookup_party(conn, FOCUS)
        for k, rows in info.items():
            print(f"  {k}: {rows if rows else '(none)'}")
        # exact ids
        for ptype, table in (("customer", "customers"), ("supplier", "suppliers")):
            row = conn.execute(f"SELECT id, code, name, opening_balance, current_balance, is_active FROM {table} WHERE code=?", (FOCUS,)).fetchone()
            if row:
                act = party_2026_activity(conn, ptype, int(row["id"]))
                gln = gl_2026_for_code(conn, FOCUS)
                print(f"  {ptype} 2026 activity: {act or 'NONE'}  gl_lines={gln}")
        conn.close()

    # --- FMYE SQL Anywhere ---
    print("\n--- SQL Anywhere probe ---")
    sa = try_sqlanywhere()
    if sa:
        print("  chart:", sa["chart"])
        print("  opening balances:", sa["obs"])
        print("  voucher_2026:", sa["voucher_2026"])

    # --- FMYE DAT export ---
    export_dir = pick_export()
    print(f"\n--- FMYE export: {export_dir} ---")
    exp = FMYEExport(export_dir)
    chart_rows = exp.rows("Chart")
    ob_rows = exp.rows("OpeningBalances")
    # Voucher can be huge — stream count for focus + build set of codes with 2026 activity
    vinfo = exp.table_map().get("Voucher")
    sale_info = exp.table_map().get("SaleInvoiceHeader")
    purch_info = exp.table_map().get("PurchaseHeader")
    sr_info = exp.table_map().get("SrHeader")
    pr_info = exp.table_map().get("PrHeader")

    chart_by_code = {r.get("AccountCode", "").strip(): r for r in chart_rows}
    # Opening balances for period 2026 (or latest)
    periods = sorted({r.get("PeriodID") for r in ob_rows if r.get("PeriodID")})
    period = "2026" if "2026" in periods else (max(periods) if periods else "2026")
    print(f"  OpeningBalances periods={periods} using={period}")
    fmye_ob: dict[str, float] = {}
    fmye_ob_detail: dict[str, tuple] = {}
    for r in ob_rows:
        if r.get("PeriodID") != period:
            continue
        code = (r.get("AccountCode") or "").strip()
        dr, cr = _f(r.get("OpeningDr")), _f(r.get("OpeningCr"))
        fmye_ob[code] = dr - cr
        fmye_ob_detail[code] = (dr, cr)

    focus_chart = chart_by_code.get(FOCUS)
    print(f"  Chart[{FOCUS}]: {focus_chart}")
    print(f"  OB[{FOCUS}] period {period}: net={fmye_ob.get(FOCUS)} detail={fmye_ob_detail.get(FOCUS)}")

    # Stream voucher / sale / purchase for 2026 txn counts by account/party code
    fmye_txn_counts: dict[str, int] = defaultdict(int)
    focus_voucher_samples = []

    def stream_count(path: Path, code_col: str, date_col: str, label: str):
        if not path or not path.exists():
            print(f"  skip {label}: missing {path}")
            return
        print(f"  Streaming {label} {path.name} ({path.stat().st_size:,} bytes)...")
        cols = None
        # get cols from table map
        for tname, info in exp.table_map().items():
            if info["dat"].resolve() == path.resolve() or info["dat"].name == path.name:
                cols = info["columns"]
                break
        if not cols:
            print(f"  cannot map columns for {label}")
            return
        ci = cols.index(code_col) if code_col in cols else None
        di = cols.index(date_col) if date_col in cols else None
        if ci is None or di is None:
            print(f"  bad cols for {label}: {code_col}/{date_col}")
            return
        n_lines = 0
        with path.open(encoding="windows-1252", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                parts = next(csv.reader(io.StringIO(line), delimiter=",", quotechar="'"))
                if len(parts) < max(ci, di) + 1:
                    continue
                dt = (parts[di] or "")[:10]
                if not dt.startswith("2026"):
                    continue
                code = (parts[ci] or "").strip()
                if not code:
                    continue
                fmye_txn_counts[code] += 1
                n_lines += 1
                if code == FOCUS and len(focus_voucher_samples) < 10 and label == "Voucher":
                    # store sample
                    row = dict(zip(cols, parts))
                    focus_voucher_samples.append(
                        {k: row.get(k) for k in ("VoucherType", "TransactionNO", "VoucherDate", "Debit", "Credit", "Narration", "DocumentName")}
                    )
        print(f"    2026 lines counted: {n_lines}")

    if vinfo:
        stream_count(vinfo["dat"], "AccountCode", "VoucherDate", "Voucher")
    if sale_info:
        stream_count(sale_info["dat"], "PartyCode", "InvoiceDate", "SaleInvoiceHeader")
    if purch_info:
        stream_count(purch_info["dat"], "PartyCode", "PurchaseInvoiceDate", "PurchaseHeader")
    if sr_info:
        stream_count(sr_info["dat"], "PartyCode", "SrDate", "SrHeader")
    if pr_info:
        stream_count(pr_info["dat"], "PartyCode", "PrDate", "PrHeader")

    print(f"  FOCUS FMYE 2026 txn count: {fmye_txn_counts.get(FOCUS, 0)}")
    for s in focus_voucher_samples:
        print(f"    sample: {s}")

    # --- Build deleted party set ---
    deleted = defaultdict(lambda: {"types": set(), "name": "", "opening": 0.0, "current": 0.0})
    with DELETED_CSV.open(encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            code = (row.get("code") or "").strip()
            if not code:
                continue
            deleted[code]["types"].add((row.get("type") or "").strip().lower())
            deleted[code]["name"] = row.get("name") or deleted[code]["name"]
            deleted[code]["opening"] = _f(row.get("opening"))
            deleted[code]["current"] = _f(row.get("current"))

    print(f"\nDeleted list codes: {len(deleted)}")

    # Backup party maps
    bak = connect(BAK_PARTY) if BAK_PARTY.exists() else None
    live = connect(LIVE)

    bak_cust = {}
    bak_sup = {}
    live_cust_codes = set()
    live_sup_codes = set()
    live_cust = {}
    live_sup = {}
    if bak:
        for r in bak.execute("SELECT id, code, name, opening_balance, current_balance, is_active FROM customers").fetchall():
            bak_cust[r["code"]] = dict(r)
        for r in bak.execute("SELECT id, code, name, opening_balance, current_balance, is_active FROM suppliers").fetchall():
            bak_sup[r["code"]] = dict(r)
    for r in live.execute("SELECT id, code, name, opening_balance, current_balance, is_active FROM customers").fetchall():
        live_cust_codes.add(r["code"])
        live_cust[r["code"]] = dict(r)
    for r in live.execute("SELECT id, code, name, opening_balance, current_balance, is_active FROM suppliers").fetchall():
        live_sup_codes.add(r["code"])
        live_sup[r["code"]] = dict(r)

    # COA balances live
    coa_by_code = {}
    try:
        for r in live.execute(
            "SELECT code, name, opening_balance, current_balance FROM chart_of_accounts"
        ).fetchall():
            coa_by_code[r["code"]] = dict(r)
    except Exception as e:
        print("COA load issue:", e)
        try:
            cols = [x[1] for x in live.execute("PRAGMA table_info(chart_of_accounts)").fetchall()]
            print("  coa cols:", cols)
            for r in live.execute("SELECT * FROM chart_of_accounts").fetchall():
                d = dict(r)
                coa_by_code[d.get("code") or d.get("account_code")] = d
        except Exception as e2:
            print("  coa fail:", e2)

    # Also find parties in backup missing from live (in case CSV incomplete)
    missing_codes = set()
    for code in bak_cust:
        if code not in live_cust_codes:
            missing_codes.add(code)
            if code not in deleted:
                deleted[code]["types"].add("customer")
                deleted[code]["name"] = bak_cust[code]["name"]
                deleted[code]["opening"] = _f(bak_cust[code].get("opening_balance"))
                deleted[code]["current"] = _f(bak_cust[code].get("current_balance"))
    for code in bak_sup:
        if code not in live_sup_codes:
            missing_codes.add(code)
            if code not in deleted:
                deleted[code]["types"].add("supplier")
                deleted[code]["name"] = bak_sup[code]["name"]
                deleted[code]["opening"] = _f(bak_sup[code].get("opening_balance"))
                deleted[code]["current"] = _f(bak_sup[code].get("current_balance"))
            else:
                deleted[code]["types"].add("supplier")

    print(f"Backup parties missing in live: {len(missing_codes)}")
    print(f"Total codes to audit: {len(deleted)}")

    # Category map from FMYE
    cat_map = {
        "S": "Customer(S)",
        "V": "Supplier(V)",
        "C": "GL/Cash(C)",
        "A": "Asset(A)",
        "L": "Liability(L)",
        "E": "Expense(E)",
        "R": "Income(R)",
        "I": "Inventory(I)",
    }

    # Counters for A-E
    cnt_A = cnt_B = cnt_C = cnt_D = cnt_E = 0
    dual_role_issues = []

    report_rows = []
    for code in sorted(deleted.keys()):
        info = deleted[code]
        types = info["types"]
        # normalize deleted_as
        has_c = "customer" in types
        has_s = "supplier" in types
        if has_c and has_s:
            deleted_as = "both"
        elif has_c:
            deleted_as = "customer"
        elif has_s:
            deleted_as = "supplier"
        else:
            deleted_as = ",".join(sorted(types)) or "unknown"

        name = info["name"]
        erp_ob = 0.0
        erp_cur = 0.0
        if code in bak_cust:
            erp_ob = max(erp_ob, abs(_f(bak_cust[code].get("opening_balance"))), _f(bak_cust[code].get("opening_balance")))
            # keep signed from primary role
        # Prefer the deleted role's backup balances
        if has_c and code in bak_cust:
            erp_ob = _f(bak_cust[code].get("opening_balance"))
            erp_cur = _f(bak_cust[code].get("current_balance"))
            name = name or bak_cust[code]["name"]
        if has_s and code in bak_sup:
            # if both, note separately — use supplier if deleted as supplier only or both take larger abs
            sob = _f(bak_sup[code].get("opening_balance"))
            scur = _f(bak_sup[code].get("current_balance"))
            if not has_c or abs(sob) + abs(scur) >= abs(erp_ob) + abs(erp_cur):
                if has_c and has_s:
                    # keep customer values in erp_ob; we'll use reason for dual
                    pass
                else:
                    erp_ob = sob
                    erp_cur = scur
            name = name or bak_sup[code]["name"]
        if has_c and has_s and code in bak_cust and code in bak_sup:
            erp_ob = _f(bak_cust[code].get("opening_balance"))
            erp_cur = _f(bak_cust[code].get("current_balance"))
            # store supplier side in reason later

        f_ob = fmye_ob.get(code)
        f_tx = fmye_txn_counts.get(code, 0)
        ch = chart_by_code.get(code)
        f_cat = ""
        if ch:
            raw_cat = (ch.get("AccountCategory") or "").strip()
            f_cat = cat_map.get(raw_cat, raw_cat)
            if not name:
                name = ch.get("AccountName") or ""

        # Dual-role: one side deleted, other kept with balance
        dual_issue = False
        dual_note = ""
        if has_c and not has_s and code in live_sup:
            if abs(_f(live_sup[code].get("opening_balance"))) > 0.009 or abs(_f(live_sup[code].get("current_balance"))) > 0.009:
                dual_issue = True
                dual_note = f"customer deleted; supplier kept OB={live_sup[code].get('opening_balance')} CUR={live_sup[code].get('current_balance')}"
        if has_s and not has_c and code in live_cust:
            if abs(_f(live_cust[code].get("opening_balance"))) > 0.009 or abs(_f(live_cust[code].get("current_balance"))) > 0.009:
                dual_issue = True
                dual_note = f"supplier deleted; customer kept OB={live_cust[code].get('opening_balance')} CUR={live_cust[code].get('current_balance')}"
        # also: both existed in backup as dual, one deleted
        if code in bak_cust and code in bak_sup:
            still_c = code in live_cust_codes
            still_s = code in live_sup_codes
            if still_c != still_s:
                if not dual_issue:
                    dual_issue = True
                    dual_note = f"dual-role in backup; live customer={still_c} supplier={still_s}"
                if still_c and code in live_cust and (abs(_f(live_cust[code].get("opening_balance"))) > 0.009 or abs(_f(live_cust[code].get("current_balance"))) > 0.009):
                    dual_issue = True
                if still_s and code in live_sup and (abs(_f(live_sup[code].get("opening_balance"))) > 0.009 or abs(_f(live_sup[code].get("current_balance"))) > 0.009):
                    dual_issue = True

        coa = coa_by_code.get(code)
        coa_nonzero = False
        coa_note = ""
        if coa:
            cob = _f(coa.get("opening_balance") or coa.get("OpeningDr"))
            ccur = _f(coa.get("current_balance"))
            if abs(cob) > 0.009 or abs(ccur) > 0.009:
                coa_nonzero = True
                coa_note = f"COA OB={cob} CUR={ccur}"

        # Classification A-E
        in_fmye_chart = code in chart_by_code
        was_in_erp = code in bak_cust or code in bak_sup
        never_imported = in_fmye_chart and not was_in_erp and code not in live_cust_codes and code not in live_sup_codes
        # For deleted list they WERE in ERP — "never imported" among deleted is rare;
        # also flag FMYE chart parties with OB/activity that were never in backup (separate scan below)

        A = f_ob is not None and abs(f_ob) > 0.009
        B = f_tx > 0
        C = never_imported  # for deleted set usually False
        D = dual_issue
        E = coa_nonzero

        if A:
            cnt_A += 1
        if B:
            cnt_B += 1
        if C:
            cnt_C += 1
        if D:
            cnt_D += 1
            dual_role_issues.append((code, dual_note))
        if E:
            cnt_E += 1

        reasons = []
        if A:
            reasons.append(f"FMYE OB({period})={f_ob:.2f}")
        if B:
            reasons.append(f"FMYE 2026 txns={f_tx}")
        if D:
            reasons.append(dual_note)
        if E:
            reasons.append(coa_note)
        if abs(erp_ob) > 0.009 or abs(erp_cur) > 0.009:
            reasons.append(f"ERP backup OB={erp_ob} CUR={erp_cur} (delete used NIL filter?)")
        if in_fmye_chart and not A and not B:
            reasons.append("In FMYE chart; nil OB and no 2026 txn in export")
        if not in_fmye_chart:
            reasons.append("Not in FMYE Chart export")

        # should_restore decision
        if A or B or (abs(erp_ob) > 0.009) or (abs(erp_cur) > 0.009):
            should = "YES"
        elif D or E:
            should = "REVIEW"
        elif in_fmye_chart:
            should = "REVIEW"  # exists in old DB, idle — user may want master back
            reasons.append("idle master present in FMYE — optional restore")
        else:
            should = "NO"
            if not reasons:
                reasons.append("nil everywhere")

        # Strengthen REVIEW -> note
        report_rows.append({
            "code": code,
            "name": name,
            "deleted_as": deleted_as,
            "erp_ob_backup": erp_ob if (code in bak_cust or code in bak_sup) else "",
            "erp_current_backup": erp_cur if (code in bak_cust or code in bak_sup) else "",
            "fmye_ob": "" if f_ob is None else round(f_ob, 2),
            "fmye_2026_txns": f_tx,
            "fmye_category": f_cat,
            "should_restore": should,
            "reason": "; ".join(reasons),
        })

    # Extra: FMYE chart parties with OB/activity never in ERP (never imported) — append as informational
    never_imp_extra = 0
    for code, ch in chart_by_code.items():
        cat = (ch.get("AccountCategory") or "").strip()
        if cat not in ("S", "V"):
            continue
        if code in bak_cust or code in bak_sup or code in live_cust_codes or code in live_sup_codes:
            continue
        if code in deleted:
            continue
        f_ob = fmye_ob.get(code)
        f_tx = fmye_txn_counts.get(code, 0)
        if (f_ob is not None and abs(f_ob) > 0.009) or f_tx > 0:
            never_imp_extra += 1
            cnt_C += 1
            deleted_as = "customer" if cat == "S" else "supplier"
            report_rows.append({
                "code": code,
                "name": ch.get("AccountName") or "",
                "deleted_as": f"never_imported_{deleted_as}",
                "erp_ob_backup": "",
                "erp_current_backup": "",
                "fmye_ob": "" if f_ob is None else round(f_ob, 2),
                "fmye_2026_txns": f_tx,
                "fmye_category": cat_map.get(cat, cat),
                "should_restore": "YES",
                "reason": "Never imported to ERP but FMYE has OB and/or 2026 activity",
            })

    # Write CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "code", "name", "deleted_as", "erp_ob_backup", "erp_current_backup",
        "fmye_ob", "fmye_2026_txns", "fmye_category", "should_restore", "reason",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(report_rows, key=lambda x: (0 if x["should_restore"] == "YES" else 1 if x["should_restore"] == "REVIEW" else 2, -(_f(x["fmye_ob"]) if x["fmye_ob"] != "" else 0), -int(x["fmye_2026_txns"] or 0), x["code"])):
            w.writerow(r)

    yes = [r for r in report_rows if r["should_restore"] == "YES"]
    review = [r for r in report_rows if r["should_restore"] == "REVIEW"]
    no = [r for r in report_rows if r["should_restore"] == "NO"]

    # Strong REVIEW: dual-role or COA nonzero or FMYE chart with name match user concern
    strong_review = [
        r for r in review
        if "dual-role" in r["reason"].lower()
        or "COA" in r["reason"]
        or "customer deleted" in r["reason"].lower()
        or "supplier deleted" in r["reason"].lower()
        or "ERP backup OB=" in r["reason"]
    ]

    print("\n" + "=" * 70)
    print("SUMMARY COUNTS")
    print("=" * 70)
    print(f"A) Non-zero FMYE OB ({period}): {cnt_A}")
    print(f"B) Any FMYE 2026 txns:         {cnt_B}")
    print(f"C) Never imported (+extra):    {cnt_C} (extra never-imp with OB/txn: {never_imp_extra})")
    print(f"D) Dual-role imbalance:        {cnt_D}")
    print(f"E) Non-zero COA match:         {cnt_E}")
    print(f"YES restore: {len(yes)}  REVIEW: {len(review)} (strong={len(strong_review)})  NO: {len(no)}")
    print(f"Wrote {OUT_CSV}")

    print("\n--- FOCUS 200164 report row ---")
    for r in report_rows:
        if r["code"] == FOCUS:
            print(r)

    print("\n--- Top 20 YES restore candidates ---")
    yes_sorted = sorted(
        yes,
        key=lambda x: (
            -(_f(x["fmye_ob"]) if x["fmye_ob"] != "" else 0),
            -int(x["fmye_2026_txns"] or 0),
            x["code"],
        ),
    )
    for i, r in enumerate(yes_sorted[:20], 1):
        print(f"{i:2}. {r['code']} | {r['name'][:40]:40} | OB={r['fmye_ob']} tx={r['fmye_2026_txns']} | {r['deleted_as']} | {r['reason'][:80]}")

    print("\n--- Strong REVIEW (sample up to 20) ---")
    for i, r in enumerate(strong_review[:20], 1):
        print(f"{i:2}. {r['code']} | {r['name'][:40]:40} | {r['reason'][:100]}")

    # Selective restore safety check
    print("\n--- Selective restore safety ---")
    if bak:
        # Sample: would restoring YES codes create PK/code conflicts?
        conflicts = []
        for r in yes:
            code = r["code"]
            if "never_imported" in r["deleted_as"]:
                continue
            if code in live_cust_codes or code in live_sup_codes:
                # partial dual still present
                conflicts.append(code)
        print(f"YES codes already partially present in live (dual leftover): {len(conflicts)}")
        print(f"  samples: {conflicts[:15]}")
        # FK orphan risk: restore from backup by code — IDs may differ if sequences moved
        print("Safety: selective INSERT of master rows from backup by copying columns is SAFE if:")
        print("  - code not already in live for that table")
        print("  - no FK refs needed (idle delete removed only unreferenced masters)")
        print("  - use new IDs or preserve backup IDs only if unused in live")
        live_max_c = live.execute("SELECT MAX(id) FROM customers").fetchone()[0]
        live_max_s = live.execute("SELECT MAX(id) FROM suppliers").fetchone()[0]
        bak_ids_c = {r["id"] for r in bak_cust.values()}
        bak_ids_s = {r["id"] for r in bak_sup.values()}
        live_ids_c = {r["id"] for r in live_cust.values()}
        live_ids_s = {r["id"] for r in live_sup.values()}
        id_overlap_c = bak_ids_c & live_ids_c
        id_overlap_s = bak_ids_s & live_ids_s
        print(f"  live max customer id={live_max_c} supplier id={live_max_s}")
        print(f"  backup customer ids still used in live: {len(id_overlap_c)} (expect many — kept parties)")
        # For deleted only:
        del_c_ids = [bak_cust[c]["id"] for c in bak_cust if c not in live_cust_codes]
        del_s_ids = [bak_sup[c]["id"] for c in bak_sup if c not in live_sup_codes]
        reclaim_c = [i for i in del_c_ids if i in live_ids_c]
        reclaim_s = [i for i in del_s_ids if i in live_ids_s]
        print(f"  deleted customer backup ids reused in live: {len(reclaim_c)} → must assign NEW ids if >0")
        print(f"  deleted supplier backup ids reused in live: {len(reclaim_s)} → must assign NEW ids if >0")

    if bak:
        bak.close()
    live.close()
    print("\nDONE")


if __name__ == "__main__":
    main()
