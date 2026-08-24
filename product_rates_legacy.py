"""
Resolve product sale/purchase rates when ERP master prices are zero.

Sources (in priority order for invoice lines with a customer/supplier):
  1. Last rate / Disc % on ERP sales/purchase invoice lines for that party
  2. Product master (sale_price / purchase_price)
  3. Last rate on any ERP invoice line
  4. FMYE ItemInformation (SaleRate / PurchaseRate)
  5. Last rate on FMYE SaleInvoiceDetail / PurchaseDetail
  6. Sales & Inventory Management .accdb (if installed)
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
FMYE_DIR = ROOT / "import" / "fmye" / "full"
DEFAULT_ACCDB = Path(
    r"c:\IFS\DataBase\26.12.2021 work\DataBase File"
    r"\SALES AND INVENTORY MANAGEMENT SOFTWARE_be.accdb"
)

CODE_HINTS = (
    "itemcode", "productcode", "productid", "code", "item_code", "product_code",
    "prcode", "sku", "partno",
)
SALE_RATE_HINTS = (
    "saleprice", "salerate", "sellingprice", "retailprice", "salesrate", "sale_rate",
)
PURCHASE_RATE_HINTS = (
    "purchaseprice", "purchaserate", "costprice", "buyingrate", "purchase_rate",
)


def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _pick_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    best, best_score = None, -1
    for col in columns:
        n = _norm_col(col)
        score = 100 if n in hints else (50 if any(h in n for h in hints) else 0)
        if score > best_score:
            best_score, best = score, col
    return best


def _f(val, default=0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(str(val).replace(",", ""))
    except ValueError:
        return default


class _RateCache:
    __slots__ = (
        "fmye_master_sale", "fmye_master_purchase",
        "fmye_last_sale", "fmye_last_purchase",
        "erp_last_sale", "erp_last_purchase",
        "erp_party_sale", "erp_party_purchase",
        "erp_party_sale_meta", "erp_party_purchase_meta",
        "erp_party_sale_disc", "erp_party_purchase_disc",
        "erp_party_sale_header_disc", "erp_party_purchase_header_disc",
        "accdb_sale", "accdb_purchase",
        "loaded_fmye", "loaded_erp", "loaded_accdb",
    )

    def __init__(self):
        self.fmye_master_sale: dict[str, float] = {}
        self.fmye_master_purchase: dict[str, float] = {}
        self.fmye_last_sale: dict[str, float] = {}
        self.fmye_last_purchase: dict[str, float] = {}
        self.erp_last_sale: dict[int, float] = {}
        self.erp_last_purchase: dict[int, float] = {}
        self.erp_party_sale: dict[tuple[int, int], float] = {}
        self.erp_party_purchase: dict[tuple[int, int], float] = {}
        self.erp_party_sale_meta: dict[tuple[int, int], dict] = {}
        self.erp_party_purchase_meta: dict[tuple[int, int], dict] = {}
        self.erp_party_sale_disc: dict[tuple[int, int], float] = {}
        self.erp_party_purchase_disc: dict[tuple[int, int], float] = {}
        self.erp_party_sale_header_disc: dict[int, float] = {}
        self.erp_party_purchase_header_disc: dict[int, float] = {}
        self.accdb_sale: dict[str, float] = {}
        self.accdb_purchase: dict[str, float] = {}
        self.loaded_fmye = False
        self.loaded_erp = False
        self.loaded_accdb = False


_CACHE: _RateCache | None = None


def _cache() -> _RateCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = _RateCache()
    return _CACHE


def clear_rate_cache():
    global _CACHE
    _CACHE = None


def _implied_line_discount_pct(
    qty, rate, line_discount=0.0, amount=0.0, header_disc=0.0,
) -> float:
    """
    Line Disc % from invoice history.
    Prefer line_discount amount; else imply from amount vs qty*rate
    (FMYE / distributor invoices often store net amount with line_discount=0);
    else header discount %.
    """
    qty = float(qty or 0)
    rate = float(rate or 0)
    disc_amt = float(line_discount or 0)
    amount = float(amount or 0)
    header_disc = float(header_disc or 0)
    gross = qty * rate
    if gross > 0.0001:
        if disc_amt > 0.0001:
            pct = disc_amt / gross * 100.0
        elif amount > 0 and amount + 0.01 < gross:
            pct = (1.0 - amount / gross) * 100.0
        elif header_disc > 0:
            pct = header_disc
        else:
            return 0.0
        pct = min(100.0, max(0.0, pct))
        pct = round(pct, 2)
        if abs(pct - round(pct)) < 0.005:
            pct = float(round(pct))
        return pct
    if header_disc > 0:
        return round(min(100.0, max(0.0, header_disc)), 2)
    return 0.0


def _load_fmye(c: _RateCache):
    if c.loaded_fmye:
        return
    c.loaded_fmye = True
    if not (FMYE_DIR / "reload.sql").exists():
        return
    try:
        from import_fmye_from_dat import FMYEExport
    except ImportError:
        return
    exp = FMYEExport(FMYE_DIR)
    for row in exp.rows("ItemInformation"):
        code = (row.get("ItemCode") or "").strip().upper()
        if not code:
            continue
        sp = _f(row.get("SaleRate"))
        pp = _f(row.get("PurchaseRate"))
        if sp > 0:
            c.fmye_master_sale[code] = sp
        if pp > 0:
            c.fmye_master_purchase[code] = pp

    sale_dates: dict[str, str] = {}
    for h in exp.rows("SaleInvoiceHeader"):
        key = (h.get("SaleInvoiceCode") or "").strip()
        if key:
            sale_dates[key] = str(h.get("InvoiceDate") or "")

    sale_dt_by_code: dict[str, str] = {}
    for ln in exp.rows("SaleInvoiceDetail"):
        code = (ln.get("ItemCode") or "").strip().upper()
        rate = _f(ln.get("SaleRate"))
        if not code or rate <= 0:
            continue
        inv = (ln.get("SaleInvoiceCode") or "").strip()
        dt = sale_dates.get(inv, "")
        if code not in sale_dt_by_code or dt >= sale_dt_by_code[code]:
            sale_dt_by_code[code] = dt
            c.fmye_last_sale[code] = rate

    purch_dates: dict[str, str] = {}
    for h in exp.rows("PurchaseHeader"):
        key = (h.get("PurchaseInvoiceCode") or "").strip()
        if key:
            purch_dates[key] = str(h.get("InvoiceDate") or "")

    purch_dt_by_code: dict[str, str] = {}
    for ln in exp.rows("PurchaseDetail"):
        code = (ln.get("ItemCode") or "").strip().upper()
        rate = _f(ln.get("PurchaseRate"))
        if not code or rate <= 0:
            continue
        inv = (ln.get("PurchaseInvoiceCode") or "").strip()
        dt = purch_dates.get(inv, "")
        if code not in purch_dt_by_code or dt >= purch_dt_by_code[code]:
            purch_dt_by_code[code] = dt
            c.fmye_last_purchase[code] = rate


def _load_erp(c: _RateCache):
    if c.loaded_erp:
        return
    c.loaded_erp = True
    from database import get_connection

    with get_connection() as conn:
        for row in conn.execute(
            """SELECT si.product_id, si.rate, si.quantity, si.amount,
                      COALESCE(si.line_discount, 0) AS line_discount,
                      s.customer_id, COALESCE(s.discount_pct, 0) AS header_disc,
                      s.invoice_date, s.document_no, si.id
               FROM sales_invoice_items si
               JOIN sales_invoices s ON s.id = si.invoice_id
               WHERE COALESCE(s.status, 'draft') = 'approved'
               ORDER BY s.invoice_date DESC, si.id DESC"""
        ).fetchall():
            pid = row["product_id"]
            rate = float(row["rate"] or 0)
            qty = float(row["quantity"] or 0)
            amount = float(row["amount"] or 0)
            cid = row["customer_id"]
            disc_amt = float(row["line_discount"] or 0)
            header_disc = float(row["header_disc"] or 0)
            inv_date = str(row["invoice_date"] or "")[:10]
            doc_no = row["document_no"] or ""
            # Only treat explicit line_discount as a real Disc % for future defaults.
            # Do not imply % from amount < qty*rate (FMYE nets) — that auto-applied unwanted 5%.
            gross = qty * rate
            disc_pct = (
                round(min(100.0, max(0.0, disc_amt / gross * 100.0)), 2)
                if disc_amt > 0.0001 and gross > 0.0001
                else 0.0
            )
            if rate > 0:
                if pid not in c.erp_last_sale:
                    c.erp_last_sale[pid] = rate
                key = (pid, cid)
                if key not in c.erp_party_sale:
                    c.erp_party_sale[key] = rate
                    c.erp_party_sale_meta[key] = {
                        "rate": rate, "date": inv_date, "document_no": doc_no,
                        "discount_pct": disc_pct,
                    }
            key = (pid, cid)
            if key not in c.erp_party_sale_disc and disc_pct > 0:
                c.erp_party_sale_disc[key] = disc_pct
            if cid not in c.erp_party_sale_header_disc:
                c.erp_party_sale_header_disc[cid] = header_disc

        for row in conn.execute(
            """SELECT pi.product_id, pi.rate, pi.quantity, pi.amount,
                      COALESCE(pi.line_discount, 0) AS line_discount,
                      p.supplier_id, COALESCE(p.discount_pct, 0) AS header_disc,
                      p.invoice_date, p.document_no, pi.id
               FROM purchase_invoice_items pi
               JOIN purchase_invoices p ON p.id = pi.invoice_id
               WHERE COALESCE(p.status, 'draft') = 'approved'
               ORDER BY p.invoice_date DESC, pi.id DESC"""
        ).fetchall():
            pid = row["product_id"]
            rate = float(row["rate"] or 0)
            qty = float(row["quantity"] or 0)
            amount = float(row["amount"] or 0)
            sid = row["supplier_id"]
            disc_amt = float(row["line_discount"] or 0)
            header_disc = float(row["header_disc"] or 0)
            inv_date = str(row["invoice_date"] or "")[:10]
            doc_no = row["document_no"] or ""
            gross = qty * rate
            disc_pct = (
                round(min(100.0, max(0.0, disc_amt / gross * 100.0)), 2)
                if disc_amt > 0.0001 and gross > 0.0001
                else 0.0
            )
            if rate > 0:
                if pid not in c.erp_last_purchase:
                    c.erp_last_purchase[pid] = rate
                key = (pid, sid)
                if key not in c.erp_party_purchase:
                    c.erp_party_purchase[key] = rate
                    c.erp_party_purchase_meta[key] = {
                        "rate": rate, "date": inv_date, "document_no": doc_no,
                        "discount_pct": disc_pct,
                    }
            key = (pid, sid)
            if key not in c.erp_party_purchase_disc and disc_pct > 0:
                c.erp_party_purchase_disc[key] = disc_pct
            if sid not in c.erp_party_purchase_header_disc:
                c.erp_party_purchase_header_disc[sid] = header_disc

        for row in conn.execute(
            """SELECT customer_id, COALESCE(discount_pct, 0) AS header_disc
               FROM sales_invoices
               WHERE COALESCE(status, 'draft') = 'approved'
               ORDER BY invoice_date DESC, id DESC"""
        ).fetchall():
            cid = row["customer_id"]
            if cid not in c.erp_party_sale_header_disc:
                c.erp_party_sale_header_disc[cid] = float(row["header_disc"] or 0)
        for row in conn.execute(
            """SELECT supplier_id, COALESCE(discount_pct, 0) AS header_disc
               FROM purchase_invoices
               WHERE COALESCE(status, 'draft') = 'approved'
               ORDER BY invoice_date DESC, id DESC"""
        ).fetchall():
            sid = row["supplier_id"]
            if sid not in c.erp_party_purchase_header_disc:
                c.erp_party_purchase_header_disc[sid] = float(row["header_disc"] or 0)


def _load_accdb(c: _RateCache, path: Path | None = None):
    if c.loaded_accdb:
        return
    c.loaded_accdb = True
    acc_path = path or DEFAULT_ACCDB
    if not acc_path.exists():
        return
    try:
        import pyodbc
        from import_product_weights import _access_driver, list_access_tables
    except Exception:
        return
    try:
        cs = f"DRIVER={{{_access_driver()}}};DBQ={acc_path};"
        with pyodbc.connect(cs) as conn:
            cur = conn.cursor()
            for tname in list_access_tables(acc_path):
                tl = tname.lower()
                if not any(x in tl for x in ("item", "product", "material", "stock")):
                    continue
                try:
                    cur.execute(f"SELECT * FROM [{tname}]")
                except Exception:
                    continue
                cols = [d[0] for d in cur.description]
                cc = _pick_column(cols, CODE_HINTS)
                sc = _pick_column(cols, SALE_RATE_HINTS)
                pc = _pick_column(cols, PURCHASE_RATE_HINTS)
                if not cc or (not sc and not pc):
                    continue
                for row in cur.fetchall():
                    rec = {cols[i]: row[i] for i in range(len(cols))}
                    code = str(rec.get(cc) or "").strip().upper()
                    if not code:
                        continue
                    if sc:
                        r = _f(rec.get(sc))
                        if r > 0:
                            c.accdb_sale[code] = r
                    if pc:
                        r = _f(rec.get(pc))
                        if r > 0:
                            c.accdb_purchase[code] = r
                if c.accdb_sale or c.accdb_purchase:
                    break
    except Exception:
        pass


def get_last_party_rate_info(
    product,
    kind: str = "sale",
    party_id: int | None = None,
) -> dict | None:
    """
    Last approved invoice rate for this product + customer/supplier.
    Returns {"rate", "date", "document_no"} or None.
    """
    if not product or not party_id:
        return None
    kind = "purchase" if kind == "purchase" else "sale"
    pid = product.get("id")
    if not pid:
        return None
    c = _cache()
    _load_erp(c)
    key = (int(pid), int(party_id))
    meta_map = c.erp_party_sale_meta if kind == "sale" else c.erp_party_purchase_meta
    meta = meta_map.get(key)
    if meta and float(meta.get("rate") or 0) > 0:
        disc_map = c.erp_party_sale_disc if kind == "sale" else c.erp_party_purchase_disc
        disc = meta.get("discount_pct")
        if disc is None:
            disc = disc_map.get(key, 0)
        return {
            "rate": float(meta["rate"]),
            "date": str(meta.get("date") or "")[:10],
            "document_no": meta.get("document_no") or "",
            "discount_pct": float(disc or 0),
        }
    rate_map = c.erp_party_sale if kind == "sale" else c.erp_party_purchase
    if key in rate_map and float(rate_map[key] or 0) > 0:
        disc_map = c.erp_party_sale_disc if kind == "sale" else c.erp_party_purchase_disc
        return {
            "rate": float(rate_map[key]),
            "date": "",
            "document_no": "",
            "discount_pct": float(disc_map.get(key, 0) or 0),
        }
    return None


def resolve_product_rate(
    product,
    kind: str = "sale",
    party_id: int | None = None,
    accdb_path: Path | None = None,
    prefer_party: bool = True,
) -> tuple[float, str]:
    """
    Return (rate, source_label) for a product dict (id, code, sale_price, purchase_price).
    kind: 'sale' or 'purchase'
    When party_id is set and prefer_party=True, last invoice rate for that
    customer/supplier wins over product master price.
    """
    if not product:
        return 0.0, ""
    kind = "purchase" if kind == "purchase" else "sale"
    pid = product.get("id")
    code = (product.get("code") or "").strip().upper()
    master = float(
        product.get("purchase_price" if kind == "purchase" else "sale_price") or 0
    )

    c = _cache()
    _load_erp(c)
    _load_fmye(c)
    if not c.loaded_accdb:
        _load_accdb(c, accdb_path)

    if prefer_party and pid and party_id:
        party_key = (int(pid), int(party_id))
        party_map = c.erp_party_sale if kind == "sale" else c.erp_party_purchase
        if party_key in party_map:
            return party_map[party_key], "last invoice (party)"

    if master > 0:
        return master, "product"

    if pid and party_id and not prefer_party:
        party_key = (int(pid), int(party_id))
        party_map = c.erp_party_sale if kind == "sale" else c.erp_party_purchase
        if party_key in party_map:
            return party_map[party_key], "last invoice (party)"

    if pid:
        last_map = c.erp_last_sale if kind == "sale" else c.erp_last_purchase
        if pid in last_map:
            return last_map[pid], "last invoice"

    if code:
        fmye_master = c.fmye_master_sale if kind == "sale" else c.fmye_master_purchase
        if code in fmye_master:
            return fmye_master[code], "FMYE item master"

        fmye_last = c.fmye_last_sale if kind == "sale" else c.fmye_last_purchase
        if code in fmye_last:
            return fmye_last[code], "FMYE last invoice"

        accdb_map = c.accdb_sale if kind == "sale" else c.accdb_purchase
        if code in accdb_map:
            return accdb_map[code], "old Access DB"

    return 0.0, ""


def resolve_product_discount_pct(
    product,
    kind: str = "sale",
    party_id: int | None = None,
    header_default: float = 0.0,
) -> tuple[float, str]:
    """
    Last Disc % for product + customer/supplier from ERP invoices.
    Falls back to last header discount for the party, then header_default.
    """
    if not product or not party_id:
        return max(0.0, min(100.0, float(header_default or 0))), "header"
    kind = "purchase" if kind == "purchase" else "sale"
    pid = product.get("id")
    c = _cache()
    _load_erp(c)
    if pid:
        key = (int(pid), int(party_id))
        disc_map = c.erp_party_sale_disc if kind == "sale" else c.erp_party_purchase_disc
        if key in disc_map:
            return float(disc_map[key]), "last invoice (party item)"
    header_map = (
        c.erp_party_sale_header_disc if kind == "sale" else c.erp_party_purchase_header_disc
    )
    if int(party_id) in header_map:
        return float(header_map[int(party_id)]), "last invoice (party)"
    return max(0.0, min(100.0, float(header_default or 0))), "header"


def get_last_party_header_discount(party_id: int | None, kind: str = "sale") -> float:
    """Last invoice header Discount % for a customer (sale) or supplier (purchase)."""
    if not party_id:
        return 0.0
    kind = "purchase" if kind == "purchase" else "sale"
    c = _cache()
    _load_erp(c)
    header_map = (
        c.erp_party_sale_header_disc if kind == "sale" else c.erp_party_purchase_header_disc
    )
    return float(header_map.get(int(party_id), 0.0) or 0.0)


def lookup_discounts_from_last_invoices(
    party_id: int | None,
    product_ids: list[int] | None = None,
    *,
    kind: str = "sale",
) -> dict:
    """
    For the manual "Apply discounts from last invoices" button.
    Returns {"header_pct": float, "by_product": {product_id: pct}}.
    Includes implied Disc % when last line amount < qty×rate (FMYE-style nets).
    """
    out = {"header_pct": 0.0, "by_product": {}}
    if not party_id:
        return out
    kind = "purchase" if kind == "purchase" else "sale"
    from database import get_connection

    want = {int(p) for p in (product_ids or []) if p}
    with get_connection() as conn:
        if kind == "sale":
            hdr = conn.execute(
                """SELECT COALESCE(discount_pct, 0) AS header_disc
                   FROM sales_invoices
                   WHERE customer_id=? AND LOWER(COALESCE(status,''))='approved'
                   ORDER BY invoice_date DESC, id DESC LIMIT 1""",
                (party_id,),
            ).fetchone()
            out["header_pct"] = float(hdr[0] or 0) if hdr else 0.0
            rows = conn.execute(
                """SELECT si.product_id, si.quantity, si.rate, si.amount,
                          COALESCE(si.line_discount, 0) AS line_discount,
                          COALESCE(s.discount_pct, 0) AS header_disc
                   FROM sales_invoice_items si
                   JOIN sales_invoices s ON s.id = si.invoice_id
                   WHERE s.customer_id=? AND LOWER(COALESCE(s.status,''))='approved'
                   ORDER BY s.invoice_date DESC, si.id DESC""",
                (party_id,),
            ).fetchall()
        else:
            hdr = conn.execute(
                """SELECT COALESCE(discount_pct, 0) AS header_disc
                   FROM purchase_invoices
                   WHERE supplier_id=? AND LOWER(COALESCE(status,''))='approved'
                   ORDER BY invoice_date DESC, id DESC LIMIT 1""",
                (party_id,),
            ).fetchone()
            out["header_pct"] = float(hdr[0] or 0) if hdr else 0.0
            rows = conn.execute(
                """SELECT pi.product_id, pi.quantity, pi.rate, pi.amount,
                          COALESCE(pi.line_discount, 0) AS line_discount,
                          COALESCE(p.discount_pct, 0) AS header_disc
                   FROM purchase_invoice_items pi
                   JOIN purchase_invoices p ON p.id = pi.invoice_id
                   WHERE p.supplier_id=? AND LOWER(COALESCE(p.status,''))='approved'
                   ORDER BY p.invoice_date DESC, pi.id DESC""",
                (party_id,),
            ).fetchall()

        seen = set()
        for row in rows:
            pid = int(row["product_id"] or 0)
            if not pid or pid in seen:
                continue
            if want and pid not in want:
                continue
            seen.add(pid)
            pct = _implied_line_discount_pct(
                row["quantity"], row["rate"], row["line_discount"],
                row["amount"], row["header_disc"],
            )
            if pct > 0.0001:
                out["by_product"][pid] = float(pct)
            if want and len(seen) >= len(want):
                break
    return out

def sync_missing_product_rates(user_id: int | None = None, dry_run: bool = False) -> dict:
    """Fill products.sale_price / purchase_price from legacy sources when zero."""
    from database import get_connection, _now

    c = _cache()
    _load_erp(c)
    _load_fmye(c)
    _load_accdb(c)
    stats = {"sale_updated": 0, "purchase_updated": 0, "skipped": 0}
    ts = _now()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, code, sale_price, purchase_price FROM products WHERE is_active=1"""
        ).fetchall()
        for row in rows:
            prod = dict(row)
            updates = []
            params = []
            if float(prod.get("sale_price") or 0) <= 0:
                rate, src = resolve_product_rate(prod, "sale", prefer_party=False)
                if rate > 0:
                    updates.append("sale_price=?")
                    params.append(rate)
                    stats["sale_updated"] += 1
            if float(prod.get("purchase_price") or 0) <= 0:
                rate, src = resolve_product_rate(prod, "purchase", prefer_party=False)
                if rate > 0:
                    updates.append("purchase_price=?")
                    params.append(rate)
                    stats["purchase_updated"] += 1
            if not updates:
                stats["skipped"] += 1
                continue
            if dry_run:
                continue
            params.extend([user_id, ts, prod["id"]])
            conn.execute(
                f"UPDATE products SET {', '.join(updates)}, modified_by=?, modified_at=? WHERE id=?",
                params,
            )
    return stats
