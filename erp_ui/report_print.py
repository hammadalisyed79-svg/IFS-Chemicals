"""Reporting & Printing engine — PDF, HTML, Excel, CSV with company header/footer."""

from __future__ import annotations

import io
import re
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from application import data_gateway as db

from erp_ui.report_profiles import (
    column_width_weights,
    prepare_report_dataframe,
    report_layout,
    summary_keys_for_report,
    clean_ledger_narration,
    _report_profile_key,
)

from contextvars import ContextVar
from contextlib import contextmanager

# When False, invoices/vouchers/reports omit the IFS Chemicals letterhead
_PRINT_COMPANY_HEADER: ContextVar[bool] = ContextVar("print_company_header", default=True)

_PRINT_BASE = """
* { box-sizing: border-box; }
body {
  font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
  color: #111; margin: 0; padding: 20px; font-size: 13px; background: #fff;
}
.doc-wrap, .report-wrap {
  margin: 0 auto; background: #fff;
  border: 1px solid #333; box-shadow: none; padding: 14px 10px;
}
.header { border-bottom: 2px solid #111; padding-bottom: 14px; margin-bottom: 18px; }
.header-row { display: flex; justify-content: space-between; align-items: flex-start; }
.header h1 { margin: 0; color: #111; font-size: 22px; letter-spacing: .3px; }
.header .co-meta { text-align: right; font-size: 12px; color: #333; line-height: 1.5; }
.header .sub { color: #333; font-size: 12px; margin-top: 4px; }
h2 { color: #111; font-size: 17px; margin: 12px 0 10px 0; border-bottom: 1px solid #999; padding-bottom: 4px; }
h3 { font-size: 15px; margin: 10px 0 8px 0; color: #111; }
.meta { display: flex; flex-wrap: wrap; gap: 10px 24px; margin: 12px 0; font-size: 12px; }
.party-block {
  margin: 12px 0 16px 0; padding: 10px 12px; background: transparent;
  border: 1px solid #333; border-radius: 0;
}
.party-block .party-label { font-size: 12px; color: #333; margin-bottom: 6px; font-weight: 600; }
.party-block .party-name { font-size: 20px; line-height: 1.35; color: #111; }
.report-title {
  background: transparent; color: #111;
  padding: 10px 14px; margin: 0 0 14px 0; font-size: 16px;
  font-weight: 700; letter-spacing: .4px; border: 2px solid #111; border-radius: 0;
}
.meta-bar {
  display: flex; flex-wrap: wrap; gap: 10px 24px;
  margin: 0 0 14px 0; padding: 11px 14px; background: transparent;
  border: 1px solid #333; border-radius: 0; font-size: 12px; color: #111;
}
.meta-bar span b { color: #111; }
table.data { width: 100%; border-collapse: collapse; margin-top: 4px; table-layout: fixed; }
table.data.report-grid { table-layout: auto; }
table.data.report-grid th.code-col,
table.data.report-grid td.code-col { min-width: 4.5em; white-space: nowrap; }
table.data.lines-table { table-layout: fixed; width: 100%; }
table.data.lines-table th:nth-child(1),
table.data.lines-table td:nth-child(1) { width: 12%; min-width: 3.5em; }
table.data.lines-table td.wrap { white-space: normal; word-wrap: break-word; }
table.data th {
  background: transparent; color: #111; padding: 9px 7px; text-align: left;
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .3px;
  border: 1px solid #333; overflow: hidden; text-overflow: ellipsis;
}
table.data td {
  border: 1px solid #333; padding: 7px 7px; font-size: 11px; vertical-align: top;
  overflow: hidden; word-wrap: break-word; line-height: 1.4; background: transparent;
}
table.data td.wrap { white-space: normal; line-height: 1.45; }
table.data tr:nth-child(even) td { background: transparent; }
table.data td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
table.data tr.total-row td {
  background: transparent !important; font-weight: 700;
  border-top: 2px solid #111; border-bottom: 2px solid #111; font-size: 12px;
}
.totals { margin-top: 16px; font-size: 13px; }
.summary-box {
  display: flex; flex-wrap: wrap; gap: 10px 28px;
  background: transparent; padding: 12px 16px;
  border: 1px solid #333; margin: 12px 0; border-radius: 0; font-size: 13px;
}
.summary-box div { min-width: 140px; }
.summary-box b { color: #111; }
.footer {
  margin-top: 28px; padding-top: 10px; border-top: 1px solid #333;
  font-size: 11px; color: #333; display: flex; justify-content: space-between;
}
.print-btn {
  background: #1e3a5f; color: #fff; border: none; padding: 9px 20px;
  border-radius: 3px; cursor: pointer; font-size: 13px; margin-top: 12px;
}
.print-btn:hover { background: #2d5a8a; }
.variance-ok { color: #111; font-weight: 700; }
.variance-warn { color: #111; font-weight: 700; }
.variance-bad { color: #111; font-weight: 700; text-decoration: underline; }
.signatures { display:flex; justify-content:space-between; margin-top:48px; gap:12px; }
.sig-cell { flex:1; text-align:center; font-size:12px; color:#111; }
.sig-line { border-top:1px solid #111; margin:28px 0 6px 0; min-height:2px; }
.sig-prepared-name { font-size:13px; color:#111; margin-bottom:4px; min-height:1.2em; font-weight:700; }
.sig-role { font-size:11px; color:#333; font-weight:600; text-transform:uppercase; letter-spacing:.03em; }
.sig-note { font-size:11px; color:#333; margin-top:8px; font-style:italic; }
.posted-by-line { font-size:13px; margin:20px 0 8px 0; font-weight:600; }
.sys-generated-notice {
  margin-top: 36px; padding: 12px 14px; border: 1px solid #333;
  text-align: center; font-size: 12px; font-weight: 600; line-height: 1.45;
}
  .sys-generated-notice p { margin: 0; }
.half-page-sheet .sys-generated-notice { margin-top: 20px; padding: 8px 10px; font-size: 11px; }
@media print {
  .sys-generated-notice, .sys-generated-notice p {
    background: transparent !important;
    color: #000 !important;
  }
}
.voucher-amt-box {
  border: 2px solid #111; padding: 18px; margin: 22px 0; text-align: center; background: transparent;
}
.voucher-amt-label { font-size:12px; text-transform:uppercase; color:#333; }
.voucher-amt-value { font-size:26px; font-weight:bold; color:#111; margin:8px 0; }
"""

# Enforced on every print HTML (reports, documents, ledgers, item-wise, weight slips)
_PRINT_INK_SAVE = """
.report-title, .meta-bar, .party-block, .summary-box, .voucher-amt-box,
.itemwise-head, .daily-module, .daily-type-head, .daily-summary-grid, .sys-generated-notice, .header, h2, h3,
table.data th, table.data td, table.data thead th, table.data tbody td,
table.data tr:nth-child(even) td, table.data tr.total-row td,
table.itemwise-lines th, table.itemwise-lines td,
table.itemwise-lines tr.item-sub td, table.itemwise-lines tr.grand-total td,
table.daily-lines th, table.daily-lines td,
table.daily-lines tr.type-sub td, table.daily-lines tr.module-sub td, table.daily-lines tr.grand-total td,
html[lang="ur"] .report-title, html[lang="ur"] .meta-bar, html[lang="ur"] .summary-box,
html[lang="ur"] table.data.ledger th, html[lang="ur"] table.data.ledger td,
html[lang="ur"] table.data.ledger tr.total-row td {
  background: transparent !important;
  background-color: transparent !important;
  background-image: none !important;
  box-shadow: none !important;
  color: #000 !important;
}
table.data th, table.itemwise-lines th, table.daily-lines th,
html[lang="ur"] table.data.ledger th {
  border: 1px solid #000 !important;
  font-weight: 700 !important;
}
table.data td, table.itemwise-lines td, table.daily-lines td,
html[lang="ur"] table.data.ledger td {
  border: 1px solid #000 !important;
}
.report-title, .meta-bar, .party-block, .summary-box, .itemwise-head, .daily-module, .daily-type-head, .sys-generated-notice {
  border: 1px solid #000 !important;
}
table.data tr.total-row td, table.itemwise-lines tr.grand-total td,
table.itemwise-lines tr.item-sub td,
table.daily-lines tr.grand-total td, table.daily-lines tr.type-sub td, table.daily-lines tr.module-sub td,
html[lang="ur"] table.data.ledger tr.total-row td {
  border-top: 2px solid #000 !important;
  border-bottom: 2px solid #000 !important;
}
.variance-ok, .variance-warn, .variance-bad {
  color: #000 !important;
}
"""

# Page margins (mm): vertical, horizontal — kept tight for all report exports
_MARGIN_V = 7
_MARGIN_H = 4

_PRINT_PAGE_LANDSCAPE = f"@page {{ size: A4 landscape; margin: {_MARGIN_V}mm {_MARGIN_H}mm; }}"
_PRINT_PAGE_PORTRAIT_FULL = f"@page {{ size: A4 portrait; margin: {_MARGIN_V}mm {_MARGIN_H}mm; }}"
_PRINT_PAGE_PORTRAIT_HALF = f"@page {{ size: A4 portrait; margin: 6mm {_MARGIN_H}mm; }}"

_PRINT_MEDIA = f"""
{_PRINT_INK_SAVE}
@media print {{
  .no-print {{ display: none !important; }}
  * {{
    -webkit-print-color-adjust: economy !important;
    print-color-adjust: economy !important;
  }}
  body {{
    margin: 0; padding: 0; background: #fff !important;
  }}
  .report-wrap, .doc-wrap {{
    box-shadow: none !important;
    border: none !important;
    max-width: 100% !important; width: 100% !important;
    margin: 0 !important; padding: 2mm 1mm !important;
  }}
  .half-page-sheet {{ page-break-after: avoid; page-break-inside: avoid; max-width: 100% !important; height: 148mm !important; max-height: 148mm !important; }}
  .half-page-blank {{ display: none !important; }}
}}
"""


def _print_page_rule(layout: str, ncol: int) -> str:
    """Wide tables use landscape page to maximize printable width."""
    if ncol >= 8:
        return _PRINT_PAGE_LANDSCAPE
    if layout == "portrait_full":
        return _PRINT_PAGE_PORTRAIT_FULL
    return _PRINT_PAGE_LANDSCAPE


def _pdf_orientation(layout: str, ncol: int) -> str:
    if ncol >= 8:
        return "L"
    if layout == "portrait_full" and ncol <= 6:
        return "P"
    return "L" if ncol > 6 else "P"


def _build_print_css(layout: str = "landscape", ncol: int = 0) -> str:
    page = _print_page_rule(layout, ncol)
    return (
        f"<style>\n{page}\n{_PRINT_BASE}\n{_PRINT_INK_SAVE}\n{_PRINT_MEDIA}\n"
        "body { padding: 8px; }\n"
        ".doc-wrap, .report-wrap { max-width: 100%; width: 100%; padding: 10px 6px; }\n"
        "</style>"
    )


# Legacy constants for document_print / vouchers
_PRINT_CSS = _build_print_css("landscape", 0)
PRINT_CSS_PORTRAIT_FULL = _build_print_css("portrait_full", 0)

# Cash / Bank book ledger columns (% of table width on A4 portrait)
_LEDGER_COL_PCTS = (12.0, 39.0, 10.0, 13.0, 13.0, 13.0)
_LEDGER_PRINT_EXTRA = """
table.data.ledger { table-layout: fixed; width: 100%; }
table.data.ledger col.col-date { width: 12%; }
table.data.ledger col.col-part { width: 39%; }
table.data.ledger col.col-ref { width: 10%; }
table.data.ledger col.col-amt { width: 13%; }
table.data.ledger th.date, table.data.ledger td.date {
  white-space: nowrap; word-break: keep-all;
  direction: ltr; unicode-bidi: isolate;
  text-align: center; vertical-align: middle;
  font-family: 'Segoe UI', Arial, sans-serif;
  padding-left: 4px; padding-right: 4px;
}
table.data.ledger td.particulars {
  white-space: normal; word-wrap: break-word; overflow-wrap: anywhere;
  line-height: 1.4; font-size: 11px;
}
table.data.ledger td.date, table.data.ledger td.ref { font-size: 11px; }
table.data.ledger th.ref, table.data.ledger td.ref {
  white-space: nowrap; direction: ltr; unicode-bidi: isolate; text-align: center;
}
table.data.ledger th.num, table.data.ledger td.num { width: 13%; text-align: right; padding-right: 4px; }
.report-wrap.ledger-a4 {
  max-width: 210mm; width: 100%; margin: 0 auto;
}
@media print {
  table.data.ledger { page-break-inside: auto; }
  table.data.ledger thead { display: table-header-group; }
  table.data.ledger tr { page-break-inside: avoid; }
}
"""
PRINT_CSS_LEDGER = (
    PRINT_CSS_PORTRAIT_FULL.replace("</style>", f"{_LEDGER_PRINT_EXTRA}</style>")
    if "</style>" in PRINT_CSS_PORTRAIT_FULL
    else PRINT_CSS_PORTRAIT_FULL + f"<style>{_LEDGER_PRINT_EXTRA}</style>"
)

PRINT_CSS_PORTRAIT_HALF = f"""
<style>
{_PRINT_PAGE_PORTRAIT_HALF}
{_PRINT_BASE}
{_PRINT_INK_SAVE}
{_PRINT_MEDIA}
body {{ padding: 10px; background: #fff; }}
/* Top 50% of A4 (~148.5mm) — cash voucher / gate pass */
.half-page-sheet {{
  max-width: 100%; width: 100%; margin: 0 auto;
  height: 148mm; min-height: 148mm; max-height: 148mm;
  overflow: hidden; padding: 8px 6px; border: 1px solid #ccc;
  box-sizing: border-box;
}}
.half-page-sheet .header {{ padding-bottom: 6px; margin-bottom: 8px; }}
.half-page-sheet .header h1 {{ font-size: 17px; }}
.half-page-sheet h2 {{ font-size: 14px; margin: 6px 0; }}
.half-page-sheet .meta {{ margin: 6px 0; font-size: 11px; }}
.half-page-sheet .party-block .party-name {{ font-size: 17px; }}
.half-page-sheet table.data th, .half-page-sheet table.data td {{ padding: 5px 6px; font-size: 11px; }}
.half-page-sheet .summary-box {{ padding: 6px 10px; margin: 6px 0; font-size: 11px; }}
.half-page-sheet .voucher-amt-box {{ padding: 8px; margin: 8px 0; }}
.half-page-sheet .voucher-amt-value {{ font-size: 18px; }}
.half-page-sheet .signatures {{ margin-top: 16px; }}
.half-page-sheet .signatures.sig-4 .sig-role {{ font-size: 9px; }}
.half-page-sheet .sig-line {{ min-height: 24px; }}
.half-page-sheet .footer {{ margin-top: 8px; font-size: 8px; }}
.half-page-cut {{
  max-width: 100%; margin: 6px auto 0; border-top: 1px dashed #999;
  text-align: center; font-size: 8px; color: #888; padding-top: 4px;
}}
.half-page-blank {{
  max-width: 100%; margin: 0 auto; height: 120mm;
  border: 1px dashed #ddd; color: #bbb; font-size: 10px;
  display: flex; align-items: center; justify-content: center;
}}
@media print {{
  .half-page-cut {{ display: none; }}
  .half-page-blank {{ display: none !important; }}
  .half-page-sheet {{
    border: none;
    height: 148mm !important; max-height: 148mm !important;
    page-break-after: avoid; page-break-inside: avoid;
  }}
}}
</style>
"""

_NUMERIC_HINTS = re.compile(
    r"(amount|total|qty|quantity|weight|balance|rate|price|tax|discount|paid|cost|debit|credit|variance|net|gross|tare|slips)",
    re.I,
)


def get_company_info():
    return {
        "name": db.get_setting("company_name", "IFS Chemicals"),
        "address": db.get_setting("company_address", ""),
        "ntn": db.get_setting("company_ntn", ""),
        "strn": db.get_setting("company_strn", ""),
    }


def print_company_header_enabled() -> bool:
    try:
        return bool(_PRINT_COMPANY_HEADER.get())
    except LookupError:
        return True


@contextmanager
def print_company_header_scope(enabled: bool):
    """Temporarily enable/disable company letterhead while building print HTML."""
    token = _PRINT_COMPANY_HEADER.set(bool(enabled))
    try:
        yield
    finally:
        _PRINT_COMPANY_HEADER.reset(token)


def company_letterhead_html() -> str:
    """Document letterhead (name / address / NTN). Empty when print header is off."""
    if not print_company_header_enabled():
        return ""
    co = get_company_info()
    return f"""
    <div class="header company-letterhead">
        <h1>{escape(co['name'])}</h1>
        <div class="sub">{escape(co.get('address') or '')}</div>
        <div class="sub">NTN: {escape(co.get('ntn') or '—')} | STRN: {escape(co.get('strn') or '—')}</div>
    </div>
    """


def company_report_header_html(*, ref_prefix: str = "RPT") -> str:
    """Report letterhead with ref + generated time. Empty when print header is off."""
    if not print_company_header_enabled():
        return ""
    co = get_company_info()
    ref = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"""
    <div class="header company-letterhead">
      <div class="header-row">
        <div>
          <h1>{escape(co['name'])}</h1>
          <div class="sub">{escape(co.get('address') or '')}</div>
          <div class="sub">NTN: {escape(co.get('ntn') or '—')} &nbsp;|&nbsp; STRN: {escape(co.get('strn') or '—')}</div>
        </div>
        <div class="co-meta">
          <div><b>Report Ref:</b> {escape(ref_prefix)}-{ref}</div>
          <div><b>Generated:</b> {_now_str()}</div>
        </div>
      </div>
    </div>
    """


def use_print_company_header_checkbox(key_prefix: str = "doc") -> bool:
    """Checkbox on print toolbars — remembers last choice for the session."""
    pref = "erp_print_company_header_pref"
    if pref not in st.session_state:
        st.session_state[pref] = True
    wkey = f"{key_prefix}_print_company_hdr"
    if wkey not in st.session_state:
        st.session_state[wkey] = bool(st.session_state[pref])
    include = st.checkbox(
        "Print company header",
        key=wkey,
        help="Print IFS Chemicals name, address, NTN/STRN. Uncheck for pre-printed stationery.",
    )
    st.session_state[pref] = bool(include)
    return bool(include)


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_df(df):
    if df is None:
        return pd.DataFrame()
    if isinstance(df, list):
        return pd.DataFrame(df)
    return df.copy()


def prettify_columns(df):
    """Human-readable column titles for reports."""
    df = _safe_df(df)
    mapping = {}
    for c in df.columns:
        label = str(c).replace("_", " ").strip()
        label = re.sub(r"\bid\b", "ID", label, flags=re.I)
        label = label.title()
        replacements = {
            "Qty": "Quantity", "Inv": "Invoice", "Doc": "Document", "Grn": "GRN",
            "Dn": "DN", "Ntn": "NTN", "Strn": "STRN", "Wht": "WHT",
        }
        for old, new in replacements.items():
            label = label.replace(old, new)
        # Aging buckets (keep readable day ranges)
        aging_labels = {
            "days_0_15": "0-15 Days",
            "days_16_30": "16-30 Days",
            "days_31_45": "31-45 Days",
            "days_46_60": "46-60 Days",
            "days_61_90": "61-90 Days",
            "over_90": "Over 90 Days",
            "total_due": "Total Due",
        }
        if str(c) in aging_labels:
            label = aging_labels[str(c)]
        mapping[c] = label
    return df.rename(columns=mapping)


def _is_numeric_col(col_name, series):
    if _NUMERIC_HINTS.search(str(col_name)):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return True
    return False


def _fmt_cell(v, numeric=False):
    if v is None or v == "":
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, str) and v.strip().lower() in ("nan", "none", "<na>"):
        return ""
    if isinstance(v, float):
        if numeric or abs(v) >= 1000 or (v != 0 and abs(v) < 0.01):
            return f"{v:,.2f}"
        return f"{v:,.2f}"
    if isinstance(v, int) and numeric:
        return f"{v:,}"
    # Helvetica PDF cannot encode em/en dashes or other unicode punctuation
    return (
        str(v)
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("—", "-")
        .replace("–", "-")
    )


def _numeric_summary(df, report_key=None):
    return summary_keys_for_report(report_key, _safe_df(df))


def _width_pct(columns: list[str]) -> list[float]:
    w = column_width_weights(columns)
    total = sum(w) or 1.0
    return [100.0 * x / total for x in w]


def _is_wide_col(name: str) -> bool:
    return bool(re.search(r"narration|description|notes|material|particular|address|name", str(name), re.I))


def _is_code_col(name: str) -> bool:
    return bool(re.search(r"product\s*code|item\s*code|^code$", str(name), re.I))


def _pdf_safe_text(text: str) -> str:
    """Normalize text for Helvetica PDF (latin-1 safe) without losing words."""
    s = str(text or "")
    repl = {
        "\u2014": "-", "\u2013": "-", "—": "-", "–": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "…": "...", "\u00a0": " ", "\t": " ",
        "\u20a8": "Rs", "₨": "Rs",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip()
    try:
        s.encode("latin-1")
        return s
    except UnicodeEncodeError:
        return s.encode("latin-1", errors="replace").decode("latin-1")


def _pdf_clip(text, max_len: int | None = None) -> str:
    s = _pdf_safe_text(text)
    return s[:max_len] if max_len else s


def _pdf_wrap_lines(pdf, text: str, width_mm: float, *, max_lines: int = 8) -> list[str]:
    """Word-wrap text to fit a PDF cell width; never truncate mid-word when possible."""
    text = _pdf_safe_text(text)
    if not text:
        return [""]
    usable = max(8.0, float(width_mm) - 1.2)
    # Prefer fpdf2 split when available
    try:
        lines = pdf.multi_cell(usable, 4.0, text, border=0, split_only=True)
        if isinstance(lines, list) and lines:
            out = [str(x) for x in lines if str(x) is not None]
            if len(out) > max_lines:
                head = out[: max_lines - 1]
                rest = " ".join(out[max_lines - 1 :])
                while rest and pdf.get_string_width(rest + "...") > usable and len(rest) > 4:
                    rest = rest[:-2]
                head.append((rest.rstrip() + "...") if rest else "...")
                return head
            return out or [""]
    except Exception:
        pass
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = w if not cur else f"{cur} {w}"
        if pdf.get_string_width(trial) <= usable:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        if pdf.get_string_width(w) <= usable:
            cur = w
        else:
            # Hard-break very long tokens (refs, account nos.)
            chunk = ""
            for ch in w:
                if pdf.get_string_width(chunk + ch) <= usable:
                    chunk += ch
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = ch
            cur = chunk
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])[:40] + "..."]
    return lines or [""]


def _pdf_draw_table_row(pdf, cells: list[tuple[str, float, bool, bool]], *, line_h: float = 4.0, pad_y: float = 0.8):
    """Draw one bordered table row with wrapped text (no overwrite / mid-cell clipping).

    cells: list of (text, width_mm, numeric_align_right, allow_wrap)
    """
    x0 = pdf.get_x()
    y0 = pdf.get_y()
    prepared: list[tuple[list[str], float, bool]] = []
    max_lines = 1
    for text, w, right, wrap in cells:
        if wrap:
            lines = _pdf_wrap_lines(pdf, text, w, max_lines=8)
        else:
            safe = _pdf_safe_text(text)
            usable = max(6.0, w - 1.0)
            if pdf.get_string_width(safe) > usable:
                while safe and pdf.get_string_width(safe + "...") > usable:
                    safe = safe[:-1]
                safe = (safe.rstrip() + "...") if safe else ""
            lines = [safe]
        prepared.append((lines, w, right))
        max_lines = max(max_lines, len(lines))

    row_h = max(line_h + pad_y * 2, max_lines * line_h + pad_y * 2)
    # Page break if needed (caller may also check; keep safe here)
    if y0 + row_h > pdf.h - pdf.b_margin - 2:
        return False  # signal caller to page-break and retry

    x = x0
    for lines, w, right in prepared:
        pdf.rect(x, y0, w, row_h)
        align = "R" if right else "L"
        text_block_h = len(lines) * line_h
        ty = y0 + max(pad_y, (row_h - text_block_h) / 2.0)
        for i, line in enumerate(lines):
            pdf.set_xy(x + 0.5, ty + i * line_h)
            pdf.cell(w - 1.0, line_h, line, border=0, align=align)
        x += w
    pdf.set_xy(x0, y0 + row_h)
    return True


def _clean_filters(filters: dict | None) -> str:
    if not filters:
        return "All"
    parts = []
    for k, v in filters.items():
        if v is None or v == "" or str(v).lower() in ("all", "none"):
            continue
        if re.search(r"^(customer|supplier|product|warehouse|employee)$", str(k), re.I) and str(v).isdigit():
            continue
        parts.append(f"{k}: {v}")
    return " | ".join(parts) if parts else "All"


def build_report_html(
    title, df, period="", filters=None, summary=None, extra_html="", layout="landscape", report_key=None,
):
    co = get_company_info()
    raw = _safe_df(df)
    df = prettify_columns(prepare_report_dataframe(raw, report_key or title))
    filters = filters or {}
    filter_txt = _clean_filters(filters)
    cols = list(df.columns)
    numeric_cols = {}
    for c in cols:
        src = raw[c] if c in raw.columns else df[c]
        numeric_cols[c] = _is_numeric_col(c, src)
    css = _build_print_css(layout, len(cols))
    pcts = _width_pct(cols)
    colgroup = "".join(f'<col style="width:{p:.1f}%">' for p in pcts)

    def _cell_classes(c):
        parts = []
        if numeric_cols[c]:
            parts.append("num")
        if _is_wide_col(c):
            parts.append("wrap")
        if _is_code_col(c):
            parts.append("code-col")
        return " ".join(parts)

    thead = "".join(
        f"<th class=\"{_cell_classes(c)}\">{escape(str(c))}</th>" for c in cols
    )
    tbody = ""
    for _, row in df.iterrows():
        tbody += "<tr>" + "".join(
            f"<td class=\"{_cell_classes(c)}\">"
            f"{escape(_fmt_cell(row[c], numeric_cols[c]))}</td>"
            for c in cols
        ) + "</tr>"

    auto_summary = _numeric_summary(raw, report_key or title)
    merged_summary = {**auto_summary, **(summary or {})}
    summary_html = ""
    if merged_summary:
        summary_html = '<div class="summary-box">' + "".join(
            f"<div><b>{escape(str(k))}:</b> {escape(str(v))}</div>" for k, v in merged_summary.items()
        ) + "</div>"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
    {css}
    <script>function doPrint(){{ window.print(); }}</script></head><body>
    <div class="report-wrap">
    {company_report_header_html(ref_prefix="RPT")}
    <div class="report-title">{escape(title)}</div>
    <div class="meta-bar">
        <span><b>Period:</b> {escape(period or '—')}</span>
        <span><b>Filters:</b> {escape(filter_txt)}</span>
        <span><b>Records:</b> {len(df)}</span>
    </div>
    {summary_html}
    {extra_html}
    <table class="data report-grid"><colgroup>{colgroup}</colgroup><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
    {_report_signatures_html(report_key or title)}
    {_report_footer_html(report_key or title)}
    <p class="no-print"><button class="print-btn" onclick="doPrint()">Print Report</button></p>
    </div></body></html>"""


def _report_signatures_html(doc_label: str = "report", report_key: str | None = None) -> str:
    from erp_ui.document_print import (
        CASH_TRANSACTION_REPORTS,
        PRINT_STYLE_CASH,
        PRINT_STYLE_SYSTEM,
        signature_block_html,
    )
    key = report_key or doc_label
    if key in CASH_TRANSACTION_REPORTS:
        return signature_block_html(style=PRINT_STYLE_CASH)
    return signature_block_html(doc_label=doc_label, style=PRINT_STYLE_SYSTEM)


def _report_footer_html(report_key: str | None = None) -> str:
    from erp_ui.document_print import CASH_TRANSACTION_REPORTS, document_footer_html
    key = report_key or ""
    if key in CASH_TRANSACTION_REPORTS:
        return ""
    if key == "Journal Register":
        return document_footer_html(None, label="Prepared by")
    return document_footer_html(None)


def _ledger_labels(title):
    inc_lbl = "Receipt" if "Bank" in title else "Income"
    exp_lbl = "Payment" if "Bank" in title else "Expense"
    return inc_lbl, exp_lbl


def _ledger_english_labels(title):
    inc_lbl, exp_lbl = _ledger_labels(title)
    return {
        "title": title,
        "date": "Date",
        "particulars": "Particulars",
        "ref": "Ref",
        "inc": inc_lbl,
        "exp": exp_lbl,
        "balance": "Balance",
        "opening": "Opening Balance",
        "total_inc": f"Total {inc_lbl}",
        "total_exp": f"Total {exp_lbl}",
        "closing": "Closing Balance",
        "totals": "Totals",
        "period": "Period",
        "generated": "Generated",
        "page": "Page",
        "page_fmt": "A4 Portrait",
        "print": "Print",
        "confidential": "",
        "note": "",
    }


def _ledger_urdu_labels(title):
    is_bank = "Bank" in title
    return {
        "title": "روزنامچہ بینک" if is_bank else "روزنامچہ نقدی",
        "date": "تاریخ",
        "particulars": "تفصیل",
        "ref": "حوالہ",
        "inc": "وصولی" if is_bank else "آمدنی",
        "exp": "ادائیگی" if is_bank else "خرچ",
        "balance": "بیلنس",
        "opening": "ابتدائی بیلنس",
        "total_inc": "کل وصولی" if is_bank else "کل آمدنی",
        "total_exp": "کل ادائیگی" if is_bank else "کل خرچ",
        "closing": "اختتامی بیلنس",
        "totals": "کل",
        "period": "مدت",
        "generated": "تیاری",
        "page": "صفحہ",
        "page_fmt": "A4 عمودی",
        "print": "چھاپیں",
        "confidential": "داخلی",
        "note": "تفصیل اردو ترجمہ ہے؛ حوالہ نمبر اور رقوم ویسے ہی ہیں۔",
    }


_LEDGER_URDU_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400;600;700&display=swap');
html[lang="ur"] body,
html[lang="ur"] .report-wrap.ledger-a4 {
  font-family: 'Noto Nastaliq Urdu', 'Jameel Noori Nastaleeq', 'Arial', serif;
  direction: rtl;
  font-size: 15px;
  line-height: 1.85;
}
html[lang="ur"] .header h1 {
  font-size: 26px;
  line-height: 1.75;
}
html[lang="ur"] .header .sub {
  font-size: 13px;
  line-height: 1.7;
}
html[lang="ur"] .report-title {
  font-size: 22px;
  line-height: 1.9;
  padding: 12px 18px;
}
html[lang="ur"] .meta-bar {
  text-align: right;
  font-size: 14px;
  line-height: 1.9;
  padding: 12px 16px;
}
html[lang="ur"] .summary-box {
  text-align: right;
  font-size: 15px;
  line-height: 2;
  padding: 14px 18px;
}
html[lang="ur"] .summary-box div {
  min-width: 180px;
}
html[lang="ur"] table.data.ledger {
  direction: rtl;
}
html[lang="ur"] table.data.ledger col.col-date { width: 12%; min-width: 78px; }
html[lang="ur"] table.data.ledger col.col-part { width: 37%; }
html[lang="ur"] table.data.ledger col.col-ref { width: 10%; }
html[lang="ur"] table.data.ledger col.col-amt { width: 13.3%; }
html[lang="ur"] table.data.ledger th {
  font-size: 15px !important;
  font-weight: 700;
  padding: 10px 8px !important;
  line-height: 1.95 !important;
  text-transform: none;
  letter-spacing: 0;
  text-align: right;
}
html[lang="ur"] table.data.ledger th.date,
html[lang="ur"] table.data.ledger td.date {
  font-family: 'Segoe UI', Arial, sans-serif !important;
  font-size: 12px !important;
  line-height: 1.35 !important;
  white-space: nowrap !important;
  word-break: keep-all !important;
  direction: ltr !important;
  unicode-bidi: isolate !important;
  text-align: center !important;
  vertical-align: middle !important;
  padding: 8px 4px !important;
}
html[lang="ur"] table.data.ledger th.ref,
html[lang="ur"] table.data.ledger td.ref {
  font-family: 'Segoe UI', Arial, sans-serif !important;
  font-size: 12px !important;
  line-height: 1.35 !important;
  white-space: nowrap !important;
  direction: ltr !important;
  unicode-bidi: isolate !important;
  text-align: center !important;
}
html[lang="ur"] table.data.ledger td {
  font-size: 14px !important;
  padding: 9px 8px !important;
  line-height: 2 !important;
  text-align: right;
}
html[lang="ur"] table.data.ledger td.particulars {
  font-size: 15px !important;
  line-height: 2.15 !important;
  padding: 10px 8px !important;
}
html[lang="ur"] table.data.ledger th.num,
html[lang="ur"] table.data.ledger td.num {
  direction: ltr;
  unicode-bidi: embed;
  text-align: left;
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 13px !important;
  line-height: 1.5 !important;
}
html[lang="ur"] table.data.ledger tr.total-row td {
  font-size: 15px !important;
  line-height: 1.9 !important;
}
html[lang="ur"] .footer {
  font-size: 12px;
  line-height: 1.7;
}
html[lang="ur"] .ledger-note {
  font-size: 13px;
  line-height: 1.85;
  color: #64748b;
  margin: 0.35rem 0 0.65rem 0;
  text-align: right;
}
html[lang="ur"] .print-btn {
  font-size: 14px;
  padding: 10px 22px;
}
@media print {
  html[lang="ur"] body,
  html[lang="ur"] .report-wrap.ledger-a4 {
    font-size: 13pt;
    -webkit-print-color-adjust: economy;
    print-color-adjust: economy;
  }
  html[lang="ur"] .header h1 { font-size: 20pt; }
  html[lang="ur"] .report-title { font-size: 17pt; padding: 8pt 12pt; }
  html[lang="ur"] .meta-bar { font-size: 11pt; }
  html[lang="ur"] .summary-box { font-size: 11.5pt; line-height: 2.1; }
  html[lang="ur"] table.data.ledger th {
    font-size: 12pt !important;
    padding: 7pt 6pt !important;
    line-height: 2 !important;
  }
  html[lang="ur"] table.data.ledger td {
    font-size: 11.5pt !important;
    padding: 6pt 5pt !important;
    line-height: 2.1 !important;
  }
  html[lang="ur"] table.data.ledger td.particulars {
    font-size: 12.5pt !important;
    line-height: 2.25 !important;
  }
  html[lang="ur"] table.data.ledger th.date,
  html[lang="ur"] table.data.ledger td.date,
  html[lang="ur"] table.data.ledger th.ref,
  html[lang="ur"] table.data.ledger td.ref {
    font-size: 9.5pt !important;
    line-height: 1.3 !important;
    white-space: nowrap !important;
    text-align: center !important;
    direction: ltr !important;
    unicode-bidi: isolate !important;
  }
  html[lang="ur"] table.data.ledger td.num,
  html[lang="ur"] table.data.ledger th.num {
    font-size: 10.5pt !important;
  }
  html[lang="ur"] table.data.ledger tr.total-row td {
    font-size: 12pt !important;
  }
}
"""


def _fmt_rs(amount):
    return f"Rs. {float(amount or 0):,.2f}"


def _ledger_row_cells(r, inc_lbl, exp_lbl):
    inc = r.get("income") if r.get("income") not in (None, "") else r.get("Receipt", "")
    exp = r.get("expense") if r.get("expense") not in (None, "") else r.get("Payment", "")
    return (
        f"<tr>"
        f"<td class='date'>{escape(str(r.get('date', '')))}</td>"
        f"<td class='particulars'>{escape(str(r.get('particulars', '')))}</td>"
        f"<td class='ref'>{escape(str(r.get('ref', '')))}</td>"
        f"<td class='num'>{_fmt_cell(inc, True)}</td>"
        f"<td class='num'>{_fmt_cell(exp, True)}</td>"
        f"<td class='num'>{_fmt_cell(r.get('balance', ''), True)}</td>"
        f"</tr>"
    )


def build_ledger_html(title, opening, rows, total_in, total_out, closing, period, urdu=False):
    """Cash/Bank day book print HTML. urdu=True: labels + particulars in Urdu (director report only)."""
    from erp_ui.urdu_narration import translate_ledger_rows

    co = get_company_info()
    inc_lbl, exp_lbl = _ledger_labels(title)
    if urdu:
        cache = st.session_state.setdefault("_ledger_urdu_narration_cache", {})
        display_rows = translate_ledger_rows(rows, cache=cache)
    else:
        display_rows = rows
    L = _ledger_urdu_labels(title) if urdu else _ledger_english_labels(title)
    lang = "ur" if urdu else "en"
    css = PRINT_CSS_LEDGER
    if urdu:
        css = css.replace("</style>", f"{_LEDGER_URDU_CSS}</style>")
    period_safe = (period or "").replace("\u2014", "-").replace("—", "-")
    colgroup = (
        '<colgroup>'
        '<col class="col-date"><col class="col-part"><col class="col-ref">'
        '<col class="col-amt"><col class="col-amt"><col class="col-amt">'
        "</colgroup>"
    )
    thead = (
        "<thead><tr>"
        f"<th class='date'>{escape(L['date'])}</th>"
        f"<th>{escape(L['particulars'])}</th>"
        f"<th class='ref'>{escape(L['ref'])}</th>"
        f"<th class='num'>{escape(L['inc'])}</th>"
        f"<th class='num'>{escape(L['exp'])}</th>"
        f"<th class='num'>{escape(L['balance'])}</th>"
        "</tr></thead>"
    )
    tbody = "".join(_ledger_row_cells(r, inc_lbl, exp_lbl) for r in display_rows)
    tbody += (
        f"<tr class='total-row'>"
        f"<td colspan='3'><b>{escape(L['totals'])}</b></td>"
        f"<td class='num'><b>{total_in:,.2f}</b></td>"
        f"<td class='num'><b>{total_out:,.2f}</b></td>"
        f"<td class='num'><b>{closing:,.2f}</b></td></tr>"
    )
    note_html = (
        f"<p class='ledger-note'>{escape(L['note'])}</p>" if L.get("note") else ""
    )
    return f"""<!DOCTYPE html><html lang="{lang}" dir="{'rtl' if urdu else 'ltr'}"><head><meta charset="utf-8">
    <title>{escape(L['title'])}</title>
    {css}<script>function doPrint(){{ window.print(); }}</script></head><body>
    <div class="report-wrap ledger-a4">
    {company_letterhead_html()}
    <div class="report-title">{escape(L['title'])}</div>
    <div class="meta-bar"><span><b>{escape(L['period'])}:</b> {escape(period_safe)}</span>
    <span><b>{escape(L['generated'])}:</b> {_now_str()}</span>
    <span><b>{escape(L['page'])}:</b> {escape(L['page_fmt'])}</span></div>
    {note_html}
    <div class="summary-box">
        <div><b>{escape(L['opening'])}:</b> {_fmt_rs(opening)}</div>
        <div><b>{escape(L['total_inc'])}:</b> {_fmt_rs(total_in)}</div>
        <div><b>{escape(L['total_exp'])}:</b> {_fmt_rs(total_out)}</div>
        <div><b>{escape(L['closing'])}:</b> {_fmt_rs(closing)}</div>
    </div>
    <table class="data ledger">{colgroup}{thead}<tbody>{tbody}</tbody></table>
    {_ledger_print_signatures(title)}
    {_ledger_print_footer(title)}
    <p class="no-print"><button class="print-btn" onclick="doPrint()">{escape(L['print'])}</button></p>
    </div></body></html>"""


def _ledger_print_signatures(title: str) -> str:
    from erp_ui.document_print import is_cash_ledger_title
    if is_cash_ledger_title(title):
        return _report_signatures_html(report_key="Cash Book")
    return _report_signatures_html("ledger")


def _ledger_print_footer(title: str) -> str:
    from erp_ui.document_print import is_cash_ledger_title
    if is_cash_ledger_title(title):
        return _report_footer_html("Cash Book")
    return _report_footer_html()


def build_ledger_html_urdu(title, opening, rows, total_in, total_out, closing, period):
    return build_ledger_html(title, opening, rows, total_in, total_out, closing, period, urdu=True)


def build_ledger_pdf(title, opening, rows, total_in, total_out, closing, period):
    """A4 portrait PDF with fixed ledger column widths."""
    from fpdf import FPDF

    co = get_company_info()
    inc_lbl, exp_lbl = _ledger_labels(title)
    pdf = FPDF(orientation="P", format="A4")
    pdf.set_margins(_MARGIN_H, _MARGIN_V, _MARGIN_H)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN_V + 4)
    pdf.add_page()
    pw = pdf.w - pdf.l_margin - pdf.r_margin
    # mm widths: date, particulars, ref, income, expense, balance
    fracs = [0.12, 0.37, 0.10, 0.135, 0.135, 0.14]
    col_ws = [pw * f for f in fracs]
    row_h = 5.0
    hdr_h = 6.5

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 6, _pdf_clip(co["name"], 72), ln=True)
    pdf.set_font("Helvetica", size=8)
    if co.get("address"):
        pdf.multi_cell(0, 4, _pdf_clip(co["address"], 180))
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _pdf_clip(title, 80), ln=True)
    pdf.set_font("Helvetica", size=8)
    period_safe = _pdf_clip(period or "-")
    pdf.cell(0, 4, _pdf_clip(f"Period: {period_safe}  |  Generated: {_now_str()}"), ln=True)
    pdf.cell(
        0, 4,
        _pdf_clip(
            f"Opening {opening:,.2f}  |  {inc_lbl} {total_in:,.2f}  |  "
            f"{exp_lbl} {total_out:,.2f}  |  Closing {closing:,.2f}"
        ),
        ln=True,
    )
    pdf.ln(2)

    headers = ["Date", "Particulars", "Ref", inc_lbl, exp_lbl, "Balance"]

    def _draw_header():
        pdf.set_font("Helvetica", "B", 9)
        for h, w in zip(headers, col_ws):
            pdf.cell(w, hdr_h, h[: int(max(4, w / 2))], border=1, align="R" if h in (inc_lbl, exp_lbl, "Balance") else "L")
        pdf.ln(hdr_h)

    _draw_header()
    pdf.set_font("Helvetica", size=8.0)

    for r in rows:
        part = str(r.get("particulars", "") or "")
        inc = r.get("income") if r.get("income") not in (None, "") else r.get("Receipt", "")
        exp = r.get("expense") if r.get("expense") not in (None, "") else r.get("Payment", "")
        cells = [
            (str(r.get("date", "")), col_ws[0], False, False),
            (part, col_ws[1], False, True),
            (str(r.get("ref", "")), col_ws[2], False, False),
            (_fmt_cell(inc, True), col_ws[3], True, False),
            (_fmt_cell(exp, True), col_ws[4], True, False),
            (_fmt_cell(r.get("balance", ""), True), col_ws[5], True, False),
        ]
        est = len(_pdf_wrap_lines(pdf, part, col_ws[1], max_lines=6))
        est_h = max(4.5, est * 3.8 + 1.4)
        if pdf.get_y() + est_h > pdf.h - 16:
            pdf.add_page()
            _draw_header()
            pdf.set_font("Helvetica", size=8.0)
        if not _pdf_draw_table_row(pdf, cells, line_h=3.8, pad_y=0.7):
            pdf.add_page()
            _draw_header()
            pdf.set_font("Helvetica", size=8.0)
            _pdf_draw_table_row(pdf, cells, line_h=3.8, pad_y=0.7)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col_ws[0] + col_ws[1] + col_ws[2], row_h, "Totals", border=1)
    pdf.cell(col_ws[3], row_h, f"{total_in:,.2f}", border=1, align="R")
    pdf.cell(col_ws[4], row_h, f"{total_out:,.2f}", border=1, align="R")
    pdf.cell(col_ws[5], row_h, f"{closing:,.2f}", border=1, align="R")
    pdf.ln(row_h)
    return bytes(pdf.output())


def build_report_pdf(title, df, period="", filters=None, summary=None, layout="landscape", report_key=None):
    from fpdf import FPDF

    raw = _safe_df(df)
    prep = prepare_report_dataframe(raw, report_key or title)
    df = prettify_columns(prep)
    co = get_company_info()
    filter_txt = _clean_filters(filters or {})

    ncol = len(df.columns)
    orient = _pdf_orientation(layout, ncol)

    pdf = FPDF(orientation=orient, format="A4")
    pdf.set_margins(_MARGIN_H, _MARGIN_V, _MARGIN_H)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN_V + 4)
    pdf.add_page()
    pw = pdf.w - pdf.l_margin - pdf.r_margin

    if print_company_header_enabled():
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 7, _pdf_clip(co["name"], 70), ln=True)
        pdf.set_font("Helvetica", size=8)
        if co.get("address"):
            pdf.multi_cell(0, 4, _pdf_clip(co["address"], 200))
    pdf.set_font("Helvetica", "B", 11)
    profile = _report_profile_key(report_key or title) or (title or "")
    pdf.cell(0, 7, _pdf_clip(str(profile), 90), ln=True)
    party = _party_from_df_attrs(raw)
    if party.get("name") or party.get("code"):
        pdf.set_font("Helvetica", "B", 10)
        party_line = " / ".join(
            x for x in [
                (party.get("kind") or "Party").title(),
                str(party.get("code") or "").strip(),
                str(party.get("name") or "").strip(),
            ] if x
        )
        pdf.cell(0, 5, _pdf_clip(party_line, 100), ln=True)
        pdf.set_font("Helvetica", size=8)
        extra = "  |  ".join(
            x for x in [
                f"Phone: {party['phone']}" if party.get("phone") else "",
                str(party.get("address") or "")[:80],
            ] if x
        )
        if extra:
            pdf.cell(0, 4, _pdf_clip(extra, 120), ln=True)
    pdf.set_font("Helvetica", size=8)
    period_safe = _pdf_clip(period or "-")
    pdf.cell(0, 4, _pdf_clip(f"Period: {period_safe}"), ln=True)
    filter_txt2 = filter_txt
    if filter_txt2.strip().lower() in ("all", "-", ""):
        filter_txt2 = ""
    if filter_txt2:
        pdf.cell(0, 4, _pdf_clip(f"Filters: {filter_txt2}", 100), ln=True)
    mode = _ledger_report_kind(report_key or title)
    if mode:
        pdf.cell(
            0, 4,
            _pdf_clip(
                f"Format: {'Detailed (invoice lines)' if mode == 'detailed' else 'Summary (voucher-wise)'}"
            ),
            ln=True,
        )
    pdf.cell(0, 4, _pdf_clip(f"Generated: {_now_str()}  |  Records: {len(df)}"), ln=True)
    merged = {**_numeric_summary(raw, report_key or title), **(summary or {})}
    if not merged and mode:
        merged = _ledger_summary_from_df(raw, profile, summary)
    if merged:
        pdf.ln(1)
        line = "  |  ".join(f"{k}: {v}" for k, v in list(merged.items())[:6])
        pdf.multi_cell(0, 4, _pdf_clip(line, 200))
    pdf.ln(3)

    cols = list(df.columns)
    if not cols:
        pdf.cell(0, 8, "No data.", ln=True)
    else:
        weights = column_width_weights(cols)
        total_w = sum(weights) or 1.0
        col_ws = [pw * (w / total_w) for w in weights]
        line_h = 3.8
        hdr_h = 6.5
        is_ledger = bool(_ledger_report_kind(report_key or title) or re.search(r"ledger", str(title or ""), re.I))

        def _draw_header():
            pdf.set_font("Helvetica", "B", 8)
            hdr_cells = [(_pdf_safe_text(str(c)), w, False, False) for c, w in zip(cols, col_ws)]
            if not _pdf_draw_table_row(pdf, hdr_cells, line_h=line_h, pad_y=1.0):
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 8)
                _pdf_draw_table_row(pdf, hdr_cells, line_h=line_h, pad_y=1.0)

        _draw_header()
        pdf.set_font("Helvetica", size=7.5 if is_ledger else 8.0)
        for _, row in df.iterrows():
            cells = []
            for c, w in zip(cols, col_ws):
                src = prep[c] if c in prep.columns else df[c]
                numeric = _is_numeric_col(c, src)
                wrap = _is_wide_col(c) or (is_ledger and re.search(r"narration|description|particular", str(c), re.I))
                txt = _fmt_cell(row[c], numeric)
                cells.append((txt, w, numeric, wrap))

            # Estimate height for page break before drawing
            est_lines = 1
            for text, w, _right, wrap in cells:
                if wrap:
                    est_lines = max(est_lines, len(_pdf_wrap_lines(pdf, text, w, max_lines=8)))
            est_h = max(line_h + 1.6, est_lines * line_h + 1.6)
            if pdf.get_y() + est_h > pdf.h - pdf.b_margin - 4:
                pdf.add_page()
                _draw_header()
                pdf.set_font("Helvetica", size=7.5 if is_ledger else 8.0)

            if not _pdf_draw_table_row(pdf, cells, line_h=line_h, pad_y=0.7):
                pdf.add_page()
                _draw_header()
                pdf.set_font("Helvetica", size=7.5 if is_ledger else 8.0)
                _pdf_draw_table_row(pdf, cells, line_h=line_h, pad_y=0.7)

        # Ledger: period totals + closing balance at bottom of table
        if mode:
            led_sum = _ledger_summary_from_df(raw, profile, summary)
            if pdf.get_y() + line_h * 4 > pdf.h - pdf.b_margin - 4:
                pdf.add_page()
                _draw_header()
            pdf.set_font("Helvetica", "B", 8)

            def _ledger_footer_row(label: str, *, debit=None, credit=None, balance=None):
                cells = []
                for i, (c, w) in enumerate(zip(cols, col_ws)):
                    label_l = str(c).lower()
                    if i == 0:
                        txt = label
                        right = False
                    elif re.search(r"debit", label_l) and debit is not None:
                        txt = str(debit)
                        right = True
                    elif re.search(r"credit", label_l) and credit is not None:
                        txt = str(credit)
                        right = True
                    elif re.search(r"balance", label_l) and balance is not None:
                        txt = str(balance)
                        right = True
                    else:
                        txt = ""
                        right = False
                    cells.append((txt, w, right, False))
                if pdf.get_y() + line_h * 2 > pdf.h - pdf.b_margin - 2:
                    pdf.add_page()
                    _draw_header()
                    pdf.set_font("Helvetica", "B", 8)
                _pdf_draw_table_row(pdf, cells, line_h=line_h, pad_y=0.8)

            _ledger_footer_row(
                "Period totals",
                debit=led_sum.get("Total Debit", ""),
                credit=led_sum.get("Total Credit", ""),
            )
            _ledger_footer_row(
                "Closing Balance",
                balance=led_sum.get("Closing", ""),
            )
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(
                0, 6,
                _pdf_clip(f"Closing Balance: {led_sum.get('Closing', '-')}"),
                ln=True,
            )

    return bytes(pdf.output())


def df_to_excel_bytes(df, report_key=None):
    prep = prepare_report_dataframe(_safe_df(df), report_key)
    df = prettify_columns(prep)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
        ws = writer.sheets["Report"]
        for col_cells in ws.columns:
            letter = col_cells[0].column_letter
            header_len = len(str(col_cells[0].value or ""))
            max_len = header_len
            for cell in col_cells[1:51]:
                if cell.value is not None:
                    max_len = max(max_len, min(len(str(cell.value)), 40))
            ws.column_dimensions[letter].width = min(42, max(9, max_len + 2))
    return buf.getvalue()


def df_to_csv_bytes(df, report_key=None):
    return prettify_columns(prepare_report_dataframe(_safe_df(df), report_key)).to_csv(index=False).encode("utf-8")


ITEMWISE_DETAIL_CSS = _PRINT_BASE + _PRINT_INK_SAVE + """
@page { size: A4 portrait; margin: 8mm 6mm; }
.itemwise-wrap { max-width: 210mm; }
.itemwise-head {
  background: transparent; border: 1px solid #333; padding: 8px 12px; margin: 18px 0 6px 0;
  font-weight: 700; font-size: 13px; color: #111;
}
table.itemwise-lines { margin-bottom: 4px; }
table.itemwise-lines th { font-size: 11px; padding: 8px 6px; background: transparent; color: #111; border: 1px solid #333; }
table.itemwise-lines td { font-size: 11px; padding: 7px 6px; border: 1px solid #333; background: transparent; }
table.itemwise-lines tr.item-sub td { background: transparent; font-weight: 700; border-top: 2px solid #111; }
table.itemwise-lines tr.grand-total td {
  background: transparent; color: #111; font-weight: 700;
  border-top: 2px solid #111; border-bottom: 2px solid #111;
}
.col-date { width: 10%; }
.col-inv { width: 13%; }
.col-name { width: 26%; }
.col-city { width: 12%; }
.col-qty { width: 10%; }
.col-rate { width: 10%; }
.col-amt { width: 11%; }
table.itemwise-lines .col-inv { min-width: 5.5em; }
""" + _PRINT_MEDIA


def _fmt_date_display(val) -> str:
    if not val:
        return ""
    s = str(val)[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return s


def _itemwise_groups(df: pd.DataFrame) -> list[tuple[str, str, pd.DataFrame]]:
    raw = _safe_df(df)
    if raw.empty:
        return []
    key = "product_id" if "product_id" in raw.columns else "product_code"
    groups = []
    for _, chunk in raw.groupby(key, sort=False):
        code = str(chunk.iloc[0].get("product_code", "") or "")
        name = str(chunk.iloc[0].get("product_name", "") or "")
        groups.append((code, name, chunk))
    return groups


def build_itemwise_detail_html(title, df, period="", filters=None, party_col="name"):
    """Grouped-by-item print layout (Finance Manager Item Wise Sale/Purchase Detail)."""
    co = get_company_info()
    raw = _safe_df(df)
    filter_txt = _clean_filters(filters or {})
    is_purchase = "purchase" in (title or "").lower()
    party_label = "Supplier" if is_purchase else "Name"
    sections = []
    grand_qty = grand_amt = 0.0
    row_count = 0

    for code, pname, chunk in _itemwise_groups(raw):
        sub_qty = float(chunk["quantity"].sum()) if "quantity" in chunk.columns else 0.0
        sub_amt = float(chunk["amount"].sum()) if "amount" in chunk.columns else 0.0
        grand_qty += sub_qty
        grand_amt += sub_amt
        head = f"Item Code: {escape(code)}&nbsp;&nbsp;&nbsp;{escape(pname)}"
        rows_html = ""
        for _, r in chunk.iterrows():
            row_count += 1
            rows_html += (
                "<tr>"
                f"<td>{escape(_fmt_date_display(r.get('date')))}</td>"
                f"<td>{escape(str(r.get('invoice_no', '')))}</td>"
                f"<td class='wrap'>{escape(str(r.get(party_col, r.get('name', ''))))}</td>"
                f"<td>{escape(str(r.get('city', '') or ''))}</td>"
                f"<td class='num'>{float(r.get('quantity') or 0):,.2f}</td>"
                f"<td class='num'>{float(r.get('rate') or 0):,.2f}</td>"
                f"<td class='num'>{float(r.get('amount') or 0):,.2f}</td>"
                "</tr>"
            )
        rows_html += (
            f"<tr class='item-sub'><td colspan='4'><b>Item Total</b></td>"
            f"<td class='num'><b>{sub_qty:,.2f}</b></td><td></td>"
            f"<td class='num'><b>{sub_amt:,.2f}</b></td></tr>"
        )
        sections.append(
            f'<div class="itemwise-head">{head}</div>'
            f'<table class="data itemwise-lines"><colgroup>'
            '<col class="col-date"><col class="col-inv"><col class="col-name">'
            '<col class="col-city"><col class="col-qty"><col class="col-rate"><col class="col-amt">'
            "</colgroup><thead><tr>"
            f"<th>Date</th><th>Invoice #</th><th>{escape(party_label)}</th><th>City</th>"
            "<th class='num'>Quantity</th><th class='num'>Rate</th><th class='num'>Amount</th>"
            f"</tr></thead><tbody>{rows_html}</tbody></table>"
        )

    if not sections:
        body_tables = "<p>No data for selected period.</p>"
    else:
        grand_row = (
            f"<tr class='grand-total'><td colspan='4'><b>Report Total ({row_count} lines)</b></td>"
            f"<td class='num'><b>{grand_qty:,.2f}</b></td><td></td>"
            f"<td class='num'><b>{grand_amt:,.2f}</b></td></tr>"
        )
        body_tables = "".join(sections) + (
            '<table class="data itemwise-lines"><tbody>' + grand_row + "</tbody></table>"
        )

    period_safe = (period or "").replace("\u2014", "-").replace("—", "-")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
    <style>{ITEMWISE_DETAIL_CSS}</style>
    <script>function doPrint(){{ window.print(); }}</script></head><body>
    <div class="report-wrap itemwise-wrap">
    {company_letterhead_html()}
    <div class="report-title">{escape(title)}</div>
    <div class="meta-bar">
      <span><b>Period:</b> {escape(period_safe)}</span>
      <span><b>Filters:</b> {escape(filter_txt)}</span>
      <span><b>Generated:</b> {_now_str()}</span>
      <span><b>Items:</b> {len(_itemwise_groups(raw))}</span>
    </div>
    {body_tables}
    {_report_signatures_html(report_key=title)}
    {_report_footer_html(title)}
    <p class="no-print"><button class="print-btn" onclick="doPrint()">Print Report</button></p>
    </div></body></html>"""


def itemwise_detail_toolbar(df, title, filename, period="", filters=None, key_prefix="rpt"):
    """Export strip for item-wise sale/purchase detail (grouped print + flat Excel/CSV)."""
    raw = _safe_df(df)
    if raw.empty:
        st.caption("No data to export.")
        return
    report_key = title
    include_hdr = use_print_company_header_checkbox(key_prefix)
    with print_company_header_scope(include_hdr):
        html = build_itemwise_detail_html(title, raw, period, filters)
    export_df = prepare_report_dataframe(raw, report_key)
    summary = _numeric_summary(raw, report_key)
    preview_h = min(820, 240 + len(raw) * 4)
    with st.expander("Print Preview (grouped by item)", expanded=True):
        components.html(html, height=preview_h, scrolling=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.download_button("CSV", df_to_csv_bytes(raw, report_key), f"{filename}.csv", "text/csv", key=f"{key_prefix}_csv")
    c2.download_button("Excel", df_to_excel_bytes(raw, report_key), f"{filename}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key_prefix}_xlsx")
    c3.download_button("Print (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_html")
    try:
        pdf = build_report_pdf(title, raw, period, filters, summary, layout="portrait_full", report_key=report_key)
        c4.download_button("Save PDF", pdf, f"{filename}.pdf", "application/pdf", key=f"{key_prefix}_pdf")
    except Exception as ex:
        c4.download_button("Save PDF (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_pdffb")
        st.caption(f"PDF: {ex} — use Print (HTML) for grouped layout.")
    if c5.button("Open Print Dialog", key=f"{key_prefix}_print"):
        components.html(html.replace("</body>", "<script>window.onload=function(){window.print();}</script></body>"), height=0)


DAILY_ACTIVITY_CSS = _PRINT_BASE + _PRINT_INK_SAVE + """
@page { size: A4 portrait; margin: 8mm 7mm; }
.daily-wrap { max-width: 210mm; }
.daily-module {
  margin: 16px 0 4px 0; padding: 6px 10px;
  border: 2px solid #111; font-weight: 700; font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.04em; background: transparent;
}
.daily-type-head {
  margin: 12px 0 4px 0; padding: 7px 10px;
  border: 1px solid #333; border-left: 4px solid #111;
  font-weight: 700; font-size: 12px; background: transparent;
}
.daily-type-meta { font-weight: 500; font-size: 11px; float: right; }
table.daily-lines { margin-bottom: 2px; width: 100%; border-collapse: collapse; }
table.daily-lines th {
  font-size: 10px; padding: 6px 5px; background: transparent; color: #111;
  border: 1px solid #333; text-align: left;
}
table.daily-lines td { font-size: 10px; padding: 5px 5px; border: 1px solid #333; }
table.daily-lines td.num, table.daily-lines th.num { text-align: right; }
table.daily-lines td.wrap { word-break: break-word; }
table.daily-lines tr.type-sub td {
  font-weight: 700; border-top: 2px solid #111; background: transparent;
}
table.daily-lines tr.module-sub td {
  font-weight: 700; border-top: 2px solid #111; border-bottom: 1px solid #111;
}
table.daily-lines tr.grand-total td {
  font-weight: 700; border-top: 2px solid #111; border-bottom: 2px solid #111;
}
.daily-summary-grid {
  display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 8px 0 12px 0;
  padding: 8px 10px; border: 1px solid #333; font-size: 11px;
}
""" + _PRINT_MEDIA


def daily_activity_groups(df: pd.DataFrame) -> list[tuple[str, str, pd.DataFrame]]:
    """Group rows by module then voucher_type (preserves existing sort)."""
    raw = _safe_df(df)
    if raw.empty:
        return []
    groups = []
    if "module" not in raw.columns or "voucher_type" not in raw.columns:
        groups.append(("", "All vouchers", raw))
        return groups
    for (module, vtype), chunk in raw.groupby(["module", "voucher_type"], sort=False):
        groups.append((str(module or ""), str(vtype or "Other"), chunk))
    return groups


def build_daily_activity_html(title, df, period="", filters=None):
    """Heading-wise / voucher-type-wise Daily Activity print layout."""
    co = get_company_info()
    raw = _safe_df(df)
    filter_txt = _clean_filters(filters or {})
    groups = daily_activity_groups(raw)
    sections = []
    grand_amt = 0.0
    grand_count = 0
    current_module = None
    module_amt = 0.0
    module_count = 0
    type_summary_bits = []

    def _flush_module_total():
        nonlocal module_amt, module_count
        if current_module is None:
            return ""
        return (
            f'<table class="data daily-lines"><tbody>'
            f'<tr class="module-sub"><td colspan="5"><b>{escape(current_module)} total '
            f'({module_count} voucher{"s" if module_count != 1 else ""})</b></td>'
            f'<td class="num"><b>{module_amt:,.2f}</b></td>'
            f'<td colspan="2"></td></tr></tbody></table>'
        )

    for module, vtype, chunk in groups:
        if module != current_module:
            if current_module is not None:
                sections.append(_flush_module_total())
            current_module = module
            module_amt = 0.0
            module_count = 0
            if module:
                sections.append(f'<div class="daily-module">{escape(module)}</div>')

        sub_amt = 0.0
        if "amount" in chunk.columns:
            sub_amt = float(pd.to_numeric(chunk["amount"], errors="coerce").fillna(0).sum())
        n = len(chunk)
        grand_amt += sub_amt
        grand_count += n
        module_amt += sub_amt
        module_count += n
        type_summary_bits.append(f"{vtype}: {n}")

        head = (
            f'{escape(vtype)}'
            f'<span class="daily-type-meta">{n} voucher{"s" if n != 1 else ""}'
            f' &nbsp;|&nbsp; Amount: {sub_amt:,.2f}</span>'
            f'<div style="clear:both"></div>'
        )
        rows_html = ""
        for seq, (_, r) in enumerate(chunk.iterrows(), start=1):
            amt_raw = r.get("amount")
            try:
                amt_txt = f"{float(amt_raw):,.2f}" if amt_raw not in (None, "") and str(amt_raw).strip() != "" else ""
            except (TypeError, ValueError):
                amt_txt = str(amt_raw or "")
            vdate = str(r.get("voucher_date") or "")[:10]
            rows_html += (
                "<tr>"
                f"<td>{seq}</td>"
                f"<td>{escape(str(r.get('voucher_no') or ''))}</td>"
                f"<td>{escape(_fmt_date_display(vdate))}</td>"
                f"<td class='wrap'>{escape(str(r.get('party') or ''))}</td>"
                f"<td class='wrap'>{escape(str(r.get('particulars') or '')[:120])}</td>"
                f"<td class='num'>{escape(amt_txt)}</td>"
                f"<td>{escape(str(r.get('status') or ''))}</td>"
                f"<td class='wrap'>{escape(str(r.get('user') or ''))}</td>"
                "</tr>"
            )
        rows_html += (
            f"<tr class='type-sub'><td colspan='5'><b>{escape(vtype)} subtotal</b></td>"
            f"<td class='num'><b>{sub_amt:,.2f}</b></td>"
            f"<td colspan='2'></td></tr>"
        )
        sections.append(
            f'<div class="daily-type-head">{head}</div>'
            f'<table class="data daily-lines"><thead><tr>'
            "<th style='width:5%'>#</th>"
            "<th style='width:11%'>Voucher No</th>"
            "<th style='width:9%'>Date</th>"
            "<th style='width:26%'>Party / GL Head</th>"
            "<th style='width:18%'>Particulars</th>"
            "<th class='num' style='width:11%'>Amount</th>"
            "<th style='width:9%'>Status</th>"
            "<th style='width:11%'>User</th>"
            f"</tr></thead><tbody>{rows_html}</tbody></table>"
        )

    if current_module is not None:
        sections.append(_flush_module_total())

    if not sections:
        body = "<p>No financial vouchers for the selected day.</p>"
    else:
        body = "".join(sections) + (
            f'<table class="data daily-lines"><tbody>'
            f'<tr class="grand-total"><td colspan="5"><b>Day total ({grand_count} vouchers)</b></td>'
            f'<td class="num"><b>{grand_amt:,.2f}</b></td>'
            f'<td colspan="2"></td></tr></tbody></table>'
        )

    type_counts = " · ".join(type_summary_bits[:12])
    if len(type_summary_bits) > 12:
        type_counts += " …"
    summary_html = (
        f'<div class="daily-summary-grid">'
        f'<div><b>Total vouchers:</b> {grand_count}</div>'
        f'<div><b>Total amount:</b> {grand_amt:,.2f}</div>'
        f'<div><b>By type:</b> {escape(type_counts) if type_counts else "—"}</div>'
        f"</div>"
    )

    ref = datetime.now().strftime("%Y%m%d%H%M%S")
    period_safe = (period or "").replace("\u2014", "-").replace("—", "-")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
    <style>{DAILY_ACTIVITY_CSS}</style>
    <script>function doPrint(){{ window.print(); }}</script></head><body>
    <div class="report-wrap daily-wrap">
    {company_report_header_html(ref_prefix="RPT")}
    <div class="report-title">{escape(title)}</div>
    <div class="meta-bar">
        <span><b>Period:</b> {escape(period_safe or '—')}</span>
        <span><b>Filters:</b> {escape(filter_txt)}</span>
        <span><b>Sections:</b> {len(groups)}</span>
    </div>
    {summary_html}
    {body}
    {_report_signatures_html(report_key=title)}
    {_report_footer_html(title)}
    <p class="no-print"><button class="print-btn" onclick="doPrint()">Print Report</button></p>
    </div></body></html>"""


def daily_activity_toolbar(df, title, filename, period="", filters=None, key_prefix="rpt"):
    """Export strip for Daily Activity (heading-wise voucher sections)."""
    raw = _safe_df(df)
    if raw.empty:
        st.caption("No data to export.")
        return
    report_key = title
    include_hdr = use_print_company_header_checkbox(key_prefix)
    with print_company_header_scope(include_hdr):
        html = build_daily_activity_html(title, raw, period, filters)
    summary = _numeric_summary(raw, report_key)
    preview_h = min(860, 260 + len(raw) * 18)
    with st.expander("Print Preview (heading-wise by voucher type)", expanded=True):
        components.html(html, height=preview_h, scrolling=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.download_button("CSV", df_to_csv_bytes(raw, report_key), f"{filename}.csv", "text/csv", key=f"{key_prefix}_csv")
    c2.download_button("Excel", df_to_excel_bytes(raw, report_key), f"{filename}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key_prefix}_xlsx")
    c3.download_button("Print (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_html")
    try:
        # Prefer grouped HTML for PDF fallback; flat PDF still available via library path
        pdf = build_report_pdf(title, raw, period, filters, summary, layout="portrait_full", report_key=report_key)
        c4.download_button("Save PDF", pdf, f"{filename}.pdf", "application/pdf", key=f"{key_prefix}_pdf")
    except Exception as ex:
        c4.download_button("Save PDF (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_pdffb")
        st.caption(f"PDF: {ex} — use Print (HTML) for heading-wise layout.")
    if c5.button("Open Print Dialog", key=f"{key_prefix}_print"):
        components.html(html.replace("</body>", "<script>window.onload=function(){window.print();}</script></body>"), height=0)


def _ledger_report_kind(title: str | None) -> str | None:
    """Return 'simple' or 'detailed' for party/GL ledgers, else None."""
    key = _report_profile_key(title) or (title or "")
    if key in ("Customer Ledger (Detailed)", "Supplier Ledger (Detailed)"):
        return "detailed"
    if key in ("Customer Ledger", "Supplier Ledger", "Account Ledger", "Employee Ledger"):
        return "simple"
    low = (title or "").lower()
    if "ledger (detailed)" in low or "detailed ledger" in low:
        return "detailed"
    if "ledger" in low and any(x in low for x in ("customer", "supplier", "account", "employee")):
        return "simple"
    return None


def _party_from_df_attrs(df: pd.DataFrame) -> dict:
    try:
        attrs = getattr(df, "attrs", {}) or {}
        party = attrs.get("ledger_party") or {}
        if party:
            return dict(party)
        summary = attrs.get("ledger_summary") or {}
        if summary.get("party_name") or summary.get("name"):
            return {
                "code": summary.get("party_code") or summary.get("code") or "",
                "name": summary.get("party_name") or summary.get("name") or "",
            }
    except Exception:
        pass
    return {}


def _fmt_dr_cr_amount(val) -> str:
    """Signed balance for print: positive Debit, negative Credit (Finance Manager)."""
    try:
        v = float(val or 0)
    except (TypeError, ValueError):
        v = 0.0
    if abs(v) < 0.005:
        return "0.00"
    side = "Dr" if v > 0 else "Cr"
    return f"{abs(v):,.2f} {side}"


def _ledger_summary_from_df(df: pd.DataFrame, title: str, summary: dict | None = None) -> dict:
    out = dict(summary or {})
    try:
        ls = (getattr(df, "attrs", {}) or {}).get("ledger_summary") or {}
        if ls:
            out.setdefault("Opening", _fmt_dr_cr_amount(ls.get("opening")))
            out.setdefault("Total Debit", f"{float(ls.get('period_debit') or 0):,.2f}")
            out.setdefault("Total Credit", f"{float(ls.get('period_credit') or 0):,.2f}")
            closing_val = ls.get("closing")
            # Detailed ledgers: prefer last non-empty Balance cell when present
            if _ledger_report_kind(title) == "detailed" or "detailed" in str(title or "").lower():
                bal_col = None
                for c in df.columns:
                    if re.search(r"^balance$", str(c), re.I):
                        bal_col = c
                        break
                if bal_col is not None:
                    for v in reversed(list(df[bal_col].tolist())):
                        s = str(v or "").strip()
                        if s and s not in ("None", "nan", "0", "0.0", "0.00"):
                            # Keep formatted Dr/Cr string if already display text
                            if re.search(r"\b(Dr|Cr)\b", s, re.I):
                                out["Closing"] = s
                                closing_val = None
                            else:
                                try:
                                    closing_val = float(str(s).replace(",", "").split()[0])
                                except (TypeError, ValueError):
                                    pass
                            break
            if closing_val is not None and "Closing" not in out:
                out["Closing"] = _fmt_dr_cr_amount(closing_val)
            elif "Closing" not in out:
                out["Closing"] = _fmt_dr_cr_amount(ls.get("closing"))
    except Exception:
        pass
    if not out:
        out = summary_keys_for_report(title, df)
    return out


_PARTY_LEDGER_CSS_EXTRA = """
.party-ledger-card {
  border: 1px solid #000; padding: 10px 12px; margin: 8px 0 10px 0;
  display: grid; grid-template-columns: 1.4fr 1fr; gap: 8px 16px;
}
.party-ledger-card .party-name { font-size: 16px; font-weight: 700; margin: 0 0 4px 0; }
.party-ledger-card .party-meta { font-size: 11px; line-height: 1.45; margin: 0; }
.party-ledger-card .kpi { font-size: 11px; }
.party-ledger-card .kpi b { display: inline-block; min-width: 7.5rem; }
table.data.party-ledger th { font-size: 10px; padding: 5px 4px; }
table.data.party-ledger td { font-size: 10px; padding: 4px; vertical-align: top; }
table.data.party-ledger td.wrap { white-space: normal; word-break: break-word; line-height: 1.35; }
table.data.party-ledger tr.opening-row td { font-weight: 700; }
table.data.party-ledger tr.doc-row td { font-weight: 600; }
table.data.party-ledger tr.line-row td.narration { padding-left: 14px; font-weight: 400; }
table.data.party-ledger tr.total-row td { font-weight: 700; border-top: 2px solid #000; }
.ledger-note-sm { font-size: 10px; color: #333; margin: 6px 0 0 0; }
"""


def build_party_ledger_html(
    title, df, period="", filters=None, summary=None, layout=None, report_key=None, party=None,
):
    """Professional customer / supplier / account ledger print (simple + detailed)."""
    co = get_company_info()
    raw = _safe_df(df)
    kind = _ledger_report_kind(report_key or title) or "simple"
    layout = layout or ("landscape" if kind == "detailed" else "portrait_full")
    prep = prepare_report_dataframe(raw, report_key or title)
    view = prettify_columns(prep)
    party = party or _party_from_df_attrs(raw)
    # Title may already include party name ("Supplier Ledger — X"); keep short report label
    profile = _report_profile_key(report_key or title) or title
    display_title = profile

    cols = list(view.columns)
    numeric_cols = {}
    for c in cols:
        src = prep[c] if c in prep.columns else view[c]
        numeric_cols[c] = _is_numeric_col(c, src)

    css = _build_print_css(layout, len(cols)).replace(
        "</style>", f"{_PARTY_LEDGER_CSS_EXTRA}</style>",
    )
    pcts = _width_pct(cols)
    colgroup = "".join(f'<col style="width:{p:.1f}%">' for p in pcts)

    def _cell_classes(c, *, narration=False):
        parts = []
        if numeric_cols.get(c):
            parts.append("num")
        if _is_wide_col(c) or narration:
            parts.append("wrap")
        if narration:
            parts.append("narration")
        if _is_code_col(c):
            parts.append("code-col")
        return " ".join(parts)

    thead = "".join(
        f"<th class=\"{_cell_classes(c)}\">{escape(str(c))}</th>" for c in cols
    )

    # Detect narration / type columns after prettify
    narr_cols = {c for c in cols if re.search(r"narration|description|particular", str(c), re.I)}
    type_cols = [c for c in cols if re.search(r"^type$|voucher type", str(c), re.I)]
    date_cols = [c for c in cols if re.search(r"^date$", str(c), re.I)]

    tbody = ""
    for _, row in view.iterrows():
        row_cls = []
        date_val = str(row[date_cols[0]] if date_cols else row.get(cols[0], "") or "")
        type_val = str(row[type_cols[0]] if type_cols else "").strip().upper()
        narr0 = ""
        for nc in narr_cols:
            narr0 = str(row.get(nc) or "")
            if narr0:
                break
        if date_val.lower().startswith("open") or type_val in ("OB",) or "balance b/f" in narr0.lower() or "previous balance" in narr0.lower() or "opening" in narr0.lower():
            row_cls.append("opening-row")
        elif kind == "detailed" and type_val in ("SAL", "PUR", "SI", "PI", "SR", "PR"):
            row_cls.append("doc-row")
        elif kind == "detailed" and not type_val and narr0:
            row_cls.append("line-row")

        cls_attr = f" class=\"{' '.join(row_cls)}\"" if row_cls else ""
        cells = []
        for c in cols:
            is_narr = c in narr_cols
            val = row[c]
            if is_narr:
                val = clean_ledger_narration(val)
            cells.append(
                f"<td class=\"{_cell_classes(c, narration=is_narr)}\">"
                f"{escape(_fmt_cell(val, numeric_cols.get(c)))}</td>"
            )
        tbody += f"<tr{cls_attr}>" + "".join(cells) + "</tr>"

    merged_summary = _ledger_summary_from_df(raw, profile, summary)
    # Period totals row (debit / credit)
    total_cells = []
    for i, c in enumerate(cols):
        label_l = str(c).lower()
        if i == 0:
            total_cells.append("<td><b>Period totals</b></td>")
        elif re.search(r"debit", label_l):
            total_cells.append(
                f"<td class='num'><b>{escape(str(merged_summary.get('Total Debit', '')))}</b></td>"
            )
        elif re.search(r"credit", label_l):
            total_cells.append(
                f"<td class='num'><b>{escape(str(merged_summary.get('Total Credit', '')))}</b></td>"
            )
        else:
            total_cells.append("<td></td>")
    tbody += f"<tr class='total-row'>{''.join(total_cells)}</tr>"

    # Closing balance row at bottom
    close_cells = []
    for i, c in enumerate(cols):
        label_l = str(c).lower()
        if i == 0:
            close_cells.append("<td><b>Closing Balance</b></td>")
        elif re.search(r"balance", label_l):
            close_cells.append(
                f"<td class='num'><b>{escape(str(merged_summary.get('Closing', '')))}</b></td>"
            )
        else:
            close_cells.append("<td></td>")
    tbody += f"<tr class='total-row closing-row'>{''.join(close_cells)}</tr>"

    party_name = (party.get("name") or "").strip()
    party_code = (party.get("code") or "").strip()
    party_phone = (party.get("phone") or "").strip()
    party_addr = (party.get("address") or party.get("city") or "").strip()
    party_kind = (party.get("kind") or "").strip().title() or "Account"
    if not party_name:
        # Fallback: parse from title suffix after em/en dash
        for sep in (" — ", " - ", " – "):
            if sep in (title or ""):
                party_name = title.split(sep, 1)[-1].strip()
                break

    kpi_html = "".join(
        f"<div class='kpi'><b>{escape(str(k))}:</b> {escape(str(v))}</div>"
        for k, v in merged_summary.items()
    )
    party_html = f"""
    <div class="party-ledger-card">
      <div>
        <p class="party-name">{escape(party_name or '—')}</p>
        <p class="party-meta">
          <b>{escape(party_kind)} code:</b> {escape(party_code or '—')}<br/>
          {f'<b>Phone:</b> {escape(party_phone)}<br/>' if party_phone else ''}
          {f'<b>Address:</b> {escape(party_addr)}' if party_addr else ''}
        </p>
      </div>
      <div>{kpi_html}</div>
    </div>"""

    filter_txt = _clean_filters(filters or {})
    if filter_txt.strip().lower() in ("all", "—", "-", ""):
        filter_txt = ""
    mode_lbl = "Detailed (invoice lines)" if kind == "detailed" else "Summary (voucher-wise)"
    period_safe = (period or "All dates").replace("\u2014", "-").replace("—", "-")

    ref = datetime.now().strftime("%Y%m%d%H%M%S")
    meta_bits = [
        f"<span><b>Period:</b> {escape(period_safe)}</span>",
        f"<span><b>Format:</b> {escape(mode_lbl)}</span>",
        f"<span><b>Entries:</b> {len(view)}</span>",
    ]
    if filter_txt:
        meta_bits.insert(1, f"<span><b>Filters:</b> {escape(filter_txt)}</span>")

    note = (
        "Detailed ledger shows invoice lines (Qty / Rate / Amount) under each voucher. "
        if kind == "detailed"
        else "Summary ledger shows one line per voucher. Use Detailed for item breakdown. "
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{escape(display_title)} — {escape(party_name or '')}</title>
    {css}
    <script>function doPrint(){{ window.print(); }}</script></head><body>
    <div class="report-wrap">
    {company_report_header_html(ref_prefix="LDG")}
    <div class="report-title">{escape(display_title)}</div>
    <div class="meta-bar">{''.join(meta_bits)}</div>
    {party_html}
    <table class="data report-grid party-ledger"><colgroup>{colgroup}</colgroup>
    <thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
    <div class="party-ledger-card" style="margin-top:10px;grid-template-columns:1fr;">
      <div class="kpi" style="font-size:13px;">
        <b>Closing Balance:</b> {escape(str(merged_summary.get('Closing') or '—'))}
      </div>
    </div>
    <p class="ledger-note-sm">{escape(note)}Amounts in PKR. Blank Debit/Credit means zero.</p>
    {_report_signatures_html(report_key or display_title)}
    {_report_footer_html(report_key or display_title)}
    <p class="no-print"><button class="print-btn" onclick="doPrint()">Print Ledger</button></p>
    </div></body></html>"""


def report_toolbar(df, title, filename, period="", filters=None, summary=None, key_prefix="rpt", layout=None):
    """Standard export strip: Preview, Print HTML, PDF, Excel, CSV. layout: landscape | portrait_full"""
    if (title or "") == "Daily Activity Report":
        daily_activity_toolbar(df, title, filename, period, filters, key_prefix=key_prefix)
        return
    df = _safe_df(df)
    if df.empty:
        st.caption("No data to export.")
        return

    report_key = _report_profile_key(title) or title
    layout = layout or report_layout(report_key)
    export_df = prepare_report_dataframe(df, report_key)
    auto_sum = summary_keys_for_report(report_key, df)
    merged_summary = {**auto_sum, **(summary or {})}

    include_hdr = use_print_company_header_checkbox(key_prefix)
    ledger_kind = _ledger_report_kind(title)
    party = _party_from_df_attrs(df)
    with print_company_header_scope(include_hdr):
        if ledger_kind:
            html = build_party_ledger_html(
                title, df, period, filters, merged_summary,
                layout=layout, report_key=report_key, party=party,
            )
        else:
            html = build_report_html(title, df, period, filters, merged_summary, layout=layout, report_key=report_key)

        pdf_bytes = None
        try:
            pdf_bytes = build_report_pdf(title, df, period, filters, merged_summary, layout=layout, report_key=report_key)
        except Exception as ex:
            st.caption(f"PDF: {ex}")
            pdf_bytes = None

    preview_label = "Print Preview — Ledger" if ledger_kind else "Print Preview"
    with st.expander(preview_label, expanded=False):
        components.html(html, height=min(640, 180 + len(df) * 22), scrolling=True)

    # Friendly ledger PDF name: "Ledger - Customer Name.pdf"
    from erp_ui.helpers import party_download_filename
    pdf_download_name = f"{filename}.pdf"
    if ledger_kind:
        pname = (party or {}).get("name") or ""
        if pname:
            pdf_download_name = party_download_filename("Ledger", pname, ext="pdf")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.download_button("CSV", df_to_csv_bytes(df, report_key), f"{filename}.csv", "text/csv", key=f"{key_prefix}_csv")
    c2.download_button("Excel", df_to_excel_bytes(df, report_key), f"{filename}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key_prefix}_xlsx")
    c3.download_button("Print (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_html")
    if pdf_bytes:
        c4.download_button("Save PDF", pdf_bytes, pdf_download_name, "application/pdf", key=f"{key_prefix}_pdf")
    else:
        c4.download_button("Save PDF (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_pdffb")
    if c5.button("Open Print Dialog", key=f"{key_prefix}_print"):
        components.html(html.replace("</body>", "<script>window.onload=function(){window.print();}</script></body>"),
                        height=0)


def ledger_toolbar(title, opening, rows, total_in, total_out, closing, period, filename, key_prefix="led"):
    include_hdr = use_print_company_header_checkbox(key_prefix)
    with print_company_header_scope(include_hdr):
        html = build_ledger_html(title, opening, rows, total_in, total_out, closing, period)
    html_urdu = None
    if st.session_state.get(f"{key_prefix}_urdu_open"):
        with print_company_header_scope(include_hdr):
            html_urdu = build_ledger_html_urdu(title, opening, rows, total_in, total_out, closing, period)
    df = prettify_columns(pd.DataFrame(rows))
    preview_h = min(780, 220 + len(rows) * 20)
    urdu_key = f"{key_prefix}_urdu_open"
    u1, u2 = st.columns([1, 3])
    if u1.button("اردو رپورٹ / Urdu (director)", key=f"{key_prefix}_urdu_btn", help="Cash book with Urdu headings and translated particulars"):
        st.session_state[urdu_key] = not st.session_state.get(urdu_key, False)
        st.rerun()
    if st.session_state.get(urdu_key):
        u2.caption("Urdu view: headings and particulars translated; voucher refs and amounts unchanged.")
        with st.expander("Print Preview — Urdu (A4)", expanded=True):
            with st.spinner("Translating particulars to Urdu…"):
                with print_company_header_scope(include_hdr):
                    html_urdu = build_ledger_html_urdu(title, opening, rows, total_in, total_out, closing, period)
            components.html(html_urdu, height=preview_h, scrolling=True)
        du1, du2, du3 = st.columns(3)
        du1.download_button(
            "Download Urdu HTML",
            (html_urdu or "").encode("utf-8"),
            f"{filename}_urdu.html",
            "text/html",
            key=f"{key_prefix}_urdu_html",
        )
        if du2.button("Print Urdu", key=f"{key_prefix}_urdu_pr") and html_urdu:
            components.html(
                html_urdu.replace("</body>", "<script>window.onload=function(){window.print();}</script></body>"),
                height=0,
            )
        if du3.button("Back to English view", key=f"{key_prefix}_urdu_off"):
            st.session_state[urdu_key] = False
            st.rerun()
    else:
        with st.expander("Print Preview (A4 portrait)", expanded=False):
            components.html(html, height=preview_h, scrolling=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.download_button("CSV", df_to_csv_bytes(df), f"{filename}.csv", "text/csv", key=f"{key_prefix}_csv")
    c2.download_button("Excel", df_to_excel_bytes(df), f"{filename}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key_prefix}_xlsx")
    c3.download_button("Print (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_html")
    try:
        pdf = build_ledger_pdf(title, opening, rows, total_in, total_out, closing, period)
        c4.download_button("Save PDF", pdf, f"{filename}.pdf", "application/pdf", key=f"{key_prefix}_pdf")
    except Exception as ex:
        c4.download_button("PDF (HTML)", html.encode("utf-8"), f"{filename}.html", "text/html", key=f"{key_prefix}_pdf")
        st.caption(f"PDF: {ex}")
    if c5.button("Print", key=f"{key_prefix}_pr"):
        components.html(html.replace("</body>", "<script>window.onload=function(){window.print();}</script></body>"), height=0)
