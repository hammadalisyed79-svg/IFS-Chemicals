"""
Import standard weights into ERP products (by product code only).

Default source: Sales & Inventory Management .accdb (tblProduct: ProductID + Weight).

Usage:
  python import_product_weights.py                 # preview from default .accdb
  python import_product_weights.py --apply         # write to ERP
  python import_product_weights.py --csv code_weight.csv --apply
  python import_product_weights.py --fmye          # FMYE InwardDetail (if 767.dat has data)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ACCDB = Path(
    r"C:\IFS\DataBase\26.12.2021 work\DataBase File"
    r"\SALES AND INVENTORY MANAGEMENT SOFTWARE_be.accdb"
)
# Front-end folder the user points to — tables are linked; real data is in *_be.accdb
SALES_SOFTWARE_DIR = Path(r"C:\IFS\DataBase\Sales Software")
DEFAULT_ACCDB_TABLE = "tblProduct"
DEFAULT_ACCDB_CODE_COL = "ProductID"
DEFAULT_ACCDB_WEIGHT_COL = "Weight"
DEFAULT_FMYE_DIR = Path(__file__).parent / "import" / "fmye" / "full"
WEIGHT_SCALE_SLIP_MARKERS = frozenset({"fweight", "sweight", "vehicleno", "itemtype"})


def resolve_sales_weights_accdb(path: Path | None = None) -> Path:
    """Prefer backend *_be.accdb; fall back to Sales Software front-end if it has local tables."""
    candidates = []
    if path:
        candidates.append(path)
    candidates.append(DEFAULT_ACCDB)
    # Sibling / known backend next to Sales Software
    be = (
        Path(r"C:\IFS\DataBase\26.12.2021 work\DataBase File")
        / "SALES AND INVENTORY MANAGEMENT SOFTWARE_be.accdb"
    )
    candidates.append(be)
    for p in SALES_SOFTWARE_DIR.glob("*_be.accdb"):
        candidates.append(p)
    for p in SALES_SOFTWARE_DIR.glob("*.accdb"):
        if p.name.lower().endswith(".laccdb") or "backup" in p.name.lower():
            continue
        candidates.append(p)
    for p in candidates:
        if p and p.exists() and p.suffix.lower() == ".accdb":
            return p
    raise FileNotFoundError(
        f"Sales weights Access DB not found. Tried: {DEFAULT_ACCDB} and {SALES_SOFTWARE_DIR}"
    )

CODE_HINTS = (
    "itemcode", "productcode", "productid", "code", "item_code", "product_code",
    "prcode", "materialcode", "rawcode", "finishedcode", "sku", "partno", "part_no",
)
WEIGHT_HINTS = (
    "standardweight", "stdweight", "standard_weight", "unitweight", "unit_weight",
    "netweight", "weight", "wt", "perunitweight", "bagweight", "packweight",
)
SKIP_TABLE_PREFIX = ("msys", "~")


def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _pick_column(columns: list[str], hints: tuple[str, ...], prefer_sub: str | None = None) -> str | None:
    normed = {c: _norm_col(c) for c in columns}
    best = None
    best_score = -1
    for col, n in normed.items():
        score = 0
        if n in hints:
            score = 100
        elif any(h in n for h in hints):
            score = 50
        if prefer_sub and prefer_sub in n:
            score += 30
        if score > best_score:
            best_score = score
            best = col
    return best


def _access_driver() -> str:
    try:
        import pyodbc
    except ImportError as e:
        raise RuntimeError(
            "pyodbc is not installed. Run: pip install pyodbc"
        ) from e
    drivers = [d for d in pyodbc.drivers() if "Access" in d or "ACE" in d]
    if not drivers:
        raise RuntimeError(
            "No Microsoft Access ODBC driver found. Install "
            "'Microsoft Access Database Engine' (64-bit) on this PC."
        )
    return drivers[0]


def list_access_tables(path: Path) -> list[str]:
    import pyodbc

    cs = f"DRIVER={{{_access_driver()}}};DBQ={path};"
    with pyodbc.connect(cs) as conn:
        cur = conn.cursor()
        return sorted(
            r.table_name
            for r in cur.tables(tableType="TABLE")
            if r.table_name and not r.table_name.lower().startswith(SKIP_TABLE_PREFIX)
        )


def read_access_rows(path: Path, table: str | None = None) -> tuple[str, str, str, list[dict]]:
    import pyodbc

    cs = f"DRIVER={{{_access_driver()}}};DBQ={path};"
    with pyodbc.connect(cs) as conn:
        cur = conn.cursor()
        tables = list_access_tables(path)
        if not tables:
            raise RuntimeError(f"No tables in {path}")

        chosen = table
        code_col = weight_col = None
        rows_out: list[dict] = []

        scan_order = [chosen] if chosen else tables
        if not chosen:
            # Prefer tables that look like item/product masters
            def rank(t: str) -> int:
                tl = t.lower()
                if "item" in tl or "product" in tl or "material" in tl:
                    return 0
                if "master" in tl or "stock" in tl:
                    return 1
                return 2
            scan_order = sorted(tables, key=rank)

        for tname in scan_order:
            if not tname:
                continue
            try:
                cur.execute(f"SELECT * FROM [{tname}]")
            except Exception:
                continue
            cols = [d[0] for d in cur.description]
            cc = _pick_column(cols, CODE_HINTS, "code")
            wc = _pick_column(cols, WEIGHT_HINTS, "standard")
            if not cc or not wc:
                continue
            batch = []
            for row in cur.fetchall():
                rec = {cols[i]: row[i] for i in range(len(cols))}
                batch.append(rec)
            if batch:
                normed = {_norm_col(c) for c in cols}
                if WEIGHT_SCALE_SLIP_MARKERS.issubset(normed) or _norm_col(tname) == "masterdb":
                    continue
                chosen = tname
                code_col, weight_col = cc, wc
                rows_out = batch
                break

        if not chosen or not code_col or not weight_col:
            raise RuntimeError(
                f"'{path.name}' has no product code + weight table. "
                f"Tables found: {', '.join(tables)}. "
                "MasterDb is weigh slips only (ItemType/FWeight/SWeight). "
                "Use: python import_product_weights.py --fmye"
            )
        return chosen, code_col, weight_col, rows_out


def read_csv_rows(path: Path) -> tuple[str, str, str, list[dict]]:
    import pandas as pd

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    cols = list(df.columns)
    code_col = _pick_column(cols, CODE_HINTS, "code")
    weight_col = _pick_column(cols, WEIGHT_HINTS, "standard")
    if not code_col or not weight_col:
        raise RuntimeError(f"CSV needs code and weight columns. Found: {cols}")
    return "csv", code_col, weight_col, df.to_dict(orient="records")


def _parse_weight(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if not s:
        return None
    try:
        w = float(s)
        # Only treat as "weight available" when greater than zero
        return w if w > 0 else None
    except ValueError:
        return None


def extract_code_weight_rows(
    raw_rows: list[dict], code_col: str, weight_col: str
) -> tuple[list[tuple[str, float]], dict]:
    """Keep only rows that have both product code and a positive weight in the source file."""
    out = []
    seen = set()
    stats = {
        "access_rows": len(raw_rows),
        "skipped_no_code": 0,
        "skipped_no_weight": 0,
        "duplicate_code": 0,
    }
    for rec in raw_rows:
        code = str(rec.get(code_col) or "").strip()
        if not code:
            stats["skipped_no_code"] += 1
            continue
        w = _parse_weight(rec.get(weight_col))
        if w is None:
            stats["skipped_no_weight"] += 1
            continue
        key = code.upper()
        if key in seen:
            stats["duplicate_code"] += 1
            continue
        seen.add(key)
        out.append((code, w))
    return out, stats


def apply_weights(
    pairs: list[tuple[str, float]],
    *,
    dry_run: bool = False,
    user_id: int | None = None,
) -> dict:
    import database as db

    stats = {
        "source_rows": len(pairs),
        "updated": 0,
        "skipped_no_product": 0,
        "not_found_codes": [],
    }
    if not pairs:
        return stats

    with db.get_connection() as conn:
        by_code = {}
        for r in conn.execute("SELECT id, code FROM products").fetchall():
            by_code[str(r[1]).strip().upper()] = (r[0], r[1])

        for code, weight in pairs:
            hit = by_code.get(code.upper())
            if not hit:
                stats["skipped_no_product"] += 1
                if len(stats["not_found_codes"]) < 50:
                    stats["not_found_codes"].append(code)
                continue
            pid, erp_code = hit
            if dry_run:
                stats["updated"] += 1
                continue
            conn.execute(
                """UPDATE products SET standard_weight=?, modified_by=?, modified_at=?
                   WHERE id=?""",
                (weight, user_id, db._now(), pid),
            )
            stats["updated"] += 1

    return stats


def fmye_inward_detail_status(export_dir: Path | None = None) -> str:
    """Human-readable status for FMYE InwardDetail / 767.dat."""
    from import_fmye_from_dat import FMYEExport

    folder = export_dir or DEFAULT_FMYE_DIR
    exp = FMYEExport(folder)
    info = exp.table_map().get("InwardDetail")
    if not info:
        return f"No InwardDetail table mapping in {folder}/reload.sql."
    dat: Path = info["dat"]
    if not dat.exists():
        return f"Missing {dat.name} — re-run dbunload on FMYE11.db and copy 767.dat into {folder}."
    if dat.stat().st_size == 0:
        return (
            f"{dat.name} exists but is empty (0 bytes). "
            "Live FMYE InwardDetail is also empty on this PC — standard weights are not in that table."
        )
    n = len(exp.rows("InwardDetail"))
    return f"InwardDetail has {n} lines in export."


def write_weight_template_csv(path: Path) -> int:
    """CSV template: code, name, standard_weight (fill column 3 and re-import)."""
    import csv
    import database as db

    path.parent.mkdir(parents=True, exist_ok=True)
    with db.get_connection() as conn, path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ItemCode", "ItemName", "standard_weight"])
        rows = conn.execute(
            """SELECT code, name, COALESCE(standard_weight, 0)
               FROM products WHERE is_active=1 ORDER BY code"""
        ).fetchall()
        for code, name, sw in rows:
            w.writerow([code, name, sw])
    return len(rows)


def load_weights_from_fmye(export_dir: Path | None = None) -> tuple[list[tuple[str, float]], dict]:
    """ItemCode + StandardWeight from FMYE InwardDetail (max StandardWeight per code)."""
    from import_fmye_from_dat import FMYEExport

    folder = export_dir or DEFAULT_FMYE_DIR
    exp = FMYEExport(folder)
    info = exp.table_map().get("InwardDetail")
    if info:
        dat = info["dat"]
        if dat.exists() and dat.stat().st_size == 0:
            raise FileNotFoundError(
                "FMYE InwardDetail (767.dat) is empty. This database does not hold product "
                "standard weights in InwardDetail. Export a CSV with ItemCode + standard_weight "
                "from wherever weights are kept, or fill the ERP template CSV."
            )
    rows = exp.rows("InwardDetail")
    if not rows:
        raise FileNotFoundError(
            f"No InwardDetail rows in {folder}. {fmye_inward_detail_status(folder)}"
        )
    by_code: dict[str, tuple[str, float]] = {}
    skipped_no_weight = 0
    skipped_no_code = 0
    for r in rows:
        code = str(r.get("ItemCode") or "").strip()
        if not code:
            skipped_no_code += 1
            continue
        w = _parse_weight(r.get("StandardWeight"))
        if w is None:
            skipped_no_weight += 1
            continue
        key = code.upper()
        if w > by_code.get(key, ("", 0))[1]:
            by_code[key] = (code, w)
    pairs = [by_code[k] for k in sorted(by_code.keys())]
    ex = {
        "access_rows": len(rows),
        "skipped_no_code": skipped_no_code,
        "skipped_no_weight": skipped_no_weight,
        "duplicate_code": 0,
        "source": "FMYE InwardDetail",
    }
    return pairs, ex


def load_weights_from_sales_inventory(
    accdb: Path | None = None,
) -> tuple[list[tuple[str, float]], dict]:
    """tblProduct: ProductID + Weight from Sales & Inventory Management .accdb."""
    path = resolve_sales_weights_accdb(accdb)
    if not path.exists():
        raise FileNotFoundError(f"Access file not found: {path}")
    _tbl, _cc, _wc, raw = read_access_rows(path, DEFAULT_ACCDB_TABLE)
    pairs, extract_stats = extract_code_weight_rows(
        raw, DEFAULT_ACCDB_CODE_COL, DEFAULT_ACCDB_WEIGHT_COL
    )
    extract_stats["source"] = str(path)
    extract_stats["table"] = _tbl
    return pairs, extract_stats


def load_pairs(
    *,
    accdb: Path | None,
    csv_path: Path | None,
    table: str | None,
    code_col: str | None,
    weight_col: str | None,
) -> tuple[str, str, str, list[tuple[str, float]], dict]:
    if csv_path:
        src, cc, wc, raw = read_csv_rows(csv_path)
    else:
        path = accdb or DEFAULT_ACCDB
        if not path.exists():
            raise FileNotFoundError(f"Access file not found: {path}")
        src, cc, wc, raw = read_access_rows(path, table)
        if code_col:
            cc = code_col
        if weight_col:
            wc = weight_col
    pairs, extract_stats = extract_code_weight_rows(raw, cc, wc)
    return src, cc, wc, pairs, extract_stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import product standard weights by code")
    ap.add_argument("--fmye", action="store_true", help="Load ItemCode+StandardWeight from FMYE InwardDetail")
    ap.add_argument("--fmye-dir", type=Path, default=DEFAULT_FMYE_DIR, help="FMYE export folder")
    ap.add_argument("--apply", action="store_true", help="Write to database (default is dry-run)")
    ap.add_argument("--path", type=Path, default=DEFAULT_ACCDB, help="Path to .accdb (if it has code+weight)")
    ap.add_argument("--csv", type=Path, help="CSV with code + weight columns")
    ap.add_argument("--table", help="Access table name")
    ap.add_argument("--code-col", help="Column name for product code")
    ap.add_argument("--weight-col", help="Column name for standard weight")
    ap.add_argument("--dry-run", action="store_true", help="Preview only (default unless --apply)")
    ap.add_argument("--list-tables", action="store_true", help="List Access tables and exit")
    args = ap.parse_args(argv)
    dry_run = not args.apply

    if args.list_tables:
        tables = list_access_tables(args.path)
        print(f"Tables in {args.path}:")
        for t in tables:
            print(f"  {t}")
        return 0

    if args.fmye:
        pairs, ex = load_weights_from_fmye(args.fmye_dir)
        src, cc, wc = ex.get("source", "FMYE"), "ItemCode", "StandardWeight"
    elif args.csv:
        src, cc, wc, pairs, ex = load_pairs(
            accdb=None,
            csv_path=args.csv,
            table=args.table,
            code_col=args.code_col,
            weight_col=args.weight_col,
        )
    else:
        # Default: Sales Software weights (ProductID = FMYE ItemCode, Weight kg)
        path = resolve_sales_weights_accdb(args.path if args.path != DEFAULT_ACCDB else None)
        pairs, ex = load_weights_from_sales_inventory(path)
        src = ex.get("source", str(path))
        cc, wc = DEFAULT_ACCDB_CODE_COL, DEFAULT_ACCDB_WEIGHT_COL
    print(f"Source: {src} | Code: {cc} | Weight: {wc}")
    print(f"Rows read: {ex['access_rows']} | With code+weight: {len(pairs)}")
    print(f"Skipped (no weight): {ex['skipped_no_weight']}")
    stats = apply_weights(pairs, dry_run=dry_run)
    print(f"{'Would update' if dry_run else 'Updated'}: {stats['updated']} | Code not in ERP: {stats['skipped_no_product']}")
    if stats["not_found_codes"]:
        print("Sample codes not in ERP:", ", ".join(stats["not_found_codes"][:15]))
    if dry_run:
        print("Add --apply to save.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
