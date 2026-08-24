"""Single source of truth for tax and discount calculations — IFS Chemicals ERP."""

from __future__ import annotations


def _r(val):
    return round(float(val or 0), 2)


def validate_pct(pct, label="Percentage", allow_over_100=False):
    p = float(pct or 0)
    if p < 0:
        raise ValueError(f"{label} cannot be negative.")
    if p > 100 and not allow_over_100:
        raise ValueError(f"{label} cannot exceed 100%.")
    return p


def _tax_pcts(tax_rate_row):
    if not tax_rate_row or tax_rate_row.get("is_exempt"):
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return (
        float(tax_rate_row.get("sales_tax_pct") or 0),
        float(tax_rate_row.get("further_tax_pct") or 0),
        float(tax_rate_row.get("extra_tax_pct") or 0),
        float(tax_rate_row.get("fed_pct") or 0),
        float(tax_rate_row.get("wht_pct") or 0),
    )


def calc_line(
    quantity,
    rate,
    discount_pct=0,
    tax_rate_row=None,
    tax_inclusive=False,
):
    """
    Compute one document line per ERP tax rules.
    Returns all amounts rounded to 2 decimals.
    """
    qty = float(quantity or 0)
    rt = float(rate or 0)
    discount_pct = validate_pct(discount_pct, "Discount %")

    line_amount = _r(qty * rt)
    st_pct, ft_pct, et_pct, fed_pct, wht_pct = _tax_pcts(tax_rate_row)
    add_pct = st_pct + ft_pct + et_pct + fed_pct

    if tax_inclusive and add_pct > 0:
        gross_base = _r(line_amount / (1 + add_pct / 100))
        discount_amt = _r(gross_base * discount_pct / 100)
        taxable = _r(gross_base - discount_amt)
    else:
        discount_amt = _r(line_amount * discount_pct / 100)
        taxable = _r(line_amount - discount_amt)

    validate_pct(st_pct, "Sales Tax %")
    validate_pct(ft_pct, "Further Tax %")
    validate_pct(et_pct, "Extra Tax %")
    validate_pct(fed_pct, "FED %")
    validate_pct(wht_pct, "WHT %")

    sales_tax = _r(taxable * st_pct / 100)
    further_tax = _r(taxable * ft_pct / 100)
    extra_tax = _r(taxable * et_pct / 100)
    fed_tax = _r(taxable * fed_pct / 100)
    wht_tax = _r(taxable * wht_pct / 100)

    add_tax = _r(sales_tax + further_tax + extra_tax + fed_tax)
    net_amount = _r(taxable + add_tax - wht_tax)

    return {
        "quantity": qty,
        "rate": rt,
        "line_amount": line_amount,
        "amount": line_amount,
        "discount_pct": discount_pct,
        "discount_amt": discount_amt,
        "line_discount": discount_amt,
        "taxable": taxable,
        "taxable_amount": taxable,
        "sales_tax": sales_tax,
        "further_tax": further_tax,
        "extra_tax": extra_tax,
        "fed_tax": fed_tax,
        "wht_tax": wht_tax,
        "tax_amount": add_tax,
        "net_amount": net_amount,
    }


def compute_document_totals(line_items, header=None, get_tax_rate_fn=None):
    """
    Sum line calculations. Each line: quantity, rate, optional discount_pct, tax_rate_id.
    Header: discount_pct (default for lines), tax_rate_id (default), tax_inclusive.
    """
    header = header or {}
    tax_inclusive = bool(header.get("tax_inclusive"))
    default_disc = float(header.get("discount_pct", 0) or 0)
    default_tax_id = header.get("tax_rate_id")

    if get_tax_rate_fn is None:
        from db_v3 import get_tax_rate as get_tax_rate_fn

    computed_lines = []
    sums = {
        "gross_amount": 0.0,
        "subtotal": 0.0,
        "discount_amt": 0.0,
        "taxable": 0.0,
        "taxable_amount": 0.0,
        "sales_tax": 0.0,
        "further_tax": 0.0,
        "extra_tax": 0.0,
        "fed_tax": 0.0,
        "wht_tax": 0.0,
        "total_tax": 0.0,
    }

    for li in line_items:
        qty = li.get("quantity", li.get("qty", 0))
        rt = li.get("rate", 0)
        disc = li.get("discount_pct", default_disc)
        # Invoice/header tax category overrides product default tax on lines
        tr_id = default_tax_id if default_tax_id else li.get("tax_rate_id")
        tr = get_tax_rate_fn(tr_id) if tr_id else None
        cl = calc_line(qty, rt, disc, tr, tax_inclusive)
        merged = {**li, **cl}
        if tr_id:
            merged["tax_rate_id"] = tr_id
        computed_lines.append(merged)
        sums["gross_amount"] += cl["line_amount"]
        sums["subtotal"] += cl["line_amount"]
        sums["discount_amt"] += cl["discount_amt"]
        sums["taxable"] += cl["taxable"]
        sums["sales_tax"] += cl["sales_tax"]
        sums["further_tax"] += cl["further_tax"]
        sums["extra_tax"] += cl["extra_tax"]
        sums["fed_tax"] += cl["fed_tax"]
        sums["wht_tax"] += cl["wht_tax"]

    for k in sums:
        sums[k] = _r(sums[k])
    sums["taxable_amount"] = sums["taxable"]
    add_tax = _r(sums["sales_tax"] + sums["further_tax"] + sums["extra_tax"] + sums["fed_tax"])
    sums["total_tax"] = add_tax
    total = _r(sums["taxable"] + add_tax - sums["wht_tax"])
    if header:
        charges = sum(float(header.get(k) or 0) for k in ("freight", "loading_charges", "other_charges", "round_off"))
        total = _r(total + charges)
    sums["total"] = total
    sums["net_amount"] = total
    sums["discount_pct"] = default_disc
    sums["discount_amt"] = sums["discount_amt"]
    sums["tax_pct"] = _r(add_tax / sums["taxable"] * 100) if sums["taxable"] else 0.0
    sums["tax_inclusive"] = int(tax_inclusive)

    # Balance validation: debits = credits pattern
    credits = _r(sums["taxable"] + add_tax)
    debits = _r(total + sums["wht_tax"])
    if abs(credits - debits) > 0.02:
        raise ValueError(f"Invoice totals not balanced: credits {credits} vs debits {debits}")

    return {"lines": computed_lines, **sums}


def apply_invoice_totals_to_data(data, line_items, get_tax_rate_fn=None):
    result = compute_document_totals(line_items, data, get_tax_rate_fn)
    data = dict(data)
    data["subtotal"] = result["subtotal"]
    data["discount"] = result["discount_amt"]
    data["discount_pct"] = result["discount_pct"]
    data["taxable_amount"] = result["taxable"]
    data["tax"] = result["total_tax"]
    data["sales_tax"] = result["sales_tax"]
    data["further_tax"] = result["further_tax"]
    data["extra_tax"] = result["extra_tax"]
    data["fed_tax"] = result["fed_tax"]
    data["wht_tax"] = result["wht_tax"]
    data["tax_inclusive"] = int(bool(data.get("tax_inclusive")))
    data["total"] = result["total"]
    for k in ("freight", "loading_charges", "other_charges", "round_off", "grand_weight",
              "registered_taxpayer", "gst_pct", "further_tax_pct", "fed_pct",
              "supplier_bill_no", "claim_input_tax"):
        if k in data:
            result[k] = data[k]
    return data, result


def calc_line_tax_dict(line_amount, tax_rate_row, tax_inclusive=False, discount_pct=0):
    """Dict return for UI helpers."""
    cl = calc_line(1, float(line_amount or 0), discount_pct, tax_rate_row, tax_inclusive)
    return {
        "sales_tax": cl["sales_tax"],
        "further_tax": cl["further_tax"],
        "extra_tax": cl["extra_tax"],
        "wht_tax": cl["wht_tax"],
        "fed_tax": cl["fed_tax"],
        "total_tax": cl["tax_amount"],
        "taxable_base": cl["taxable"],
        "net_amount": cl["net_amount"],
    }


# Backward-compatible aliases
def calc_line_tax(taxable_amount, tax_rate_row, tax_inclusive=False):
    """Legacy wrapper — taxes on a pre-discounted taxable base (no line amount)."""
    st_pct, ft_pct, et_pct, fed_pct, wht_pct = _tax_pcts(tax_rate_row)
    taxable = float(taxable_amount or 0)
    if tax_inclusive:
        add_pct = st_pct + ft_pct + et_pct + fed_pct
        if add_pct:
            taxable = taxable / (1 + add_pct / 100)
    sales_tax = _r(taxable * st_pct / 100)
    further_tax = _r(taxable * ft_pct / 100)
    extra_tax = _r(taxable * et_pct / 100)
    fed_tax = _r(taxable * fed_pct / 100)
    wht_tax = _r(taxable * wht_pct / 100)
    total_tax = _r(sales_tax + further_tax + extra_tax + fed_tax)
    return sales_tax, further_tax, extra_tax, wht_tax


def compute_invoice_totals(line_items, data):
    """Backward-compatible wrapper."""
    result = compute_document_totals(line_items, data)
    return {k: result[k] for k in result if k != "lines"}


def enrich_lines(line_items, header=None, get_tax_rate_fn=None):
    return compute_document_totals(line_items, header, get_tax_rate_fn)["lines"]
