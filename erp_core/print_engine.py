"""V13.14 — unified print engine (logo, watermarks, print count)."""

from __future__ import annotations

from datetime import datetime
from html import escape


def record_print(
    doc_type: str,
    doc_table: str,
    record_id: int,
    document_no: str,
    user_id: int | None,
    *,
    is_draft: bool = False,
    is_reprint: bool = False,
) -> int:
    """Log print event and return cumulative print count."""
    from database import get_connection

    count = 1
    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='erp_print_log'"
        ).fetchone():
            return count
        prev = conn.execute(
            """SELECT COALESCE(SUM(print_count), 0) FROM erp_print_log
               WHERE doc_table=? AND record_id=?""",
            (doc_table, record_id),
        ).fetchone()
        count = int(prev[0] or 0) + 1
        conn.execute(
            """INSERT INTO erp_print_log
               (doc_type, doc_table, record_id, document_no, print_count,
                is_reprint, is_draft, printed_by, printed_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                doc_type, doc_table, record_id, document_no, 1,
                1 if is_reprint or count > 1 else 0,
                1 if is_draft else 0,
                user_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        if conn.execute(
            f"SELECT 1 FROM pragma_table_info('{doc_table}') WHERE name='printed_count'"
        ).fetchone():
            conn.execute(
                f"""UPDATE {doc_table}
                    SET printed_count=COALESCE(printed_count,0)+1,
                        last_printed_at=?
                    WHERE id=?""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), record_id),
            )
    return count


def print_watermark_html(*, is_draft: bool = False, is_reprint: bool = False, print_count: int = 1) -> str:
    if is_draft:
        return '<div class="print-watermark draft">DRAFT</div>'
    if is_reprint or print_count > 1:
        return f'<div class="print-watermark reprint">REPRINT #{print_count}</div>'
    return ""


def print_header_extras_html(company: dict, *, qr_data: str = "") -> str:
    logo = company.get("logo_url") or company.get("logo_path") or ""
    parts = []
    if logo:
        parts.append(f'<img class="print-logo" src="{escape(logo)}" alt="logo"/>')
    if qr_data:
        parts.append(f'<div class="print-qr" title="{escape(qr_data)}">QR</div>')
    return "".join(parts)


def signature_block_html(
    *,
    prepared_by: str = "",
    approved_by: str = "",
    printed_by: str = "",
    printed_at: str = "",
) -> str:
    rows = []
    if prepared_by:
        rows.append(f"<tr><td>Prepared By</td><td>{escape(prepared_by)}</td></tr>")
    if approved_by:
        rows.append(f"<tr><td>Approved By</td><td>{escape(approved_by)}</td></tr>")
    if printed_by:
        rows.append(f"<tr><td>Printed By</td><td>{escape(printed_by)}</td></tr>")
    if printed_at:
        rows.append(f"<tr><td>Printed At</td><td>{escape(printed_at)}</td></tr>")
    if not rows:
        return ""
    return '<table class="print-sigs">' + "".join(rows) + "</table>"
