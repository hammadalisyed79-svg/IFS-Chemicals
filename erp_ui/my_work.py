"""My Work task queue — read-only aggregates (no schema changes)."""

from __future__ import annotations

from application import data_gateway as db
from erp_ui.helpers import fmt_money
from erp_ui.nav import can_view_screen


def load_my_work_tasks(user: dict, nav: dict) -> list[dict]:
    """Return actionable tasks for the home dashboard."""
    tasks: list[dict] = []
    if not user:
        return tasks

    try:
        stats = db.get_dashboard_stats()
        p = stats.get("pending_breakdown") or {}
    except Exception:
        p = {}

    def _add(label: str, detail: str, group: str, screen: str, *, tone: str = "accent"):
        if group not in nav or screen not in nav.get(group, []):
            return
        if not can_view_screen(user, screen):
            return
        tasks.append({
            "label": label,
            "detail": detail,
            "group": group,
            "screen": screen,
            "tone": tone,
        })

    n = int(p.get("sales_approval") or 0)
    if n:
        _add(
            f"{n} sale(s) pending approval",
            "Review and approve cash / credit invoices",
            "Sales", "Sale Approval",
        )
    n = int(p.get("purchase_approval") or 0)
    if n:
        _add(
            f"{n} purchase(s) pending approval",
            "Review supplier bills before posting",
            "Purchases", "Purchase Approval",
        )
    n = int(p.get("gate_pass_open") or 0)
    if n:
        _add(
            f"{n} open gate pass(es)",
            "Complete outbound / inbound gate control",
            "Gate Pass", "Gate Pass Entry",
        )
    n = int(p.get("journal_draft") or 0)
    if n:
        _add(
            f"{n} journal voucher draft(s)",
            "Post or clear draft JV entries",
            "Finance", "Journal Voucher",
        )

    try:
        adv = db.cash_advance_outstanding_summary()
        adv_n = float(adv.get("total_outstanding") or 0)
        if adv_n > 0.01 and "Finance" in nav and "Cash Advance" in nav.get("Finance", []):
            if can_view_screen(user, "Cash Advance"):
                open_res = db.search_cash_advances(open_only=True, page_size=200, export_all=False)
                cnt = len(open_res.get("items") or [])
                tasks.append({
                    "label": f"{cnt} open cash advance(s)",
                    "detail": f"{fmt_money(adv_n)} outstanding with staff",
                    "group": "Finance",
                    "screen": "Cash Advance",
                    "tone": "warning",
                })
    except Exception:
        pass

    try:
        from datetime import date
        today = str(date.today())
        if db.is_cash_day_closed(today):
            pass
        elif "Finance" in nav and "Cash Book" in nav.get("Finance", []):
            if can_view_screen(user, "Cash Book"):
                tasks.append({
                    "label": "Cash day is open",
                    "detail": f"Close cash book when till is reconciled ({today})",
                    "group": "Finance",
                    "screen": "Cash Book",
                    "tone": "neutral",
                })
    except Exception:
        pass

    return tasks[:8]
