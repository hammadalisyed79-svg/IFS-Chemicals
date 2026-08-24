"""Close all cash book days through a cutoff date; report any still unclosed."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import database as db
from db_cash_day import close_cash_day, is_cash_day_closed, list_closed_cash_days

CUTOFF = "2026-08-19"
USER_ID = 1  # system/admin batch close
NOTES = "Batch close through 2026-08-19"


def cash_activity_dates(conn, cutoff: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT dt FROM (
            SELECT receipt_date AS dt FROM cash_receipts WHERE receipt_date <= ?
            UNION
            SELECT payment_date AS dt FROM cash_payments WHERE payment_date <= ?
        ) ORDER BY dt
        """,
        (cutoff, cutoff),
    ).fetchall()
    return [str(r[0])[:10] for r in rows if r[0]]


def day_summary(conn, d: str) -> dict:
    rec = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cash_receipts WHERE receipt_date=?",
        (d,),
    ).fetchone()
    pay = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM cash_payments WHERE payment_date=?",
        (d,),
    ).fetchone()
    return {
        "date": d,
        "receipts": int(rec[0] or 0),
        "receipt_amount": round(float(rec[1] or 0), 2),
        "payments": int(pay[0] or 0),
        "payment_amount": round(float(pay[1] or 0), 2),
        "entries": int(rec[0] or 0) + int(pay[0] or 0),
    }


def main():
    report = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "cutoff": CUTOFF,
        "already_closed": [],
        "newly_closed": [],
        "failed_to_close": [],
        "unclosed_with_activity": [],
        "summary": {},
    }

    with db.get_connection() as conn:
        activity_dates = cash_activity_dates(conn, CUTOFF)
        report["activity_dates_count"] = len(activity_dates)
        report["first_activity"] = activity_dates[0] if activity_dates else None
        report["last_activity"] = activity_dates[-1] if activity_dates else None

        for d in activity_dates:
            summary = day_summary(conn, d)
            if is_cash_day_closed(d):
                close_row = db.get_cash_day_close(d) or {}
                report["already_closed"].append({**summary, "closed_at": close_row.get("closed_at")})
                continue
            try:
                close_cash_day(d, USER_ID, notes=NOTES)
                report["newly_closed"].append(summary)
            except Exception as e:
                report["failed_to_close"].append({**summary, "error": str(e)})

        # Final unclosed report: any activity date <= cutoff still open
        for d in activity_dates:
            if not is_cash_day_closed(d):
                report["unclosed_with_activity"].append(day_summary(conn, d))

        closed_through = list_closed_cash_days(from_date=None, to_date=CUTOFF, limit=5000)
        report["closed_through_cutoff"] = len(closed_through)

    report["summary"] = {
        "activity_days_through_cutoff": len(activity_dates),
        "already_closed_before": len(report["already_closed"]),
        "newly_closed": len(report["newly_closed"]),
        "failed_to_close": len(report["failed_to_close"]),
        "still_unclosed": len(report["unclosed_with_activity"]),
    }

    out = f"reports/cash_book_close_through_{CUTOFF.replace('-', '')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print("CUTOFF", CUTOFF)
    print("SUMMARY", json.dumps(report["summary"], indent=2))
    if report["newly_closed"]:
        print(f"\nNEWLY CLOSED ({len(report['newly_closed'])})")
        for r in report["newly_closed"]:
            print(
                f"  {r['date']} | entries={r['entries']} | "
                f"rec {r['receipt_amount']:,.2f} | pay {r['payment_amount']:,.2f}"
            )
    if report["already_closed"]:
        print(f"\nALREADY CLOSED ({len(report['already_closed'])}) — last 10:")
        for r in report["already_closed"][-10:]:
            print(f"  {r['date']} | entries={r['entries']}")
    if report["unclosed_with_activity"]:
        print(f"\n*** UNCLOSED CASH BOOK ({len(report['unclosed_with_activity'])}) ***")
        for r in report["unclosed_with_activity"]:
            print(
                f"  {r['date']} | entries={r['entries']} | "
                f"rec {r['receipt_amount']:,.2f} ({r['receipts']}) | "
                f"pay {r['payment_amount']:,.2f} ({r['payments']})"
            )
    if report["failed_to_close"]:
        print(f"\nFAILED ({len(report['failed_to_close'])})")
        for r in report["failed_to_close"]:
            print(f"  {r['date']}: {r['error']}")
    print("WROTE", out)


if __name__ == "__main__":
    main()
