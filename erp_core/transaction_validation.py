"""V13.13 — global transaction validation for all line-based documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DOC_SALES = "sales"
DOC_PURCHASE = "purchase"
DOC_STOCK = "stock"
DOC_PRODUCTION = "production"
DOC_HR = "hr"


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: "ValidationResult") -> None:
        if not other.ok:
            self.ok = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def raise_if_invalid(self, prefix: str = "") -> None:
        if not self.ok:
            head = f"{prefix}: " if prefix else ""
            raise ValueError(head + "; ".join(self.errors))


def _line_key(line: dict) -> Any:
    return line.get("product_id") or line.get("item_id")


def validate_lines(
    lines: list[dict],
    *,
    require_rate: bool = True,
    require_warehouse: bool = False,
    doc_label: str = "Document",
) -> ValidationResult:
    res = ValidationResult()
    valid = []
    for i, ln in enumerate(lines or [], start=1):
        pid = _line_key(ln)
        qty = float(ln.get("quantity") or 0)
        rate = float(ln.get("rate") or 0)
        wh = ln.get("warehouse_id")
        if not pid:
            continue
        if qty <= 0:
            res.fail(f"Line {i}: quantity must be greater than zero.")
        if require_rate and rate <= 0:
            res.fail(f"Line {i}: rate must be greater than zero.")
        if require_warehouse and not wh:
            res.fail(f"Line {i}: warehouse is required.")
        valid.append(ln)
    if not valid:
        res.fail(f"{doc_label}: at least one valid line item is required.")
    return res


def validate_party(
    data: dict,
    *,
    doc_kind: str,
    doc_label: str = "Document",
) -> ValidationResult:
    res = ValidationResult()
    if doc_kind == DOC_SALES and not data.get("customer_id"):
        res.fail(f"{doc_label}: customer is required.")
    if doc_kind == DOC_PURCHASE and not data.get("supplier_id"):
        res.fail(f"{doc_label}: supplier is required.")
    if doc_kind == DOC_STOCK and not data.get("warehouse_id"):
        res.fail(f"{doc_label}: warehouse is required.")
    return res


def validate_tax_totals(totals: dict, *, doc_label: str = "Document") -> ValidationResult:
    res = ValidationResult()
    taxable = float(totals.get("taxable") or 0)
    discount_amt = float(totals.get("discount_amt") or 0)
    subtotal = float(totals.get("subtotal") or 0)
    if discount_amt > subtotal + 0.001:
        res.fail(f"{doc_label}: discount cannot exceed gross amount.")
    if taxable < -0.001:
        res.fail(f"{doc_label}: taxable amount cannot be negative after discount.")
    for key, label in (
        ("sales_tax", "GST"),
        ("further_tax", "Further tax"),
        ("fed_tax", "FED"),
        ("extra_tax", "Extra tax"),
        ("wht_tax", "WHT"),
        ("total_tax", "Total tax"),
    ):
        if float(totals.get(key) or 0) < -0.001:
            res.fail(f"{doc_label}: {label} cannot be negative.")
    return res


def validate_document(
    data: dict,
    lines: list[dict],
    totals: dict | None,
    *,
    doc_kind: str,
    doc_label: str = "Document",
    require_rate: bool = True,
    require_warehouse: bool = False,
    stage: str = "draft",
) -> ValidationResult:
    """Validate header + lines + tax. stage: draft | approve | post."""
    res = ValidationResult()
    res.merge(validate_party(data, doc_kind=doc_kind, doc_label=doc_label))
    res.merge(
        validate_lines(
            lines,
            require_rate=require_rate,
            require_warehouse=require_warehouse,
            doc_label=doc_label,
        )
    )
    if totals:
        res.merge(validate_tax_totals(totals, doc_label=doc_label))
    if stage in ("approve", "post") and not res.ok:
        res.fail(f"{doc_label}: cannot {stage} — fix validation errors first.")
    return res


def validate_sale_invoice(data: dict, lines: list[dict], totals: dict | None, *, stage: str = "draft"):
    return validate_document(
        data, lines, totals,
        doc_kind=DOC_SALES, doc_label="Sales invoice",
        require_rate=True, stage=stage,
    )


def validate_purchase_invoice(data: dict, lines: list[dict], totals: dict | None, *, stage: str = "draft"):
    return validate_document(
        data, lines, totals,
        doc_kind=DOC_PURCHASE, doc_label="Purchase invoice",
        require_rate=True, stage=stage,
    )


def validate_stock_document(data: dict, lines: list[dict], *, doc_label: str = "Stock document", stage: str = "draft"):
    return validate_document(
        data, lines, None,
        doc_kind=DOC_STOCK, doc_label=doc_label,
        require_rate=False, require_warehouse=True, stage=stage,
    )


def assert_editable_status(status: str, *, posted_locked: bool = True) -> None:
    s = (status or "draft").lower()
    if posted_locked and s in ("posted", "approved"):
        raise ValueError(f"Document status '{status}' is locked. Use reversal or unapprove (admin) first.")
    if s == "cancelled":
        raise ValueError("Cancelled documents cannot be edited.")
