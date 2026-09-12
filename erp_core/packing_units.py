"""Packing size helpers — no Streamlit dependency (safe for database layer)."""
from __future__ import annotations

import re


def parse_packing_units(packing_size, product_name: str | None = None) -> float:
    """Units (pcs) per carton from product packing_size or name like 500/24."""
    for raw in (packing_size, product_name):
        s = str(raw or "").strip()
        if not s:
            continue
        try:
            n = float(s)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
        m = re.search(r"/\s*(\d+(?:\.\d+)?)\s*(?:$|[^\d])", s)
        if m:
            n = float(m.group(1))
            if n > 0:
                return n
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:pcs?|pieces?|pc)\b", s, re.I)
        if m:
            n = float(m.group(1))
            if n > 0:
                return n
    return 0.0


def packing_units_for_product(product) -> float:
    """Resolve pcs/carton for a product dict."""
    if not product:
        return 0.0
    return parse_packing_units(
        product.get("packing_size"),
        product.get("name") or product.get("product_name"),
    )
