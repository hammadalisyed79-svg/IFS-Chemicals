"""Stable invoice line row ids (no Streamlit). Delete one row without shifting others."""

import uuid

MIN_LINE_ROWS = 5


def new_line_row_uid():
    return uuid.uuid4().hex[:12]


def ensure_line_row_uid(line):
    """Stable id so delete/reorder does not steal another row's widget state."""
    row = dict(line or {})
    uid = str(row.get("_row_uid") or "").strip()
    if not uid:
        row["_row_uid"] = new_line_row_uid()
    return row


def blank_line_item():
    return {
        "item_id": None, "product_id": None,
        "quantity": 0.0, "rate": 0.0, "amount": 0.0, "net_weight": 0.0,
        "discount_pct": 0.0,
        "_row_uid": new_line_row_uid(),
    }


def drop_lines_by_uid(lines, drop_uids):
    """Keep every line except those whose _row_uid is in drop_uids (one click, one row)."""
    drop = {str(u) for u in (drop_uids or []) if u}
    kept = []
    for ln in lines or []:
        if ln is None:
            continue
        uid = str(ln.get("_row_uid") or "")
        if uid and uid in drop:
            continue
        kept.append(ln)
    return kept


def pad_line_rows(lines, min_rows=MIN_LINE_ROWS):
    """Ensure at least min_rows for tabular entry (empty rows for new lines)."""
    rows = [ensure_line_row_uid(ln) for ln in (lines or []) if ln is not None]
    seen = set()
    for row in rows:
        uid = str(row.get("_row_uid") or "")
        if not uid or uid in seen:
            row["_row_uid"] = new_line_row_uid()
            uid = row["_row_uid"]
        seen.add(uid)
    if not rows:
        rows = [blank_line_item()]
    while len(rows) < min_rows:
        rows.append(blank_line_item())
    return rows
