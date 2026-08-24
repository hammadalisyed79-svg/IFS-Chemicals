"""Group-wise report views — master groups + COA type summaries."""

from __future__ import annotations

TRIAL_VIEW_DETAIL = "detail"
TRIAL_VIEW_COA_TYPE = "coa_type"
TRIAL_VIEW_MASTER_GROUP = "master_group"

TRIAL_VIEW_LABELS = {
    TRIAL_VIEW_DETAIL: "Detail (each account)",
    TRIAL_VIEW_COA_TYPE: "Summary by account type (Asset / Liability / …)",
    TRIAL_VIEW_MASTER_GROUP: "Summary by chart account group",
}


def summarize_trial_balance(rows, view_mode):
    """Roll up trial balance lines for group-wise display."""
    if not rows or view_mode == TRIAL_VIEW_DETAIL:
        return rows or []

    if view_mode == TRIAL_VIEW_COA_TYPE:
        key = "group_type"
        out = {}
        for r in rows:
            k = r.get(key) or "other"
            if k not in out:
                out[k] = {
                    "code": k.upper()[:1] + k[1:],
                    "name": f"Total — {k.replace('_', ' ').title()}",
                    "group_type": k,
                    "period_debit": 0.0,
                    "period_credit": 0.0,
                    "balance": 0.0,
                }
            out[k]["period_debit"] += float(r.get("period_debit") or 0)
            out[k]["period_credit"] += float(r.get("period_credit") or 0)
            out[k]["balance"] += float(r.get("balance") or 0)
        order = ("asset", "liability", "equity", "income", "expense", "other")
        return [out[k] for k in order if k in out] + [out[k] for k in out if k not in order]

    if view_mode == TRIAL_VIEW_MASTER_GROUP:
        out = {}
        for r in rows:
            gid = r.get("master_group_id")
            if gid:
                k = f"g{gid}"
                code = r.get("group_code") or ""
                name = r.get("group_name") or ""
            else:
                k = "_none"
                code = "—"
                name = "Unassigned accounts"
            if k not in out:
                out[k] = {
                    "code": code,
                    "name": name,
                    "group_type": r.get("group_type"),
                    "period_debit": 0.0,
                    "period_credit": 0.0,
                    "balance": 0.0,
                }
            out[k]["period_debit"] += float(r.get("period_debit") or 0)
            out[k]["period_credit"] += float(r.get("period_credit") or 0)
            out[k]["balance"] += float(r.get("balance") or 0)
        rows_out = list(out.values())
        rows_out.sort(key=lambda x: (x["code"] == "—", x["code"]))
        return rows_out

    return rows


def summarize_balance_sheet_rows(rows, view_mode):
    """Group balance sheet lines by COA type or chart account master group."""
    if not rows or view_mode == TRIAL_VIEW_DETAIL:
        return rows or []
    if view_mode == TRIAL_VIEW_COA_TYPE:
        out = {}
        for r in rows:
            k = r.get("group_type") or "other"
            if k not in out:
                out[k] = {
                    "group_type": k,
                    "code": "",
                    "name": f"Total — {k.replace('_', ' ').title()}",
                    "balance": 0.0,
                }
            out[k]["balance"] += float(r.get("balance") or 0)
        order = ("asset", "liability", "equity")
        return [out[k] for k in order if k in out]
    if view_mode == TRIAL_VIEW_MASTER_GROUP:
        out = {}
        for r in rows:
            gid = r.get("master_group_id")
            k = f"g{gid}" if gid else "_none"
            if k not in out:
                out[k] = {
                    "group_type": r.get("group_type"),
                    "code": r.get("group_code") or "—",
                    "name": r.get("group_name") or "Unassigned accounts",
                    "balance": 0.0,
                }
            out[k]["balance"] += float(r.get("balance") or 0)
        return sorted(out.values(), key=lambda x: (x["code"] == "—", x["code"]))
    return rows


PARTY_VIEW_DETAIL = "detail"
PARTY_VIEW_MASTER_GROUP = "master_group"

PARTY_VIEW_LABELS = {
    PARTY_VIEW_DETAIL: "Detail (each party / product)",
    PARTY_VIEW_MASTER_GROUP: "Summary by group",
}


def summarize_party_outstanding(rows, view_mode):
    if not rows or view_mode != PARTY_VIEW_MASTER_GROUP:
        return rows or []
    out = {}
    for r in rows:
        gid = r.get("group_id")
        k = f"g{gid}" if gid else "_none"
        if k not in out:
            out[k] = {
                "code": r.get("group_code") or "—",
                "name": r.get("group_name") or "Unassigned",
                "phone": "",
                "outstanding": 0.0,
            }
        out[k]["outstanding"] += float(r.get("outstanding") or 0)
    return sorted(out.values(), key=lambda x: (x["code"] == "—", x["code"]))


def summarize_product_sales(rows, view_mode):
    if not rows or view_mode != PARTY_VIEW_MASTER_GROUP:
        return rows or []
    out = {}
    for r in rows:
        gid = r.get("group_id")
        k = f"g{gid}" if gid else "_none"
        if k not in out:
            out[k] = {
                "code": r.get("group_code") or "—",
                "name": r.get("group_name") or "Unassigned",
                "qty": 0.0,
                "amount": 0.0,
            }
        out[k]["qty"] += float(r.get("qty") or 0)
        out[k]["amount"] += float(r.get("amount") or 0)
    return sorted(out.values(), key=lambda x: (x["code"] == "—", x["code"]))
