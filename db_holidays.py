"""Weekly off-days and gazetted holidays for Cash/Bank book calendars."""

from datetime import date, timedelta
from calendar import monthrange


WEEKDAY_LABELS = [
    ("Mon", 0), ("Tue", 1), ("Wed", 2), ("Thu", 3),
    ("Fri", 4), ("Sat", 5), ("Sun", 6),
]


def apply_holidays(conn, db_module):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS weekly_holidays (
            weekday INTEGER PRIMARY KEY,
            created_at TEXT,
            created_by INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gazetted_holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            holiday_date TEXT NOT NULL,
            name TEXT NOT NULL,
            is_annual INTEGER DEFAULT 0,
            created_at TEXT,
            created_by INTEGER
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gazetted_holidays_date ON gazetted_holidays(holiday_date)"
    )
    if conn.execute("SELECT COUNT(*) FROM weekly_holidays").fetchone()[0] == 0:
        ts = db_module.now()
        conn.execute(
            "INSERT INTO weekly_holidays (weekday, created_at) VALUES (6, ?)",
            (ts,),
        )
    conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES('schema_version','11') "
        "ON CONFLICT(key) DO UPDATE SET value='11'"
    )


def get_weekly_holidays():
    from database import get_connection
    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='weekly_holidays'"
        ).fetchone():
            apply_holidays(conn, __import__("database"))
        rows = conn.execute("SELECT weekday FROM weekly_holidays ORDER BY weekday").fetchall()
    return {int(r[0]) for r in rows}


def save_weekly_holidays(weekdays, user_id=None):
    from database import get_connection, now
    days = {int(d) for d in weekdays if 0 <= int(d) <= 6}
    ts = now()
    with get_connection() as conn:
        conn.execute("DELETE FROM weekly_holidays")
        for wd in sorted(days):
            conn.execute(
                "INSERT INTO weekly_holidays (weekday, created_at, created_by) VALUES (?, ?, ?)",
                (wd, ts, user_id),
            )


def list_gazetted_holidays():
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(
            conn.execute(
                """SELECT id, holiday_date, name, is_annual
                   FROM gazetted_holidays ORDER BY holiday_date, id"""
            ).fetchall()
        )


def add_gazetted_holiday(holiday_date, name, is_annual=False, user_id=None):
    from database import get_connection, now
    if isinstance(holiday_date, date):
        holiday_date = holiday_date.isoformat()
    name = (name or "").strip() or "Holiday"
    with get_connection() as conn:
        dup = conn.execute(
            "SELECT id FROM gazetted_holidays WHERE holiday_date=? AND is_annual=?",
            (holiday_date, 1 if is_annual else 0),
        ).fetchone()
        if dup:
            raise ValueError("This holiday date is already on the calendar.")
        conn.execute(
            """INSERT INTO gazetted_holidays (holiday_date, name, is_annual, created_at, created_by)
               VALUES (?, ?, ?, ?, ?)""",
            (holiday_date, name, 1 if is_annual else 0, now(), user_id),
        )


def delete_gazetted_holiday(holiday_id):
    from database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM gazetted_holidays WHERE id=?", (holiday_id,))


def cash_month_holiday_days(year, month):
    """Day-of-month numbers (1..N) that are weekly off or gazetted holiday."""
    y, m = int(year), int(month)
    maxd = monthrange(y, m)[1]
    info = holidays_in_range(date(y, m, 1), date(y, m, maxd))
    return {int(ds.split("-")[2]) for ds in info}


def _parse_iso_date(raw) -> date | None:
    if isinstance(raw, date):
        return raw
    t = str(raw or "").strip()[:10]
    if len(t) < 10:
        return None
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


def _gazetted_match(d: date, holiday_date: str, is_annual: bool) -> bool:
    gd = _parse_iso_date(holiday_date)
    if not gd:
        return False
    if is_annual:
        return gd.month == d.month and gd.day == d.day
    return gd == d


def holiday_info_for_date(d) -> dict | None:
    """Return holiday metadata for a date, or None if it is a working day.

    Keys: kind ('weekly'|'gazetted'), status (attendance status code),
    label (UI label), name (calendar name / weekday).
    Gazetted takes precedence over weekly off when both apply.
    """
    day = _parse_iso_date(d)
    if not day:
        return None
    # Prefer gazetted when both fall on the same day
    for row in list_gazetted_holidays():
        if _gazetted_match(day, row.get("holiday_date"), bool(row.get("is_annual"))):
            name = (row.get("name") or "Gazetted Holiday").strip()
            return {
                "kind": "gazetted",
                "status": "public_holiday",
                "label": "Gazetted Holiday",
                "name": name,
            }
    weekly = get_weekly_holidays()
    if day.weekday() in weekly:
        wd_label = next((lbl for lbl, wd in WEEKDAY_LABELS if wd == day.weekday()), day.strftime("%A"))
        return {
            "kind": "weekly",
            "status": "weekly_holiday",
            "label": "Weekly Holiday",
            "name": f"Weekly off ({wd_label})",
        }
    return None


def holidays_in_range(from_date, to_date) -> dict:
    """Map ISO date string → holiday_info_for_date result for each holiday in range."""
    fd = _parse_iso_date(from_date)
    td = _parse_iso_date(to_date)
    if not fd or not td or fd > td:
        return {}
    weekly = get_weekly_holidays()
    gazetted = list_gazetted_holidays()
    out = {}
    cur = fd
    while cur <= td:
        hit = None
        for row in gazetted:
            if _gazetted_match(cur, row.get("holiday_date"), bool(row.get("is_annual"))):
                name = (row.get("name") or "Gazetted Holiday").strip()
                hit = {
                    "kind": "gazetted",
                    "status": "public_holiday",
                    "label": "Gazetted Holiday",
                    "name": name,
                }
                break
        if hit is None and cur.weekday() in weekly:
            wd_label = next((lbl for lbl, wd in WEEKDAY_LABELS if wd == cur.weekday()), cur.strftime("%A"))
            hit = {
                "kind": "weekly",
                "status": "weekly_holiday",
                "label": "Weekly Holiday",
                "name": f"Weekly off ({wd_label})",
            }
        if hit:
            out[cur.isoformat()] = hit
        cur += timedelta(days=1)
    return out
