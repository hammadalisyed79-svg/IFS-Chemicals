"""Dispatch planning — aggregate open/partial sales orders for production & loading."""

from __future__ import annotations

import re
from datetime import date, timedelta

from database import get_connection, rows_to_list


def _effective_kg_factor_sql(product_alias: str = "p", unit_alias: str = "u") -> str:
    """SQL: kg per order qty.

    Uses ``standard_weight`` when set; otherwise 1 (qty already treated as net kg),
    matching invoice ``enrich_line_weights`` / auto net-weight behaviour.
    """
    p = product_alias
    return f"""CASE
        WHEN COALESCE({p}.standard_weight, 0) > 0.0000001 THEN {p}.standard_weight
        ELSE 1.0
    END"""


def effective_unit_kg(standard_weight=0, unit_symbol: str = "", weight_unit: str = "") -> float:
    """Python twin of ``_effective_kg_factor_sql`` for aggregates."""
    sw = float(standard_weight or 0)
    if sw > 0.0000001:
        return sw
    return 1.0


# Patterns for free-text destinations in SO / portal notes
_DELIVER_TO_RE = re.compile(
    r"(?:deliver(?:y)?|delever|dispatch)\s+to\s+([A-Za-z][A-Za-z0-9 .'/&-]{1,40})",
    re.IGNORECASE,
)
_PLACE_ORDER_RE = re.compile(
    r"\b([A-Za-z][A-Za-z]{2,30})\s+order\b",
    re.IGNORECASE,
)
# Noise words that look like place names but aren't destinations
_NOISE_PLACES = frozenset({
    "portal", "sales", "purchase", "customer", "please", "urgent", "partial",
    "pending", "delivery", "dispatch", "order", "orders", "this", "that",
    "from", "with", "your", "their", "cash", "credit", "invoice",
})


def resolve_dispatch_to(notes: str | None = None, city: str | None = None) -> str:
    """Extract a short Dispatch To label from notes, else customer city."""
    text = (notes or "").strip()
    if text:
        m = _DELIVER_TO_RE.search(text)
        if m:
            place = _clean_place(m.group(1))
            if place:
                return place
        for m in _PLACE_ORDER_RE.finditer(text):
            place = _clean_place(m.group(1))
            if place and place.lower() not in _NOISE_PLACES:
                return place
    city_clean = (city or "").strip()
    if city_clean:
        return city_clean.title() if city_clean.isupper() or city_clean.islower() else city_clean
    return "-"


def _clean_place(raw: str) -> str:
    place = (raw or "").strip(" .|,;:-")
    # Stop at note separators
    for sep in ("|", "·", ";", ","):
        if sep in place:
            place = place.split(sep, 1)[0].strip()
    place = re.sub(r"\s+", " ", place)
    if len(place) < 2:
        return ""
    # Title-case short place names; keep existing casing for multi-word if mixed
    if place.isupper() or place.islower():
        return place.title()
    return place


def list_dispatch_sales_orders(
    statuses=("open", "partial"),
    *,
    delivery_from: str | None = None,
    delivery_to: str | None = None,
) -> list[dict]:
    """Open/partial SOs with pending qty/kg and resolved Dispatch To."""
    statuses = tuple(statuses or ("open", "partial"))
    placeholders = ",".join("?" * len(statuses))
    params: list = list(statuses)
    date_clause = ""
    # Prefer delivery_date when present; else order_date for window filter
    if delivery_from:
        date_clause += " AND COALESCE(so.delivery_date, so.order_date) >= ?"
        params.append(str(delivery_from)[:10])
    if delivery_to:
        date_clause += " AND COALESCE(so.delivery_date, so.order_date) <= ?"
        params.append(str(delivery_to)[:10])

    with get_connection() as conn:
        # Ensure optional columns exist on older DBs
        try:
            conn.execute("SELECT delivery_date FROM sales_orders LIMIT 1")
        except Exception:
            try:
                conn.execute("ALTER TABLE sales_orders ADD COLUMN delivery_date TEXT")
            except Exception:
                pass
        try:
            conn.execute("SELECT city FROM customers LIMIT 1")
        except Exception:
            pass

        kg_factor = _effective_kg_factor_sql("p", "u")
        rows = rows_to_list(conn.execute(
            f"""
            SELECT so.id, so.document_no, so.order_date, so.delivery_date, so.status,
                   so.total, so.notes, so.customer_id, so.dispatch_town,
                   c.name AS customer_name, c.code AS customer_code,
                   COALESCE(c.city, '') AS customer_city,
                   COALESCE(SUM(soi.quantity), 0) AS ordered_qty,
                   COALESCE(SUM(COALESCE(soi.delivered_qty, 0)), 0) AS delivered_qty,
                   COALESCE(SUM(
                       CASE WHEN soi.quantity > COALESCE(soi.delivered_qty, 0)
                            THEN soi.quantity - COALESCE(soi.delivered_qty, 0)
                            ELSE 0 END
                   ), 0) AS pending_qty,
                   COALESCE(SUM(
                       CASE WHEN soi.quantity > COALESCE(soi.delivered_qty, 0)
                            THEN (soi.quantity - COALESCE(soi.delivered_qty, 0))
                                 * ({kg_factor})
                            ELSE 0 END
                   ), 0) AS pending_kg,
                   COUNT(DISTINCT soi.product_id) AS line_count
            FROM sales_orders so
            JOIN customers c ON c.id = so.customer_id
            LEFT JOIN sales_order_items soi ON soi.order_id = so.id
            LEFT JOIN products p ON p.id = soi.product_id
            LEFT JOIN units_of_measure u ON u.id = p.unit_id
            WHERE LOWER(COALESCE(so.status, '')) IN ({placeholders})
              {date_clause}
            GROUP BY so.id
            HAVING pending_qty > 0.0001
            ORDER BY so.id DESC, COALESCE(so.delivery_date, so.order_date) DESC, so.document_no DESC
            """,
            params,
        ).fetchall())

    for r in rows:
        town = (r.get("dispatch_town") or "").strip()
        r["dispatch_to"] = town or resolve_dispatch_to(r.get("notes"), r.get("customer_city"))
        r["pending_qty"] = round(float(r.get("pending_qty") or 0), 3)
        r["pending_kg"] = round(float(r.get("pending_kg") or 0), 3)
        r["ordered_qty"] = round(float(r.get("ordered_qty") or 0), 3)
        r["delivered_qty"] = round(float(r.get("delivered_qty") or 0), 3)
    return rows


def default_delivery_window(days_ahead: int = 7) -> tuple[str, str]:
    today = date.today()
    return today.isoformat(), (today + timedelta(days=days_ahead)).isoformat()


def aggregate_dispatch_requirements(order_ids: list[int]) -> list[dict]:
    """Combine pending lines across selected SOs by product."""
    ids = [int(x) for x in (order_ids or []) if x]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    from database import _product_stock_join, _product_stock_sql

    with get_connection() as conn:
        stk = _product_stock_join("p")
        sc = _product_stock_sql("p")
        rows = rows_to_list(conn.execute(
            f"""
            SELECT p.id AS product_id, p.code AS product_code, p.name AS product_name,
                   COALESCE(u.symbol, '') AS unit,
                   COALESCE(p.weight_unit, '') AS weight_unit,
                   COALESCE(p.standard_weight, 0) AS standard_weight,
                   COALESCE(SUM(soi.quantity), 0) AS ordered_qty,
                   COALESCE(SUM(COALESCE(soi.delivered_qty, 0)), 0) AS delivered_qty,
                   COALESCE(SUM(
                       CASE WHEN soi.quantity > COALESCE(soi.delivered_qty, 0)
                            THEN soi.quantity - COALESCE(soi.delivered_qty, 0)
                            ELSE 0 END
                   ), 0) AS pending_qty,
                   {sc} AS stock_qty
            FROM sales_order_items soi
            JOIN products p ON p.id = soi.product_id
            LEFT JOIN units_of_measure u ON p.unit_id = u.id
            {stk}
            WHERE soi.order_id IN ({placeholders})
            GROUP BY p.id
            HAVING pending_qty > 0.0001
            ORDER BY p.code COLLATE NOCASE
            """,
            ids,
        ).fetchall())

    out = []
    for r in rows:
        pending = round(float(r.get("pending_qty") or 0), 3)
        sw = effective_unit_kg(
            r.get("standard_weight"),
            r.get("unit") or "",
            r.get("weight_unit") or "",
        )
        stock = round(float(r.get("stock_qty") or 0), 3)
        pending_kg = round(pending * sw, 3)
        shortfall = round(max(0.0, pending - stock), 3) if pending > 0 else 0.0
        out.append({
            "product_id": r["product_id"],
            "product_code": r.get("product_code") or "",
            "product_name": r.get("product_name") or "",
            "unit": r.get("unit") or "",
            "standard_weight": float(r.get("standard_weight") or 0) or sw,
            "ordered_qty": round(float(r.get("ordered_qty") or 0), 3),
            "delivered_qty": round(float(r.get("delivered_qty") or 0), 3),
            "pending_qty": pending,
            "pending_kg": pending_kg,
            "stock_qty": stock,
            "shortfall_qty": shortfall,
        })
    return out


def summarize_by_destination(orders: list[dict]) -> list[dict]:
    """Group selected order rows by Dispatch To with kg/qty subtotals."""
    buckets: dict[str, dict] = {}
    for o in orders or []:
        key = (o.get("dispatch_to") or "-").strip() or "-"
        b = buckets.setdefault(key, {
            "dispatch_to": key,
            "order_count": 0,
            "pending_qty": 0.0,
            "pending_kg": 0.0,
            "customers": set(),
        })
        b["order_count"] += 1
        b["pending_qty"] += float(o.get("pending_qty") or 0)
        b["pending_kg"] += float(o.get("pending_kg") or 0)
        if o.get("customer_name"):
            b["customers"].add(o["customer_name"])
    out = []
    for b in buckets.values():
        out.append({
            "dispatch_to": b["dispatch_to"],
            "order_count": b["order_count"],
            "customer_count": len(b["customers"]),
            "pending_qty": round(b["pending_qty"], 3),
            "pending_kg": round(b["pending_kg"], 3),
        })
    out.sort(key=lambda x: (-x["pending_kg"], x["dispatch_to"]))
    return out


def dispatch_kpis(orders: list[dict]) -> dict:
    if not orders:
        return {
            "order_count": 0,
            "customer_count": 0,
            "pending_qty": 0.0,
            "pending_kg": 0.0,
            "earliest_delivery": None,
        }
    customers = {o.get("customer_id") for o in orders if o.get("customer_id")}
    dates = []
    for o in orders:
        d = o.get("delivery_date") or o.get("order_date")
        if d:
            dates.append(str(d)[:10])
    return {
        "order_count": len(orders),
        "customer_count": len(customers),
        "pending_qty": round(sum(float(o.get("pending_qty") or 0) for o in orders), 3),
        "pending_kg": round(sum(float(o.get("pending_kg") or 0) for o in orders), 3),
        "earliest_delivery": min(dates) if dates else None,
    }
