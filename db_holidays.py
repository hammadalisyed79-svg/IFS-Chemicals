"""Weekly off-days and gazetted holidays for Cash/Bank book calendars."""

from datetime import date
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
    weekly = get_weekly_holidays()
    days = set()
    for d in range(1, maxd + 1):
        if date(y, m, d).weekday() in weekly:
            days.add(d)
    from database import get_connection
    with get_connection() as conn:
        for row in conn.execute(
            "SELECT holiday_date, is_annual FROM gazetted_holidays"
        ).fetchall():
            raw = row["holiday_date"]
            if int(row["is_annual"] or 0):
                try:
                    parts = raw.split("-")
                    if len(parts) >= 3:
                        gd, gm = int(parts[2]), int(parts[1])
                        if gm == m:
                            if 1 <= gd <= maxd:
                                days.add(gd)
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    parts = raw.split("-")
                    if len(parts) >= 3:
                        gy, gm, gd = int(parts[0]), int(parts[1]), int(parts[2])
                        if gy == y and gm == m and 1 <= gd <= maxd:
                            days.add(gd)
                except (ValueError, TypeError):
                    pass
    return days
