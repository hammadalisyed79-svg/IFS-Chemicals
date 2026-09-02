"""Per-report column sets, layouts, and export cleanup for Reports Center."""

from __future__ import annotations

import re

import pandas as pd

# Columns never shown on printed / exported reports (internal keys)
DROP_COLUMNS = frozenset({
    "id", "customer_id", "supplier_id", "product_id", "employee_id", "warehouse_id",
    "account_id", "invoice_id", "purchase_id", "sale_id", "created_by", "modified_by",
    "created_at", "modified_at", "posted_by", "posted_at", "approved_by", "approved_at",
    "gate_pass_id", "weight_slip_id", "grn_id", "delivery_note_id", "sales_invoice_id",
    "purchase_invoice_id", "voucher_id", "journal_id", "batch_id", "bom_id",
    "entry_source", "raw_balance", "_sort", "_balance_line",
})

# Ordered export columns per report (omit keys not in dataframe)
REPORT_COLUMNS: dict[str, list[str]] = {
    "Sales Register": [
        "invoice_no", "sale_date", "customer_name", "subtotal", "discount", "tax",
        "total", "paid_amount", "payment_mode", "notes",
    ],
    "Sales Invoice Register": [
        "invoice_no", "invoice_date", "customer", "product_code", "product",
        "quantity", "rate", "amount", "line_discount", "tax_amount", "invoice_total",
    ],
    "Purchase Register": [
        "invoice_no", "purchase_date", "supplier_name", "subtotal", "discount", "tax",
        "total", "paid_amount", "payment_mode", "notes",
    ],
    "Purchase Invoice Register": [
        "invoice_no", "invoice_date", "supplier", "product_code", "product",
        "quantity", "rate", "amount", "line_discount", "tax_amount", "invoice_total",
    ],
    "Customer Outstanding": [
        "code", "name", "city",
        "period_debit", "period_credit", "balance",
    ],
    "Customer Due Aging": [
        "code", "name", "phone",
        "days_0_15", "days_16_30", "days_31_45", "days_46_60", "days_61_90",
        "over_90", "total_due",
    ],
    "Supplier Outstanding": ["code", "name", "phone", "outstanding"],
    "Customer Ledger": ["date", "ref", "description", "debit", "credit", "balance"],
    "Supplier Ledger": ["date", "ref", "description", "debit", "credit", "balance"],
    "Account Ledger": ["date", "ref", "description", "debit", "credit", "balance"],
    "Customer Ledger (Detailed)": [
        "Date", "Type", "Vr. #", "Narration", "Qty", "Rate", "Amount", "Debit", "Credit", "Balance",
    ],
    "Supplier Ledger (Detailed)": [
        "Date", "Type", "Vr. #", "Narration", "Qty", "Rate", "Amount", "Debit", "Credit", "Balance",
    ],
    "Product Sales Analysis": ["code", "name", "qty", "amount"],
    "Item Wise Sale (Detail)": [
        "product_code", "product_name", "date", "invoice_no", "name", "city",
        "quantity", "amount", "rate",
    ],
    "Item Wise Purchase (Detail)": [
        "product_code", "product_name", "date", "invoice_no", "name", "city",
        "quantity", "amount", "net_weight", "rate",
    ],
    "Purchase Analysis": ["code", "name", "qty", "amount"],
    "Tax Sales Report": [
        "invoice_no", "invoice_date", "subtotal", "discount", "taxable_amount",
        "sales_tax", "further_tax", "extra_tax", "fed_tax", "wht_tax", "total",
    ],
    "Tax Purchase Report": [
        "invoice_no", "invoice_date", "subtotal", "discount", "taxable_amount",
        "sales_tax", "further_tax", "extra_tax", "fed_tax", "wht_tax", "total",
    ],
    "Sales Returns": ["return_no", "return_date", "customer", "invoice_no", "subtotal", "total", "notes"],
    "Purchase Returns": ["return_no", "return_date", "supplier", "invoice_no", "subtotal", "total", "notes"],
    "Pending Sale Invoices": [
        "invoice_no", "sale_date", "customer_name", "total", "status",
        "weight_slip_no", "gate_pass_no", "weight_match_status",
    ],
    "Approved Sale Invoices": [
        "invoice_no", "sale_date", "customer_name", "total", "status", "weight_slip_no",
    ],
    "Pending Purchase Invoices": [
        "invoice_no", "purchase_date", "supplier_name", "total", "status", "weight_slip_no",
    ],
    "Approved Purchase Invoices": [
        "invoice_no", "purchase_date", "supplier_name", "total", "status",
    ],
    "Stock Position": [
        "code", "name", "category", "unit", "item_type", "stock_qty",
        "purchase_price", "stock_value", "reorder_level", "status",
    ],
    "Stock Valuation": ["code", "name", "category", "unit", "stock_qty", "purchase_price", "stock_value"],
    "Stock Ledger": ["date", "ref", "movement_type", "quantity", "reason", "code", "name"],
    "Warehouse Stock": ["warehouse", "code", "name", "quantity", "unit", "value"],
    "Batch Stock": ["batch_no", "product_code", "product_name", "warehouse_name", "quantity", "expiry_date"],
    "Reorder Report": ["code", "name", "stock_qty", "reorder_level", "purchase_price"],
    "Negative Stock Report": ["code", "name", "stock_qty", "unit"],
    "Cash Book": ["entry_date", "document_no", "description", "reference_no", "entry_type", "amount", "balance_after"],
    "Bank Book": ["entry_date", "document_no", "description", "reference_no", "entry_type", "amount", "balance_after"],
    "General Ledger": [
        "entry_date", "account_code", "account_name", "description", "reference_no", "debit", "credit",
    ],
    "Trial Balance": ["code", "name", "group_type", "period_debit", "period_credit", "balance"],
    "Balance Sheet": ["group_type", "code", "name", "balance"],
    "Journal Register": ["document_no", "voucher_date", "description", "total_debit", "total_credit", "status"],
    "Daily Activity Report": [
        "line_no", "voucher_no", "voucher_date", "party", "amount",
        "status", "user", "particulars", "time", "module", "voucher_type", "action",
    ],
    "Employee List": ["code", "full_name", "department_name", "designation_name", "phone", "join_date", "is_active"],
    "Employee Ledger": ["date", "ref", "description", "debit", "credit", "balance"],
    "Attendance Report": ["att_date", "emp_code", "employee_name", "status", "check_in", "check_out", "overtime_hrs"],
    "Payroll Register": [
        "document_no", "payroll_month", "payroll_year", "employee_name",
        "gross_salary", "total_deductions", "net_salary", "status",
    ],
    "Leave Report": ["from_date", "to_date", "employee_name", "leave_type_name", "days", "status"],
    "Overtime Report": ["code", "full_name", "total_overtime_hrs", "days"],
    "Gate Pass Register": [
        "document_no", "pass_date", "pass_type", "party_name", "vehicle_no", "driver_name",
        "material_desc", "quantity", "weight", "status",
    ],
    "Inward Register": [
        "document_no", "pass_date", "party_name", "vehicle_no", "material_desc", "quantity", "weight", "status",
    ],
    "Outward Register": [
        "document_no", "pass_date", "party_name", "vehicle_no", "material_desc", "quantity", "weight", "status",
    ],
    "Daily Weight Report": [
        "document_no", "slip_date", "customer_name", "supplier_name", "product_name",
        "registration_no", "gross_weight", "tare_weight", "net_weight", "status",
    ],
    "Sale Weight Variance Report": [
        "invoice_no", "invoice_date", "customer", "weight_slip_no",
        "invoice_weight_kg", "physical_weight_kg", "variance_kg", "vehicle_no",
    ],
    "Purchase Weight Variance Report": [
        "invoice_no", "invoice_date", "supplier", "weight_slip_no",
        "invoice_weight_kg", "physical_weight_kg", "variance_kg", "vehicle_no",
    ],
    "Weight Variance Report": [
        "doc_type", "invoice_no", "invoice_date", "customer", "supplier",
        "weight_slip_no", "invoice_weight_kg", "physical_weight_kg", "variance_kg",
    ],
    "BOM Cost Sheet": ["bom_no", "finished_product", "standard_output_qty", "raw_material", "rm_qty", "standard_cost", "line_cost"],
    "Production Register": ["document_no", "order_date", "product", "planned_qty", "actual_qty", "wastage_qty", "actual_cost", "status"],
    "Production Variance": ["document_no", "order_date", "product", "planned_qty", "actual_qty", "variance_qty", "status"],
    "Raw Material Consumption": [
        "document_no", "batch_no", "order_date", "finished_product",
        "raw_material_code", "raw_material", "consumed_qty", "weight", "rate", "amount",
    ],
    "Production Consumption": [
        "document_no", "batch_no", "order_date", "finished_product",
        "raw_material_code", "raw_material", "consumed_qty", "weight", "rate", "amount",
    ],
    "Production Consumption (by Order)": [
        "document_no", "batch_no", "order_date", "finished_product",
        "raw_material_code", "raw_material", "consumed_qty", "weight", "rate", "amount",
    ],
    "Production Consumption Register": [
        "document_no", "batch_no", "order_date", "finished_product",
        "raw_material_code", "raw_material", "consumed_qty", "weight", "rate", "amount",
    ],
    "Finished Goods Report": ["document_no", "order_date", "product", "qty_received", "cost_per_unit", "value"],
    "GRN Register": ["document_no", "grn_date", "supplier_name", "status", "notes"],
}

REPORT_LAYOUT = {
    "Customer Outstanding": "portrait_full",
    "Customer Ledger": "portrait_full",
    "Supplier Ledger": "portrait_full",
    "Employee Ledger": "portrait_full",
    "Customer Ledger (Detailed)": "landscape",
    "Supplier Ledger (Detailed)": "landscape",
    "Profit & Loss": "portrait_full",
    "Balance Sheet": "portrait_full",
    "Trial Balance": "portrait_full",
    "Cash Book": "portrait_full",
    "Bank Book": "portrait_full",
    "Item Wise Sale (Detail)": "portrait_full",
    "Item Wise Purchase (Detail)": "portrait_full",
    "Daily Activity Report": "portrait_full",
}

# Relative width weights by column name (higher = wider)
_WIDTH_HINTS = (
    (re.compile(r"narration|description|notes|material_desc|particular|address", re.I), 5.8),
    (re.compile(r"name|customer|supplier|party|product_name|item_name|employee", re.I), 2.4),
    (re.compile(r"product_code|item_code", re.I), 2.0),
    (re.compile(r"invoice|document_no|document|ref|vr_no|vr\.?\s*#?", re.I), 1.25),
    (re.compile(r"(?:^|_)code$|^code$", re.I), 1.5),
    (re.compile(r"^type$|status|unit|category|group", re.I), 0.85),
    (re.compile(r"^qty$|quantity|^rate$", re.I), 0.9),
    (re.compile(r"date|month|year|phone", re.I), 0.95),
    (re.compile(r"amount|total|debit|credit|balance|weight|value|tax|cost|price|paid|outstanding|slips", re.I), 1.25),
)

_SKIP_SUMMARY = re.compile(
    r"(^id$|_id$|balance$|rate$|code$|date$|type$|status$|phone$|ref$|vr|month|year|slips$|percent|pct)",
    re.I,
)


def report_layout(report_title: str) -> str:
    if report_title in REPORT_LAYOUT:
        return REPORT_LAYOUT[report_title]
    low = (report_title or "").lower()
    if any(x in low for x in ("ledger", "profit & loss", "balance sheet", "trial balance", "cash book", "bank book")):
        return "portrait_full"
    return "landscape"


def _report_profile_key(report_title: str | None) -> str | None:
    """Match catalog title when export title has extra suffix (e.g. 'Customer Ledger — ABC')."""
    if not report_title:
        return None
    if report_title in REPORT_COLUMNS:
        return report_title
    low = report_title.lower()
    for key in REPORT_COLUMNS:
        if key.lower() in low or low.startswith(key.lower()):
            return key
    return report_title


def prepare_report_dataframe(df: pd.DataFrame, report_title: str | None = None) -> pd.DataFrame:
    """Drop internal columns, apply report column order, format numbers for export."""
    if df is None or df.empty:
        return pd.DataFrame()

    profile_key = _report_profile_key(report_title)
    out = df.copy()
    out = out.replace({float("nan"): None})
    try:
        out = out.where(pd.notna(out), None)
    except Exception:
        pass

    # Drop internal / empty columns
    for c in list(out.columns):
        if c in DROP_COLUMNS or str(c).startswith("_"):
            out = out.drop(columns=[c], errors="ignore")
    out = out.dropna(axis=1, how="all")

    if profile_key and profile_key in REPORT_COLUMNS:
        wanted = REPORT_COLUMNS[profile_key]
        cols = [c for c in wanted if c in out.columns]
        extra = [c for c in out.columns if c not in cols and c not in DROP_COLUMNS]
        out = out[cols + extra] if cols else out
        if cols:
            out = out[cols]

    # Format numeric columns for display
    for c in out.columns:
        blank0 = _blank_zero_money_col(c) if profile_key and "Ledger" in str(profile_key) else False
        if out[c].dtype in ("float64", "float32", "int64", "int32"):
            if _should_format_money(c):
                out[c] = out[c].apply(lambda x, bz=blank0: _fmt_num(x, blank_zero=bz))
        elif out[c].dtype == object:
            try:
                s = pd.to_numeric(out[c], errors="coerce")
                if s.notna().sum() > len(out) * 0.5 and _should_format_money(c):
                    out[c] = s.apply(
                        lambda x, bz=blank0: _fmt_num(x, blank_zero=bz) if pd.notna(x) else ""
                    )
            except Exception:
                pass

    # Clean ledger narrations
    if profile_key and "Ledger" in str(profile_key):
        for col in ("description", "Description", "narration", "Narration"):
            if col in out.columns:
                out[col] = out[col].map(clean_ledger_narration)

    return out


def _should_format_money(col: str) -> bool:
    return bool(re.search(
        r"amount|total|debit|credit|balance|value|tax|discount|paid|cost|price|outstanding|gross|net|subtotal|weight",
        str(col),
        re.I,
    ))


def _fmt_num(v, blank_zero: bool = False):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        f = float(v)
        if blank_zero and abs(f) < 0.005:
            return ""
        return f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _blank_zero_money_col(col: str) -> bool:
    """Blank 0.00 on Dr/Cr/Qty/Rate/Amount — keep Balance visible."""
    cs = str(col)
    if re.search(r"balance", cs, re.I):
        return False
    return bool(re.search(r"debit|credit|qty|quantity|rate|^amount$|amount$", cs, re.I))


def clean_ledger_narration(text) -> str:
    """Strip import noise and collapse whitespace for professional ledger print."""
    s = str(text or "").strip()
    if not s:
        return ""
    up = s.upper()
    for prefix in ("FMYE:", "FMYE-", "FMYE "):
        if up.startswith(prefix):
            s = s[len(prefix):].strip()
            up = s.upper()
            break
    s = re.sub(r"\s+", " ", s)
    return s


def column_width_weights(columns: list[str]) -> list[float]:
    weights = []
    for c in columns:
        w = 1.0
        cs = str(c)
        for pat, mult in _WIDTH_HINTS:
            if pat.search(cs):
                w = mult
                break
        weights.append(w)
    return weights


def summary_keys_for_report(report_title: str | None, df: pd.DataFrame) -> dict:
    """Meaningful footer totals — avoid summing IDs, balances on line reports, etc."""
    if df is None or df.empty:
        return {}
    report_title = _report_profile_key(report_title) or report_title
    if report_title == "Customer Outstanding":
        # Closing Debit/Credit = split of signed balance; also sum period activity
        bals = pd.to_numeric(df.get("balance", df.get("Balance", 0)), errors="coerce").fillna(0)
        total_dr = float(bals[bals > 0.005].sum())
        total_cr = float((-bals[bals < -0.005]).sum())
        net = float(bals.sum())
        out = {
            "Total Debit": f"{total_dr:,.2f}",
            "Total Credit": f"{total_cr:,.2f}",
            "Net Balance": f"{abs(net):,.2f} {'Dr' if net >= 0 else 'Cr'}",
        }
        for col, label in (
            ("period_debit", "Period Debit"),
            ("period_credit", "Period Credit"),
            ("Period Debit", "Period Debit"),
            ("Period Credit", "Period Credit"),
        ):
            if col in df.columns:
                try:
                    s = pd.to_numeric(df[col], errors="coerce").fillna(0).sum()
                    out[f"Total {label}"] = f"{float(s):,.2f}"
                except Exception:
                    pass
        return out
    ledger_titles = (
        "Customer Ledger", "Supplier Ledger",
        "Customer Ledger (Detailed)", "Supplier Ledger (Detailed)",
        "Account Ledger",
    )
    if report_title in ledger_titles:
        ls = {}
        try:
            ls = dict(getattr(df, "attrs", {}) or {}).get("ledger_summary") or {}
        except Exception:
            ls = {}
        if ls:
            def _drcr(v):
                try:
                    x = float(v or 0)
                except (TypeError, ValueError):
                    x = 0.0
                if abs(x) < 0.005:
                    return "0.00"
                return f"{abs(x):,.2f} {'Dr' if x > 0 else 'Cr'}"

            return {
                "Opening": _drcr(ls.get("opening")),
                "Total Debit": f"{float(ls.get('period_debit') or 0):,.2f}",
                "Total Credit": f"{float(ls.get('period_credit') or 0):,.2f}",
                "Closing": _drcr(ls.get("closing")),
            }
    out = {}
    for c in df.columns:
        cs = str(c)
        if _SKIP_SUMMARY.search(cs):
            continue
        if not re.search(
            r"amount|total|debit|credit|value|tax|discount|paid|outstanding|cost|gross|net|subtotal|weight|"
            r"qty|quantity|consumed",
            cs,
            re.I,
        ):
            continue
        try:
            raw = df[c]
            if raw.dtype == object:
                s = pd.to_numeric(
                    raw.astype(str).str.replace(",", "", regex=False),
                    errors="coerce",
                )
            else:
                s = pd.to_numeric(raw, errors="coerce")
            if s.notna().any():
                label = cs.replace("_", " ").title()
                out[f"Total {label}"] = f"{s.sum():,.2f}"
        except Exception:
            pass
    if report_title in ledger_titles:
        for k in list(out.keys()):
            if "Balance" in k and "Debit" not in k and "Credit" not in k:
                del out[k]
        # Prefer not to include Opening row debit/credit in period totals when attrs missing:
        # drop keys that double-count OB by requiring ledger_summary when possible.
    return out


def profit_loss_dataframe(pl: dict) -> pd.DataFrame:
    """Single-column P&L as readable line items."""
    lines = [
        ("Gross Sales", pl.get("gross_sales", 0)),
        ("Less: Sale Returns", pl.get("sale_returns", 0)),
        ("Net Sales", pl.get("net_sales", 0)),
        ("Cost of Goods Sold", pl.get("cogs", 0)),
        ("Gross Profit", pl.get("gross_profit", 0)),
        ("Operating Expenses", pl.get("operating_expenses", 0)),
        ("Net Profit", pl.get("net_profit", 0)),
    ]
    return pd.DataFrame(lines, columns=["Line", "Amount"]).assign(
        Amount=lambda d: d["Amount"].apply(_fmt_num)
    )
