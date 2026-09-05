"""Daily cash book close — blocks cash receipts/payments on closed dates."""

from __future__ import annotations


def apply_cash_day_schema(conn, db_module=None):
    from db_v3 import _schema_ver

    conn.execute(
        """CREATE TABLE IF NOT EXISTS cash_day_closes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            close_date  TEXT NOT NULL UNIQUE,
            notes       TEXT,
            closed_by   INTEGER REFERENCES users(id),
            closed_at   TEXT NOT NULL,
            reopened_by INTEGER REFERENCES users(id),
            reopened_at TEXT
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cash_day_closes_date ON cash_day_closes(close_date)"
    )
    if _schema_ver(conn) < 13:
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('schema_version','13') "
            "ON CONFLICT(key) DO UPDATE SET value='13'"
        )


def _norm_date(d):
    return str(d)[:10] if d else None


def is_cash_day_closed(entry_date):
    from database import get_connection

    d = _norm_date(entry_date)
    if not d:
        return False
    with get_connection() as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM cash_day_closes WHERE close_date=? AND reopened_at IS NULL",
                (d,),
            ).fetchone()
        )


def get_cash_day_close(entry_date):
    from database import get_connection, row_to_dict

    d = _norm_date(entry_date)
    if not d:
        return None
    with get_connection() as conn:
        row = conn.execute(
            """SELECT c.*, u.full_name AS closed_by_name
               FROM cash_day_closes c
               LEFT JOIN users u ON c.closed_by=u.id
               WHERE c.close_date=? AND c.reopened_at IS NULL""",
            (d,),
        ).fetchone()
        return row_to_dict(row) if row else None


def assert_cash_day_open(entry_date, action="post or change"):
    """Raise if cash book day is closed for this date."""
    d = _norm_date(entry_date)
    if not d or not is_cash_day_closed(d):
        return
    row = get_cash_day_close(d) or {}
    by = row.get("closed_by_name") or "system"
    raise ValueError(
        f"Cash day **{d}** is closed (by {by}). "
        f"Cannot {action}. "
        f"**Open the day** in Finance > Cash Book to post this transaction."
    )


def assert_cash_day_open_for_invoice(entry_date, *, kind="cash invoice"):
    """Block cash invoice submit/approve when the cash day is closed."""
    d = _norm_date(entry_date)
    if not d or not is_cash_day_closed(d):
        return
    raise ValueError(
        f"Cash day **{d}** is closed — this {kind} was **not posted**. "
        f"**Open the day** in Finance > Cash Book to post this transaction."
    )


def pending_cash_invoices_for_date(entry_date, *, limit=50):
    """Cash sale/purchase invoices awaiting approval on this invoice date.

    Matches invoices that would post to Cash Book on approve
    (cash paid mode, or SALE IN CASH / counter cash customer).
    """
    from database import get_connection, rows_to_list

    d = _norm_date(entry_date)
    if not d:
        return []
    lim = max(1, min(int(limit or 50), 200))
    with get_connection() as conn:
        sales = rows_to_list(conn.execute(
            """
            SELECT s.id, s.document_no, s.invoice_date, s.total, s.paid_amount,
                   s.payment_mode, 'sale' AS kind,
                   c.code AS party_code, c.name AS party_name
            FROM sales_invoices s
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.invoice_date = ?
              AND s.status = 'pending_approval'
              AND (
                    (LOWER(COALESCE(s.payment_mode, '')) = 'cash'
                     AND COALESCE(s.paid_amount, 0) > 0.009)
                 OR COALESCE(c.code, '') = '100013'
                 OR UPPER(TRIM(COALESCE(c.name, ''))) IN
                    ('SALE IN CASH', 'CASH SALE', 'CASH SALES')
              )
            ORDER BY s.document_no
            LIMIT ?
            """,
            (d, lim),
        ).fetchall())
        purchases = rows_to_list(conn.execute(
            """
            SELECT p.id, p.document_no, p.invoice_date, p.total, p.paid_amount,
                   p.payment_mode, 'purchase' AS kind,
                   s.code AS party_code, s.name AS party_name
            FROM purchase_invoices p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.invoice_date = ?
              AND p.status = 'pending_approval'
              AND LOWER(COALESCE(p.payment_mode, '')) = 'cash'
              AND COALESCE(p.paid_amount, 0) > 0.009
            ORDER BY p.document_no
            LIMIT ?
            """,
            (d, lim),
        ).fetchall())
    return sales + purchases


def assert_no_pending_cash_invoices(entry_date):
    """Raise if any cash invoice is still pending approval for this date."""
    pending = pending_cash_invoices_for_date(entry_date, limit=20)
    if not pending:
        return
    d = _norm_date(entry_date)
    refs = ", ".join(
        f"{r.get('document_no') or r.get('id')} ({r.get('kind')})"
        for r in pending[:10]
    )
    extra = ""
    if len(pending) > 10:
        extra = f" and {len(pending) - 10} more"
    raise ValueError(
        f"Cannot close cash day **{d}** — {len(pending)} cash invoice(s) still "
        f"pending approval: {refs}{extra}. "
        f"Approve, reject, or return them for edit first."
    )


def close_cash_day(close_date, user_id=None, notes=None):
    from database import get_connection, now

    d = _norm_date(close_date)
    if not d:
        raise ValueError("Close date is required.")
    if is_cash_day_closed(d):
        raise ValueError(f"Cash book for {d} is already closed.")
    assert_no_pending_cash_invoices(d)
    ts = now()
    note_val = (notes or "").strip() or None
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, reopened_at FROM cash_day_closes WHERE close_date=?",
            (d,),
        ).fetchone()
        if existing:
            if not existing["reopened_at"]:
                raise ValueError(f"Cash book for {d} is already closed.")
            conn.execute(
                """UPDATE cash_day_closes SET notes=?, closed_by=?, closed_at=?,
                   reopened_by=NULL, reopened_at=NULL WHERE close_date=?""",
                (note_val, user_id, ts, d),
            )
            row_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO cash_day_closes (close_date, notes, closed_by, closed_at)
                   VALUES (?, ?, ?, ?)""",
                (d, note_val, user_id, ts),
            )
            row_id = cur.lastrowid
    try:
        from db_audit import log_event
        log_event(
            "cash_day_closes", row_id, "close", user_id=user_id, module="Finance",
            summary=f"Cash day closed {d}",
        )
    except Exception:
        pass
    return d


def reopen_cash_day(close_date, user_id=None, admin_password=None):
    from database import get_connection, now, verify_user_password

    d = _norm_date(close_date)
    if not d:
        raise ValueError("Date is required.")
    if not user_id:
        raise ValueError("You must be logged in to reopen a cash day.")
    with get_connection() as conn:
        u = conn.execute(
            "SELECT role, username FROM users WHERE id=? AND is_active=1", (user_id,),
        ).fetchone()
        if not u or u["role"] != "admin":
            raise ValueError("Only administrators can reopen a closed cash day.")
    if not verify_user_password(user_id, admin_password or ""):
        raise ValueError("Incorrect administrator password.")
    row = get_cash_day_close(d)
    if not row:
        raise ValueError(f"Cash book for {d} is not closed.")
    with get_connection() as conn:
        conn.execute(
            """UPDATE cash_day_closes SET reopened_by=?, reopened_at=?
               WHERE close_date=? AND reopened_at IS NULL""",
            (user_id, now(), d),
        )
    try:
        from db_audit import log_event
        log_event(
            "cash_day_closes", row.get("id"), "reopen", user_id=user_id, module="Finance",
            summary=f"Cash day reopened {d}",
        )
    except Exception:
        pass
    return d


def list_closed_cash_days(from_date=None, to_date=None, limit=90):
    from database import get_connection, rows_to_list

    q = """SELECT c.close_date, c.closed_at, c.notes, u.full_name AS closed_by_name
           FROM cash_day_closes c
           LEFT JOIN users u ON c.closed_by=u.id
           WHERE c.reopened_at IS NULL"""
    p = []
    if from_date:
        q += " AND c.close_date>=?"
        p.append(_norm_date(from_date))
    if to_date:
        q += " AND c.close_date<=?"
        p.append(_norm_date(to_date))
    q += " ORDER BY c.close_date DESC LIMIT ?"
    p.append(int(limit))
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())
