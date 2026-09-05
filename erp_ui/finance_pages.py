"""Finance Manager style Cash Book & Bank Book — like IFS Industrial ERP V13."""

from datetime import date, timedelta
from calendar import monthrange
import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui.helpers import uid, std_page_header, fmt_money, money_input, smart_select, user_role, fmt_datetime, fmt_datetime_from_record, form_compact, form_line
from erp_ui.report_print import ledger_toolbar, report_toolbar
from erp_ui.document_print import (
    document_print_toolbar,
    document_print_batch_toolbar,
    finance_vouchers_batch_html,
)
from erp_ui.finance_attachments import slip_attachment_workspace, preset_from_voucher
from erp_ui import form_flow as ff


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _cash_account_id(conn):
    """Prefer live FMYE cash code 000000; fall back to legacy 1000 / name match."""
    for code in ("000000", "1000"):
        row = conn.execute(
            "SELECT id FROM chart_of_accounts WHERE code=? AND is_active=1", (code,)
        ).fetchone()
        if row:
            return row[0]
    row = conn.execute(
        """SELECT id FROM chart_of_accounts
           WHERE is_active=1 AND UPPER(name) LIKE '%CASH%HAND%'
           ORDER BY code LIMIT 1"""
    ).fetchone()
    return row[0] if row else None


def _cash_opening(before_date):
    with db.get_connection() as conn:
        aid = _cash_account_id(conn)
        if aid:
            coa = conn.execute(
                "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE id=?",
                (aid,),
            ).fetchone()
        else:
            coa = conn.execute(
                "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE code='000000'"
            ).fetchone()
        base = float(coa[0] if coa else 0)
        rec = db.cash_book_receipts_sum(conn, before_date=before_date)
        pay = db.cash_book_payments_sum(conn, before_date=before_date)
        return base + float(rec) - float(pay)


def _bank_opening(before_date, account_id=None):
    with db.get_connection() as conn:
        if account_id:
            coa = conn.execute(
                "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE id=?", (account_id,)
            ).fetchone()
        else:
            # FMYE bank accounts (e.g. 100068 Habib, 100314 Alfalah) — not legacy 11xx only
            coa = conn.execute(
                """SELECT COALESCE(SUM(opening_balance),0) FROM chart_of_accounts
                   WHERE is_active=1 AND (
                     code IN ('100068','100314','100740','100959')
                     OR (UPPER(name) LIKE '%BANK%' AND UPPER(name) NOT LIKE '%CHARGE%'
                         AND UPPER(name) NOT LIKE '%FED%')
                   )"""
            ).fetchone()
        base = float(coa[0] if coa else 0)
        q_rec, q_pay = (
            "SELECT COALESCE(SUM(amount),0) FROM bank_receipts WHERE receipt_date<?",
            "SELECT COALESCE(SUM(amount),0) FROM bank_payments WHERE payment_date<?",
        )
        p = [before_date]
        if account_id:
            q_rec += " AND account_id=?"; q_pay += " AND account_id=?"
            p.append(account_id)
        rec = conn.execute(q_rec, p).fetchone()[0]
        pay = conn.execute(q_pay, p).fetchone()[0]
        return base + float(rec) - float(pay)


def _day_rows(raw_rows, opening):
    receipts, payments, bal = [], [], opening
    total_in = total_out = 0.0
    for r in raw_rows:
        inc = float(r["amount"]) if r["entry_type"] == "credit" else 0
        exp = float(r["amount"]) if r["entry_type"] == "debit" else 0
        bal += inc - exp
        total_in += inc
        total_out += exp
        row = {
            "id": r["id"], "entry_type": r["entry_type"],
            "voucher": r.get("document_no") or "",
            "particulars": r["description"],
            "ledger": (r.get("account_title") or "").strip(),
            "ref": r.get("reference_no") or "",
            "amount": float(r["amount"]),
            "balance": bal,
            "entry_source": r.get("entry_source"),
            "created_at": r.get("created_at"),
            "entry_date": r.get("entry_date"),
            "datetime": fmt_datetime(r.get("entry_date"), r.get("created_at")),
            "provisional": False,
        }
        if r["entry_type"] == "credit":
            receipts.append(row)
        else:
            payments.append(row)
    return receipts, payments, total_in, total_out, bal


def _provisional_cash_sale_status_label(status: str) -> str:
    s = (status or "").strip().lower()
    if s == "draft":
        return "drafted"
    if s == "pending_approval":
        return "pending"
    return s or "pending"


def _append_provisional_cash_sales(receipts: list[dict], closing_posted: float, day_iso: str) -> tuple[int, float]:
    """Add draft/pending cash sale invoices to Income grid (display only).

    Amounts are shown with [drafted]/[pending] on Particulars but do not change
    Opening / Receipts / Payments / Closing metrics (posted cash only).

    Returns (count added, total pending amount).
    """
    try:
        invs = db.get_provisional_cash_sale_invoices(day_iso, day_iso)
    except Exception:
        return 0, 0.0
    added = 0
    pending_total = 0.0
    for inv in invs or []:
        status_lbl = _provisional_cash_sale_status_label(inv.get("status"))
        cust = (inv.get("customer_name") or "").strip()
        particular = f"Sale {inv.get('document_no') or ''}"
        if cust:
            particular = f"{particular} — {cust}"
        particular = f"{particular} [{status_lbl}]"
        receipts.append({
            "id": f"si-{inv.get('id')}",
            "entry_type": "credit",
            "voucher": inv.get("document_no") or "",
            "particulars": particular,
            "ledger": cust or "Cash Sale",
            "ref": inv.get("document_no") or "",
            "amount": float(inv.get("amount") or 0),
            "balance": float(closing_posted),  # unchanged — not posted to cash yet
            "entry_source": "sales_invoice_provisional",
            "created_at": inv.get("created_at"),
            "entry_date": inv.get("entry_date") or day_iso,
            "datetime": fmt_datetime(inv.get("entry_date") or day_iso, inv.get("created_at")),
            "provisional": True,
            "status": status_lbl,
        })
        added += 1
        pending_total += float(inv.get("amount") or 0)
    return added, pending_total


def _day_book_dataframe(rows: list[dict], *, show_balance: bool = True) -> pd.DataFrame:
    """Build a display frame for Cash/Bank Daily Book grids."""
    records = []
    for r in rows or []:
        dt = str(r.get("datetime") or "")
        # Day is already chosen in the date bar — show time only when present
        time_s = ""
        if len(dt) >= 16 and dt[10] == " ":
            time_s = dt[11:16]  # HH:MM
        records.append({
            "Time": time_s or "—",
            "Voucher": r.get("voucher") or "",
            "Particulars": r.get("particulars") or "",
            "Ledger": (r.get("ledger") or "").strip() or "—",
            "Ref": r.get("ref") or "",
            "Amount": round(float(r.get("amount") or 0), 2),
            "Balance": round(float(r.get("balance") or 0), 2),
        })
    df = pd.DataFrame(records)
    if df.empty:
        return df
    # Drop empty Ref so Particulars / Ledger get the space
    if "Ref" in df.columns and not df["Ref"].astype(str).str.strip().any():
        df = df.drop(columns=["Ref"])
    if not show_balance and "Balance" in df.columns:
        df = df.drop(columns=["Balance"])
    return df


def _day_book_column_config(df: pd.DataFrame) -> dict:
    """Widths tuned so Income|Expense side panels show every column without scroll."""
    cfg = {
        "Time": st.column_config.TextColumn("Time", width=64, help="Entry time"),
        "Voucher": st.column_config.TextColumn("Voucher", width=100),
        "Particulars": st.column_config.TextColumn("Particulars", width="large"),
        "Ledger": st.column_config.TextColumn(
            "Ledger", width="medium", help="Customer / supplier / GL account",
        ),
        "Ref": st.column_config.TextColumn("Ref", width=72),
        "Amount": st.column_config.NumberColumn(
            "Amount", width=100, format="%.2f", help="Rs.",
        ),
        "Balance": st.column_config.NumberColumn(
            "Balance", width=110, format="%.2f", help="Running cash/bank balance",
        ),
    }
    return {k: v for k, v in cfg.items() if k in df.columns}


def _render_day_book_grid(title: str, rows: list[dict], *, empty_caption: str, key: str):
    st.markdown(f"**{title}**")
    if not rows:
        st.caption(empty_caption)
        return
    df = _day_book_dataframe(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=_day_book_column_config(df),
        height=min(520, 56 + len(df) * 36),
        key=key,
    )
    st.caption(f"{len(df)} row(s) · Amounts in Rs.")


def _init_date_state(prefix, today=None):
    today = today or date.today()
    if f"{prefix}_year" not in st.session_state:
        st.session_state[f"{prefix}_year"] = today.year
        st.session_state[f"{prefix}_month"] = today.month
        st.session_state[f"{prefix}_day"] = today.day


def _selected_date(prefix):
    y = int(st.session_state[f"{prefix}_year"])
    m = int(st.session_state[f"{prefix}_month"])
    d = int(st.session_state[f"{prefix}_day"])
    maxd = monthrange(y, m)[1]
    if d > maxd:
        d = maxd
        st.session_state[f"{prefix}_day"] = d
    return date(y, m, d)


def _date_nav_bar(prefix, label):
    today = date.today()
    _init_date_state(prefix, today)
    sel_iso = _selected_date(prefix).isoformat()
    with st.container(key=f"{prefix}_datenav"):
        nav = st.columns([0.5, 0.55, 0.5, 1.6, 0.7, 0.85, 0.55], gap="small")
        if nav[0].button("◀ Prev", key=f"{prefix}_prev", help="Previous day"):
            nd = _selected_date(prefix) - timedelta(days=1)
            st.session_state[f"{prefix}_year"] = nd.year
            st.session_state[f"{prefix}_month"] = nd.month
            st.session_state[f"{prefix}_day"] = nd.day
            st.rerun()
        if nav[1].button("Today", key=f"{prefix}_today"):
            st.session_state[f"{prefix}_year"] = today.year
            st.session_state[f"{prefix}_month"] = today.month
            st.session_state[f"{prefix}_day"] = today.day
            st.rerun()
        if nav[2].button("Next ▶", key=f"{prefix}_next", help="Next day"):
            nd = _selected_date(prefix) + timedelta(days=1)
            st.session_state[f"{prefix}_year"] = nd.year
            st.session_state[f"{prefix}_month"] = nd.month
            st.session_state[f"{prefix}_day"] = nd.day
            st.rerun()
        nav[3].markdown(f"**{label}** · `{sel_iso}`")
        st.session_state[f"{prefix}_year"] = nav[4].number_input(
            "Year", 2020, 2035, int(st.session_state[f"{prefix}_year"]), key=f"{prefix}_yr",
        )
        st.session_state[f"{prefix}_month"] = nav[5].selectbox(
            "Month", list(range(1, 13)),
            index=int(st.session_state[f"{prefix}_month"]) - 1,
            format_func=lambda x: MONTHS[x - 1],
            key=f"{prefix}_mo",
        )
        maxd = monthrange(int(st.session_state[f"{prefix}_year"]), int(st.session_state[f"{prefix}_month"]))[1]
        st.session_state[f"{prefix}_day"] = nav[6].selectbox(
            "Day", list(range(1, maxd + 1)),
            index=min(int(st.session_state[f"{prefix}_day"]), maxd) - 1,
            key=f"{prefix}_dy",
        )
        y = int(st.session_state[f"{prefix}_year"])
        mo = int(st.session_state[f"{prefix}_month"])
        _day_picker_grid(prefix, maxd, y, mo)


def _day_picker_grid(prefix, maxd, year, month):
    """Compact day grid — green = selected working day, red = holiday."""
    selected = int(st.session_state[f"{prefix}_day"])
    holiday_days = db.cash_month_holiday_days(year, month)
    cols_per_row = 10
    grid_key = f"{prefix}_daygrid"
    day_w = "2.05rem"
    day_h = "1.65rem"
    css_rules = [
        f"""
        div.st-key-{grid_key} [data-testid="stHorizontalBlock"] {{
            gap: 0.15rem !important;
            align-items: flex-start !important;
        }}
        div.st-key-{grid_key} [data-testid="column"] {{
            flex: 0 0 {day_w} !important;
            width: {day_w} !important;
            min-width: {day_w} !important;
            max-width: {day_w} !important;
            padding: 0 !important;
        }}
        div.st-key-{grid_key} div[class*="st-key-{prefix}_db_"] {{
            width: {day_w} !important;
            min-height: unset !important;
        }}
        div.st-key-{grid_key} div[class*="st-key-{prefix}_db_"] [data-testid="stVerticalBlock"] {{
            gap: 0 !important;
        }}
        div.st-key-{grid_key} div[class*="st-key-{prefix}_db_"] button,
        div.st-key-{grid_key} div[class*="st-key-{prefix}_db_"] [data-testid="stBaseButton-secondary"] {{
            height: {day_h} !important;
            min-height: {day_h} !important;
            max-height: {day_h} !important;
            width: {day_w} !important;
            min-width: {day_w} !important;
            max-width: {day_w} !important;
            padding: 0 !important;
            margin: 0 !important;
            font-size: 0.72rem !important;
            line-height: 1 !important;
            box-sizing: border-box !important;
        }}
        """,
    ]

    def _day_color_rule(key, bg, bg_hover, border):
        # Exact st-key class only — [class*=...] would match db_3 on db_30, db_1 on db_10, etc.
        sel = (
            f"div.st-key-{grid_key} div.st-key-{key} button, "
            f"div.st-key-{grid_key} div.st-key-{key} [data-testid='stBaseButton-secondary']"
        )
        return (
            f"{sel} {{ background-color: {bg} !important; border-color: {border} !important; "
            f"color: #ffffff !important; }}"
            f"{sel}:hover {{ background-color: {bg_hover} !important; "
            f"border-color: {border} !important; color: #ffffff !important; }}"
        )

    for d in range(1, maxd + 1):
        key = f"{prefix}_db_{d}"
        if d == selected:
            css_rules.append(_day_color_rule(key, "#198754", "#157347", "#198754"))
        elif d in holiday_days:
            css_rules.append(_day_color_rule(key, "#dc3545", "#bb2d3b", "#dc3545"))
    st.markdown(f"<style>{''.join(css_rules)}</style>", unsafe_allow_html=True)
    with st.container(key=grid_key):
        for row_start in range(0, maxd, cols_per_row):
            cols = st.columns(cols_per_row, gap="small")
            for i, col in enumerate(cols):
                d = row_start + i + 1
                if d > maxd:
                    break
                if col.button(
                    str(d),
                    key=f"{prefix}_db_{d}",
                    type="secondary",
                    use_container_width=False,
                ):
                    st.session_state[f"{prefix}_day"] = d
                    st.rerun()
    legend = "**Green** = working day"
    if holiday_days:
        legend += " · **Red** = off / holiday"
    st.markdown(f'<p class="erp-day-legend">{legend}</p>', unsafe_allow_html=True)


def _voucher_print_from_rows(rows, doc_type, key_prefix, label_fn=None):
    """Print panel for finance register rows (must include id + vch_source)."""
    if not rows:
        return
    label_fn = label_fn or (
        lambda r: f"{r.get('document_no','')} — {r.get('txn_date','')} — "
        f"{fmt_money(r.get('amount', 0))}"
    )
    opts = {label_fn(r): r for r in rows}
    mode = st.radio(
        "Print mode",
        ["One voucher", "Multiple vouchers"],
        horizontal=True,
        key=f"{key_prefix}_vprint_mode",
    )
    if mode.startswith("One"):
        sel = st.selectbox("Select voucher to print", list(opts.keys()), key=f"{key_prefix}_vprint_sel")
        row = opts[sel]
        document_print_toolbar(
            doc_type, row["id"], key_prefix=f"{key_prefix}_vprint",
            vch_source=row.get("vch_source"),
        )
        return

    picks = st.multiselect(
        "Select vouchers to print",
        list(opts.keys()),
        default=[],
        key=f"{key_prefix}_vprint_multi",
        help="Choose one or more vouchers — they print in one job (one page each).",
    )
    b1, b2 = st.columns([1, 3])
    if b1.button("Select all shown", key=f"{key_prefix}_vprint_all"):
        st.session_state[f"{key_prefix}_vprint_multi"] = list(opts.keys())
        st.rerun()
    if not picks:
        st.caption("Select at least one voucher, then open the print dialog.")
        return
    entries = [opts[p] for p in picks if p in opts]
    from erp_ui.report_print import use_print_company_header_checkbox, print_company_header_scope
    include_hdr = use_print_company_header_checkbox(f"{key_prefix}_vprint_batch")
    with print_company_header_scope(include_hdr):
        html = finance_vouchers_batch_html(entries)
    document_print_batch_toolbar(
        html, f"{doc_type} × {len(entries)}", key_prefix=f"{key_prefix}_vprint_batch",
    )


def _cashbook_print_tab(book, key_prefix, sel_date=None, bank_account_id=None):
    if not sel_date:
        st.warning("Select the working day above (year / month / day).")
        return
    ds = str(sel_date)
    rows = db.get_cash_book(ds, ds) if book == "cash" else db.get_bank_book(ds, ds)
    if book == "bank" and bank_account_id:
        rows = [r for r in rows if r.get("account_id") in (None, bank_account_id)]
    if not rows:
        st.info(f"No vouchers on **{ds}** for this book.")
        return
    st.caption(f"Showing vouchers for working day **{ds}** only.")

    def _row_src(r):
        src = r.get("entry_source")
        if src:
            return src
        if r["entry_type"] == "credit":
            return "cash_receipt" if book == "cash" else "bank_receipt"
        return "cash_payment" if book == "cash" else "bank_payment"

    opts = {
        f"{r.get('document_no','')} | "
        f"{'Receipt' if r['entry_type']=='credit' else 'Payment'} | "
        f"{(r.get('description') or '')[:40]} | {fmt_money(r['amount'])}": r
        for r in rows
    }
    mode = st.radio(
        "Print mode",
        ["One voucher", "Multiple vouchers"],
        horizontal=True,
        key=f"{key_prefix}_mode_{ds}",
    )
    if mode.startswith("One"):
        sel = st.selectbox("Voucher", list(opts.keys()), key=f"{key_prefix}_cbsel_{ds}")
        row = opts[sel]
        document_print_toolbar(
            "Finance Voucher", row["id"], key_prefix=f"{key_prefix}_cbpr",
            vch_source=_row_src(row),
        )
        return

    picks = st.multiselect(
        "Select vouchers to print together",
        list(opts.keys()),
        default=[],
        key=f"{key_prefix}_multi_{ds}",
        help="Each voucher prints on its own page in one print job.",
    )
    c1, c2 = st.columns([1, 3])
    if c1.button("Select all for this day", key=f"{key_prefix}_all_{ds}"):
        st.session_state[f"{key_prefix}_multi_{ds}"] = list(opts.keys())
        st.rerun()
    if not picks:
        st.caption("Tick one or more vouchers above, or use **Select all for this day**.")
        return
    entries = []
    for p in picks:
        r = opts.get(p)
        if not r:
            continue
        entries.append({"id": r["id"], "vch_source": _row_src(r)})
    from erp_ui.report_print import use_print_company_header_checkbox, print_company_header_scope
    include_hdr = use_print_company_header_checkbox(f"{key_prefix}_batch_{ds}")
    with print_company_header_scope(include_hdr):
        html = finance_vouchers_batch_html(entries)
    book_label = "Cash" if book == "cash" else "Bank"
    document_print_batch_toolbar(
        html,
        f"{book_label} vouchers {ds} × {len(entries)}",
        key_prefix=f"{key_prefix}_batch_{ds}",
        preview_height=min(900, 320 + 180 * min(len(entries), 4)),
    )


def _expense_system_account_codes():
    """Year-end / control heads that must never be picked as an expense bill line."""
    codes = {"3999"}
    try:
        from db_v3 import gl_account_code
        clr = (gl_account_code("pl_clearing") or "").strip()
        if clr:
            codes.add(clr)
    except Exception:
        pass
    return codes


def _expense_account_opts():
    """Operating expense heads only — exclude P&L clearing and similar system accounts."""
    blocked = _expense_system_account_codes()
    preferred = ("400003", "400015", "400029", "400036")  # misc / mess / stationery / bank charges
    pref_rank = {c: i for i, c in enumerate(preferred)}
    rows = [
        a for a in db.get_accounts(active_only=True)
        if a.get("account_type") == "expense"
        and str(a.get("code") or "") not in blocked
        and "clearing" not in str(a.get("name") or "").lower()
        and "profit & loss" not in str(a.get("name") or "").lower()
    ]
    rows.sort(
        key=lambda a: (
            pref_rank.get(str(a.get("code") or ""), 99),
            str(a.get("code") or ""),
        )
    )
    return {f"{a['code']} - {a['name']}": a["id"] for a in rows}


def _default_expense_account_id(exp_opts: dict):
    if not exp_opts:
        return None
    return list(exp_opts.values())[0]


def _cash_advance_settle_account_rows(advance_account_id=None):
    """GL heads for advance settlement — expense bills or any ledger adjustment."""
    excl = {int(advance_account_id)} if advance_account_id else set()
    return _gl_accounts_for_cash_bank(exclude_ids=excl)


def _gl_accounts_for_cash_bank(exclude_ids=None):
    """All active COA heads except cash/bank asset being posted against."""
    excl = {int(x) for x in (exclude_ids or []) if x is not None}
    rows = []
    for a in db.get_accounts(active_only=True):
        aid = int(a["id"])
        if aid in excl:
            continue
        code = str(a.get("code") or "")
        # Skip primary cash codes (posted as the book side, not the contra)
        if code in ("000000", "1000", "100000"):
            continue
        rows.append(a)
    return rows


def _customer_opts():
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers(active_only=True)}


def _supplier_opts():
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers(active_only=True)}


def _cash_day_status_bar(sel_date, key_prefix="cashbk"):
    """Close / reopen cash day; show lock status on Cash Book."""
    ds = str(sel_date)
    closed = db.is_cash_day_closed(ds)
    info = db.get_cash_day_close(ds) if closed else None
    c1, c2 = st.columns([3, 1])
    if closed:
        by = (info or {}).get("closed_by_name") or "—"
        at = (info or {}).get("closed_at") or ""
        c1.error(
            f"**Cash day closed** ({ds}) — no new cash vouchers and no edit/delete for this date. "
            f"Closed by {by}" + (f" at {at}" if at else "") + "."
        )
        if user_role() == "admin":
            with c2.form(f"{key_prefix}_reopen_form"):
                st.caption("Reopen requires your **admin password**.")
                admin_pwd = st.text_input(
                    "Admin password",
                    type="password",
                    key=f"{key_prefix}_reopen_pwd",
                    autocomplete="current-password",
                )
                if st.form_submit_button("Reopen day", type="primary"):
                    try:
                        db.reopen_cash_day(ds, uid(), admin_password=admin_pwd)
                        ff.action_done(f"Cash day {ds} reopened.")
                    except Exception as e:
                        st.error(str(e))
        else:
            c2.caption("Reopen: administrator + password required")
    else:
        pending = db.pending_cash_invoices_for_date(ds, limit=15)
        if pending:
            refs = ", ".join(
                str(r.get("document_no") or r.get("id")) for r in pending[:8]
            )
            more = f" (+{len(pending) - 8} more)" if len(pending) > 8 else ""
            c1.warning(
                f"Cash day is **open**, but **{len(pending)} cash invoice(s)** are still "
                f"pending approval for {ds}: {refs}{more}. "
                f"Approve / reject / return them before closing the day."
            )
        else:
            c1.info(
                "Cash day is **open** — you can post, edit, and delete cash vouchers for this date."
            )
        notes = c2.text_input("Close notes", key=f"{key_prefix}_close_notes", placeholder="Optional")
        close_disabled = bool(pending)
        if c2.button(
            "Close cash day",
            type="primary",
            key=f"{key_prefix}_close",
            disabled=close_disabled,
        ):
            try:
                db.close_cash_day(ds, uid(), notes=notes)
                ff.action_done(f"Cash day {ds} closed.")
            except Exception as e:
                st.error(str(e))


def _entry_form(book, sel_date, bank_account_id=None, key_prefix="cb"):
    fid = f"{book}_{key_prefix}"
    wk = lambda n: ff.widget_key(fid, n)
    with form_compact(f"{key_prefix}_entry"):
        vtype = st.selectbox(
            "Voucher Type",
            ["Cash Receipt", "Cash Payment"] if book == "cash" else ["Bank Receipt", "Bank Payment"],
            key=wk("vt"),
        )
        is_payment = "Payment" in vtype
        st.caption(
            "Optional: pick **any GL account** (expense, salary, liability, etc.) so the voucher "
            "updates Cash/Bank Book **and** General Ledger. Leave blank for cash/bank-only entry."
        )
        exclude = [bank_account_id] if book == "bank" and bank_account_id else []
        gl_rows = _gl_accounts_for_cash_bank(exclude)
        gl_id = None
        if gl_rows:
            _lbl, gl_id, _rec = smart_select(
                "Account (GL)",
                gl_rows,
                key=wk("gl"),
                placeholder="Type code or name — e.g. Fayyaz, salary, director…",
                max_results=80,
                allow_all=True,
                all_label="— None (cash/bank book only) —",
                layout="row",
            )
            if gl_id:
                side_txt = "debit this account / credit cash-bank" if is_payment else "debit cash-bank / credit this account"
                st.caption(f"Will post to GL: **{side_txt}**.")
        c1, c2, c3 = st.columns([2.4, 1.6, 1.2])
        desc = c1.text_input("Particulars *", key=wk("d"))
        ref = c2.text_input("Reference / Cheque No", key=wk("r"))
        with c3:
            amt = money_input("Amount", value=0.0, min_value=0.0, key=wk("a"))
    if book == "cash" and db.is_cash_day_closed(str(sel_date)):
        st.warning("This cash day is closed — posting is disabled.")
        return
    if st.button("Post Voucher", type="primary", key=f"{key_prefix}_post"):
        if not desc or amt <= 0:
            st.error("Particulars and amount are required.")
        else:
            try:
                def _post_voucher():
                    retain = {}
                    mode = "cash" if book == "cash" else "bank"
                    if gl_id:
                        res = db.record_cash_bank_gl_voucher(
                            gl_id, str(sel_date), amt,
                            side="payment" if is_payment else "receipt",
                            reference_no=ref, description=desc,
                            payment_mode=mode,
                            bank_account_id=bank_account_id if book == "bank" else None,
                            user_id=uid(),
                        )
                        msg = (
                            f"Posted **{res['document_no']}** against **{res.get('account_name', 'GL')}** — "
                            "cash/bank book and General Ledger updated."
                        )
                        if book == "bank":
                            att_type = "bank_payment" if is_payment else "bank_receipt"
                            retain[f"{key_prefix}_slip_preset"] = preset_from_voucher(
                                att_type, res["id"], res.get("document_no"),
                            )
                    else:
                        et = "credit" if "Receipt" in vtype else "debit"
                        if book == "cash":
                            db.add_cash_entry(str(sel_date), desc, ref, et, amt, None, uid())
                            msg = "Voucher posted."
                        else:
                            att_type = "bank_receipt" if "Receipt" in vtype else "bank_payment"
                            res = db.add_bank_entry(str(sel_date), desc, ref, et, amt, bank_account_id, uid())
                            retain[f"{key_prefix}_slip_preset"] = preset_from_voucher(
                                att_type, res["id"], res.get("document_no"),
                            )
                            msg = f"Voucher posted — **{res['document_no']}**. Open **Bank Slips** tab to attach slip."
                    ff.finish_post_new_form(fid, msg, retain=retain or None)

                ff.run_with_loading(_post_voucher, "Posting voucher…")
            except Exception as e:
                st.error(str(e))


def _edit_delete_tab(book, key_prefix="cb", sel_date=None):
    rows = db.get_cash_book() if book == "cash" else db.get_bank_book()
    if sel_date:
        ds = str(sel_date)
        rows = [r for r in rows if r.get("entry_date") == ds]
        if book == "cash" and db.is_cash_day_closed(ds):
            st.error(f"**{ds}** is closed — cash entries for this day cannot be edited or deleted.")
            if rows:
                st.caption(f"{len(rows)} voucher(s) on this day (view only).")
                from erp_ui.helpers import render_dataframe_html_table
                render_dataframe_html_table(pd.DataFrame([{
                    "Voucher": r.get("document_no"),
                    "Type": "Receipt" if r["entry_type"] == "credit" else "Payment",
                    "Account Title": r.get("account_title") or "—",
                    "Particulars": r["description"],
                    "Amount": float(r["amount"]),
                } for r in rows]))
            else:
                st.info("No entries on this day.")
            return
    if not rows:
        st.info("No entries to edit or delete" + (f" for **{sel_date}**." if sel_date else "."))
        return
    from erp_ui.list_paging import page_slice
    view = page_slice(rows, f"{key_prefix}_ed_pg", default_size=50)
    opts = {
        f"{r['entry_date']} | {r.get('document_no','')} | "
        f"{(r.get('account_title') or r['description'] or '')[:40]} | "
        f"{'Receipt' if r['entry_type']=='credit' else 'Payment'} {float(r['amount']):,.2f}": r
        for r in view
    }
    sel = st.selectbox("Select entry", list(opts.keys()), key=f"{key_prefix}_esel")
    if not sel:
        return
    e = opts[sel]
    if book == "cash" and db.is_cash_day_closed(e.get("entry_date")):
        st.error(f"Cannot change voucher on closed day **{e['entry_date']}**.")
        return

    # Account title kind (party / GL)
    cur_pt = (e.get("party_type") or "").lower()
    if cur_pt == "customer":
        kind_default = "Customer"
    elif cur_pt == "supplier":
        kind_default = "Supplier"
    elif cur_pt in ("account", "expense"):
        kind_default = "GL Account"
    else:
        kind_default = "None (book only)"
    kind_opts = ["None (book only)", "Customer", "Supplier", "GL Account"]
    kind = st.selectbox(
        "Account Title Type",
        kind_opts,
        index=kind_opts.index(kind_default),
        key=f"{key_prefix}_title_kind_{e['id']}",
        help="Customer / Supplier / GL head for this voucher (ledger + GL).",
    )

    party_type = None
    party_id = None
    if kind == "Customer":
        custs = db.get_customers(active_only=False)
        _lbl, party_id, _rec = smart_select(
            "Account Title (Customer)",
            custs,
            key=f"{key_prefix}_title_cust_{e['id']}",
            placeholder="Type customer code or name…",
            max_results=80,
            default_id=e.get("party_id") if cur_pt == "customer" else None,
        )
        party_type = "customer" if party_id else None
    elif kind == "Supplier":
        sups = db.get_suppliers(active_only=False)
        _lbl, party_id, _rec = smart_select(
            "Account Title (Supplier)",
            sups,
            key=f"{key_prefix}_title_sup_{e['id']}",
            placeholder="Type supplier code or name…",
            max_results=80,
            default_id=e.get("party_id") if cur_pt == "supplier" else None,
        )
        party_type = "supplier" if party_id else None
    elif kind == "GL Account":
        gl_rows = _gl_accounts_for_cash_bank(
            [e.get("account_id")] if book == "bank" and e.get("account_id") else None
        )
        _lbl, party_id, _rec = smart_select(
            "Account Title (GL)",
            gl_rows,
            key=f"{key_prefix}_title_gl_{e['id']}",
            placeholder="Type GL code or name…",
            max_results=80,
            default_id=e.get("party_id") if cur_pt in ("account", "expense") else None,
        )
        party_type = "account" if party_id else None

    if e.get("account_title"):
        st.caption(f"Current account title: **{e['account_title']}**")

    with st.form(f"{key_prefix}_edit"):
        ed = st.date_input("Date", value=date.fromisoformat(e["entry_date"]))
        desc = st.text_input("Particulars", value=e["description"] or "")
        ref = st.text_input("Reference", value=e.get("reference_no") or "")
        side = st.radio(
            "Type", ["Receipt", "Payment"],
            index=0 if e["entry_type"] == "credit" else 1,
            horizontal=True,
        )
        amt = money_input("Amount", value=float(e["amount"]), min_value=0.0, key=f"{key_prefix}_edit_amt")
        c1, c2 = st.columns(2)
        upd = c1.form_submit_button("Update Entry")
        delb = c2.form_submit_button("Delete Entry")
        if upd:
            et = "credit" if side == "Receipt" else "debit"
            try:
                if kind == "Customer" and side != "Receipt":
                    st.error("Customer account title requires Type = Receipt.")
                elif kind == "Supplier" and side != "Payment":
                    st.error("Supplier account title requires Type = Payment.")
                elif kind != "None (book only)" and not party_id:
                    st.error("Select an account title.")
                else:
                    db.update_cash_bank_book_entry(
                        book,
                        e["id"],
                        e["entry_type"],
                        entry_date=str(ed),
                        description=desc,
                        reference_no=ref,
                        entry_type=et,
                        amount=amt,
                        party_type=party_type,
                        party_id=party_id,
                        bank_account_id=e.get("account_id") if book == "bank" else None,
                        user_id=uid(),
                    )
                    ff.action_done("Updated (including account title).")
            except Exception as ex:
                st.error(str(ex))
        if delb:
            try:
                db.void_cash_bank_book_entry(book, e["id"], e["entry_type"])
                ff.action_done("Deleted.")
            except Exception as ex:
                st.error(str(ex))


def _bank_accounts_for_book():
    """Bank accounts for Bank Book selector — Bank Al Habib first (default), full list."""
    accts = db.get_accounts_by_type("asset") if hasattr(db, "get_accounts_by_type") else db.get_accounts()
    bank_accts = [a for a in accts if "bank" in (a.get("name") or "").lower() or str(a.get("code") or "").startswith("11")]
    if not bank_accts:
        bank_accts = list(accts or [])[:3]

    def _habib_rank(a):
        name = (a.get("name") or "").lower()
        code = str(a.get("code") or "")
        # Prefer the company Al Habib account (100068) at the top of the list
        if code == "100068" or "al habib" in name or "habib" in name:
            if code == "100068" or "al habib" in name:
                return (0, name)
            return (1, name)
        return (2, name)

    return sorted(bank_accts, key=_habib_rank)


def _interactive_book(book="cash"):
    prefix = "cashbk" if book == "cash" else "bankbk"
    title = "Cash Book" if book == "cash" else "Bank Book"
    subtitle = "Daily receipts & payments with opening and closing balance"

    bank_account_id = None
    if book == "bank":
        bank_accts = _bank_accounts_for_book()
        acct_opts = {f"{a['code']} - {a['name']}": a["id"] for a in bank_accts}
        if not acct_opts:
            std_page_header(title, subtitle=subtitle, status="register", status_kind="shell")
            st.error("No bank accounts found in Chart of Accounts. Add an asset account with “Bank” in the name.")
            return
        acct_lbl = st.selectbox("Bank Account", list(acct_opts.keys()), key=f"{prefix}_acct")
        if not acct_lbl:
            return
        bank_account_id = acct_opts[acct_lbl]

    _date_nav_bar(prefix, title)
    sel_date = _selected_date(prefix)
    ds = str(sel_date)

    cash_closed = book == "cash" and db.is_cash_day_closed(ds)
    peek = st.session_state.get(f"{prefix}_book_tab") or "Daily Book"
    hdr_status = None
    if peek == "Daily Book":
        hdr_status = "locked" if cash_closed else "posted"
    std_page_header(
        title,
        subtitle=subtitle,
        status=hdr_status,
        status_kind="shell",
    )

    if book == "cash":
        _cash_day_status_bar(sel_date, prefix)

    raw = db.get_cash_book(ds, ds) if book == "cash" else db.get_bank_book(ds, ds)
    if book == "bank" and bank_account_id:
        raw = [r for r in raw if r.get("account_id") in (None, bank_account_id)]

    opening = _cash_opening(ds) if book == "cash" else _bank_opening(ds, bank_account_id)
    receipts, payments, total_in, total_out, closing = _day_rows(raw, opening)
    provisional_n = 0
    pending_sales_total = 0.0
    if book == "cash":
        provisional_n, pending_sales_total = _append_provisional_cash_sales(receipts, closing, ds)

    posted_entry_count = len(receipts) + len(payments) - provisional_n
    expected_closing = closing + pending_sales_total

    with st.container(key=f"{prefix}_metrics"):
        from erp_ui.page_shell import shell_status_badge
        strip_bits = [
            f'{shell_status_badge("posted", kind="shell")}&nbsp;<strong>Book</strong>',
        ]
        if book == "cash" and cash_closed:
            strip_bits.insert(
                0,
                f'{shell_status_badge("locked", kind="shell")}&nbsp;<strong>Day closed</strong>',
            )
        if book == "cash" and pending_sales_total > 0:
            strip_bits.append(
                f'{shell_status_badge("pending_approval", kind="invoice")}&nbsp;'
                f'Pending cash sales <strong>{fmt_money(pending_sales_total)}</strong>'
            )
        st.markdown(
            f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(strip_bits)}</div>',
            unsafe_allow_html=True,
        )

        def _kpi(label, value, help_txt=""):
            tip = f' title="{help_txt}"' if help_txt else ""
            return (
                f"<div class='txn-kpi-card'{tip}><p class='txn-kpi'>{label}</p>"
                f"<p class='txn-kpi-val'>{value}</p></div>"
            )

        m1, m2, m3, m4, m5 = st.columns(5, gap="small")
        m1.markdown(_kpi("Opening", fmt_money(opening)), unsafe_allow_html=True)
        m2.markdown(_kpi("Receipts", fmt_money(total_in)), unsafe_allow_html=True)
        m3.markdown(_kpi("Payments", fmt_money(total_out)), unsafe_allow_html=True)
        m4.markdown(
            _kpi("Closing", fmt_money(closing), "Posted cash only (approved receipts and payments)."),
            unsafe_allow_html=True,
        )
        m5.markdown(_kpi("Entries", str(posted_entry_count)), unsafe_allow_html=True)
        if book == "cash" and pending_sales_total > 0:
            cols = st.columns(2, gap="small")
            cols[0].markdown(
                _kpi(
                    "Pending cash sales",
                    fmt_money(pending_sales_total),
                    f"{provisional_n} draft/pending cash invoice(s) — not in Closing until approved.",
                ),
                unsafe_allow_html=True,
            )
            cols[1].markdown(
                _kpi(
                    "Expected closing",
                    fmt_money(expected_closing),
                    "Closing after pending cash sales are approved.",
                ),
                unsafe_allow_html=True,
            )
    if book == "cash" and provisional_n:
        st.caption(
            f"{provisional_n} draft/pending cash sale(s) under Income ([drafted]/[pending]) — "
            f"**{fmt_money(pending_sales_total)}** not in **Closing** until approved in **Sale Approval**. "
            f"Expected closing if approved: **{fmt_money(expected_closing)}**."
        )

    from erp_ui.helpers import section_header, sticky_page_tabs
    section_header("Daily entries & vouchers")
    if book == "bank":
        book_tabs = ["Daily Book", "Post Voucher", "Edit / Delete", "Print Voucher", "Bank Slips"]
    else:
        book_tabs = ["Daily Book", "Post Voucher", "Edit / Delete", "Print Voucher"]
    with st.container(key=f"{prefix}_book_body"):
        bk_tab = sticky_page_tabs(book_tabs, f"{prefix}_book_tab")

        if bk_tab == "Daily Book":
            # Classic Income | Expense side-by-side on a widened panel so all columns fit
            with st.container(key=f"{prefix}_day_wide"):
                left, right = st.columns(2, gap="medium")
                with left:
                    _render_day_book_grid(
                        "Income / Receipts", receipts,
                        empty_caption="No receipts today.",
                        key=f"{prefix}_recv_grid",
                    )
                with right:
                    _render_day_book_grid(
                        "Expenses / Payments", payments,
                        empty_caption="No payments today.",
                        key=f"{prefix}_pay_grid",
                    )
            if not receipts and not payments and not (book == "cash" and cash_closed):
                if st.button("Post voucher", type="primary", key=f"{prefix}_empty_post"):
                    st.session_state[f"{prefix}_book_tab"] = "Post Voucher"
                    st.rerun()
            all_rows = receipts + payments
            all_rows.sort(key=lambda r: (r.get("voucher", ""), r["particulars"]))
            if all_rows:
                ledger_toolbar(
                    title, opening, [
                        {
                            "date": ds,
                            "particulars": (
                                f"{r['particulars']}"
                                + (f" · {r['ledger']}" if (r.get("ledger") or "").strip() else "")
                            ),
                            "ref": r["ref"],
                            "income": r["amount"] if r in receipts else "",
                            "expense": r["amount"] if r in payments else "",
                            "balance": r["balance"],
                        }
                        for r in all_rows
                    ],
                    total_in, total_out, closing,
                    f"{title} — {ds}", f"{book}_book_{ds}", key_prefix=f"{prefix}_print",
                )

        elif bk_tab == "Post Voucher":
            _entry_form(book, sel_date, bank_account_id, key_prefix=f"{prefix}_new")

        elif bk_tab == "Edit / Delete":
            _edit_delete_tab(book, key_prefix=f"{prefix}_ed", sel_date=sel_date)

        elif bk_tab == "Print Voucher":
            _cashbook_print_tab(
                book, key_prefix=f"{prefix}_pr", sel_date=sel_date, bank_account_id=bank_account_id,
            )

        elif book == "bank" and bk_tab == "Bank Slips":
            preset = st.session_state.get(f"{prefix}_slip_preset")
            slip_attachment_workspace(
                ["bank_receipt", "bank_payment"], f"{prefix}_slips",
                preset=preset,
                title="Bank slips",
            )


def page_cash_book():
    _interactive_book("cash")


def page_bank_book():
    _interactive_book("bank")


def _bank_account_opts():
    accts = db.get_accounts_by_type("asset") if hasattr(db, "get_accounts_by_type") else db.get_accounts()
    bank = [a for a in accts if "bank" in a["name"].lower() or str(a["code"]).startswith("11")]
    if not bank:
        bank = [a for a in accts if str(a["code"]).startswith("11")]
    if not bank:
        bank = accts[:5]
    return {f"{a['code']} - {a['name']}": a["id"] for a in bank}


def _party_receipt_register(
    search_fn, party_label, key_prefix,
    *, empty_tab_key=None, empty_tab_value=None, empty_cta_label=None,
):
    from html import escape

    party_opts = (
        {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers()}
        if party_label == "Customer"
        else {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers()}
    )
    st.markdown('<div class="txn-filter-box">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2.2, 1.4, 1, 1])
    q = c1.text_input("Search", placeholder="Voucher, party, reference…", key=f"{key_prefix}_q")
    party_lbl = c2.selectbox(party_label, ["All"] + list(party_opts.keys()), key=f"{key_prefix}_party")
    fd = c3.date_input("From", value=None, key=f"{key_prefix}_fd")
    td = c4.date_input("To", value=None, key=f"{key_prefix}_td")
    st.markdown("</div>", unsafe_allow_html=True)
    party_id = party_opts.get(party_lbl) if party_lbl != "All" else None
    kwargs = {
        "q": q or None,
        "from_date": str(fd) if fd else None,
        "to_date": str(td) if td else None,
        "page": 1,
        "page_size": 50,
    }
    if party_label == "Customer":
        kwargs["customer_id"] = party_id
    else:
        kwargs["supplier_id"] = party_id
    result = search_fn(**kwargs)
    rows = result.get("items") or result.get("rows") or []
    total_amt = sum(float(r.get("amount") or 0) for r in rows)
    k1, k2 = st.columns(2)
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Records</p>"
        f"<p class='txn-kpi-val'>{result.get('total', len(rows)):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Amount (this page)</p>"
        f"<p class='txn-kpi-val'>{fmt_money(total_amt)}</p></div>",
        unsafe_allow_html=True,
    )
    if rows:
        # Mode as badge-like chips via status CSS when cash/bank
        ths = "".join(
            f"<th>{h}</th>"
            for h in ("Date / Time", "Voucher", "Party", "Mode", "Reference", "Description", "Amount")
        )
        body = []
        for r in rows:
            mode = (r.get("payment_mode") or "").lower()
            if mode == "cash":
                mode_html = '<span class="inv-badge inv-badge-approved">Cash</span>'
            elif mode == "bank":
                mode_html = '<span class="inv-badge inv-badge-pending">Bank</span>'
            else:
                mode_html = escape((r.get("payment_mode") or "—").title())
            body.append(
                "<tr>"
                f"<td>{escape(fmt_datetime_from_record(r, 'txn_date'))}</td>"
                f"<td>{escape(str(r.get('document_no') or ''))}</td>"
                f"<td>{escape(str(r.get('customer_name') or r.get('supplier_name') or ''))}</td>"
                f"<td>{mode_html}</td>"
                f"<td>{escape(str(r.get('reference_no') or ''))}</td>"
                f"<td>{escape(str(r.get('description') or ''))}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('amount')))}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Showing {len(rows)} of {result.get('total', len(rows))} record(s)")
        doc_type = "Customer Receipt" if party_label == "Customer" else "Supplier Payment"
        st.divider()
        _voucher_print_from_rows(
            rows, doc_type, key_prefix,
            label_fn=lambda r: (
                f"{r['document_no']} — {r.get('customer_name') or r.get('supplier_name')} — "
                f"{fmt_datetime_from_record(r, 'txn_date')} — {fmt_money(r['amount'])}"
            ),
        )
        bank_rows = [r for r in rows if (r.get("payment_mode") or "").lower() == "bank"]
        if bank_rows:
            st.caption("For bank slip attachments, search the voucher no under **Bank Book → Bank Slips**.")
    else:
        st.info("No receipts/payments found.")
        if empty_tab_key and empty_tab_value:
            if st.button(
                empty_cta_label or "New entry",
                type="primary",
                key=f"{key_prefix}_empty_cta",
            ):
                st.session_state[empty_tab_key] = empty_tab_value
                st.rerun()


def page_customer_receipt():
    from erp_ui.helpers import sticky_page_tabs
    peek = st.session_state.get("cr_page_tab") or "Register"
    std_page_header(
        "Customer Receipt",
        status="register" if peek == "Register" else "posted",
        status_kind="shell",
    )
    tab = sticky_page_tabs(["Register", "New Receipt"], "cr_page_tab")
    if tab == "Register":
        _party_receipt_register(
            db.search_customer_receipts, "Customer", "cust_rcpt",
            empty_tab_key="cr_page_tab",
            empty_tab_value="New Receipt",
            empty_cta_label="New Receipt",
        )
    else:
        fid = "cust_rcpt"
        wk = lambda n: ff.widget_key(fid, n)
        cust_opts = {f"{r['code']} - {r['name']}": r for r in db.get_customers()}
        if not cust_opts:
            st.warning("Add customers first.")
            return
        with form_compact("cr_new"):
            c1, c2 = st.columns([2.4, 1.2])
            cust_lbl = c1.selectbox("Customer *", list(cust_opts.keys()), key=wk("cust"))
            cust = cust_opts[cust_lbl]
            c2.metric("Current Balance", fmt_money(cust.get("current_balance")))
            r1, r2 = st.columns([1.2, 1.6])
            rdate = r1.date_input("Receipt Date", value=date.today(), key=wk("date"))
            mode = r2.radio("Payment Mode", ["Cash", "Bank"], horizontal=True, key=wk("mode"))
            bank_id = None
            if mode == "Bank":
                bank_opts = _bank_account_opts()
                if not bank_opts:
                    st.error("No bank accounts in chart of accounts.")
                    return
                bank_id = bank_opts[st.selectbox("Bank Account *", list(bank_opts.keys()), key=wk("bank"))]
            c3, c4, c5 = st.columns([1.6, 1.2, 2.2])
            ref = c3.text_input("Reference / Cheque No", key=wk("ref"))
            with c4:
                amt = money_input("Amount *", value=0.01, min_value=0.01, key=wk("amt"))
            desc = c5.text_input("Description", value=f"Receipt from {cust['name']}", key=wk("desc"))
            cash_blocked = mode == "Cash" and db.is_cash_day_closed(str(rdate))
            if cash_blocked:
                st.warning(
                    f"Cash book for **{rdate}** is closed — choose another date or ask admin to reopen the day."
                )
            if st.button(
                "Post Customer Receipt", type="primary", key="cr_post", disabled=cash_blocked,
            ):
                try:
                    res = db.record_customer_receipt(
                        cust["id"], str(rdate), amt, ref, desc,
                        payment_mode=mode.lower(), bank_account_id=bank_id, user_id=uid(),
                    )
                    book = "Bank Book" if mode == "Bank" else "Cash Book"
                    retain = {"last_cr_print": res}
                    if (mode or "").lower() == "bank":
                        att = db.vch_source_to_attachment_type(res.get("vch_source"))
                        if att:
                            retain["cr_slip_preset"] = preset_from_voucher(att, res["id"], res.get("document_no"))
                    ff.finish_post_new_form(
                        fid,
                        f"Posted **{res['document_no']}** — appears in **{book}**, "
                        f"**Customer Ledger**, and **General Ledger**.",
                        retain=retain,
                    )
                except Exception as e:
                    st.error(str(e))
        if st.session_state.get("last_cr_print"):
            res = st.session_state.pop("last_cr_print")
            document_print_toolbar(
                "Customer Receipt", res["id"], key_prefix="cr_new_print",
                vch_source=res.get("vch_source"),
            )
            if (res.get("payment_mode") or "").lower() == "bank":
                preset = st.session_state.get("cr_slip_preset")
                st.divider()
                slip_attachment_workspace(
                    ["bank_receipt"], "cr_new_slip", preset=preset, title="Bank receipt slip",
                )


def page_supplier_payment():
    from erp_ui.helpers import sticky_page_tabs
    peek = st.session_state.get("sp_page_tab") or "Register"
    std_page_header(
        "Supplier Payment",
        status="register" if peek == "Register" else "posted",
        status_kind="shell",
    )
    tab = sticky_page_tabs(["Register", "New Payment"], "sp_page_tab")
    if tab == "Register":
        _party_receipt_register(
            db.search_supplier_payments, "Supplier", "sup_pay",
            empty_tab_key="sp_page_tab",
            empty_tab_value="New Payment",
            empty_cta_label="New Payment",
        )
    else:
        fid = "sup_pay"
        wk = lambda n: ff.widget_key(fid, n)
        sup_opts = {f"{r['code']} - {r['name']}": r for r in db.get_suppliers()}
        if not sup_opts:
            st.warning("Add suppliers first.")
            return
        with form_compact("sp_new"):
            c1, c2 = st.columns([2.4, 1.2])
            sup_lbl = c1.selectbox("Supplier *", list(sup_opts.keys()), key=wk("sup"))
            sup = sup_opts[sup_lbl]
            c2.metric("Current Balance", fmt_money(sup.get("current_balance")))
            r1, r2 = st.columns([1.2, 1.6])
            pdate = r1.date_input("Payment Date", value=date.today(), key=wk("date"))
            mode = r2.radio("Payment Mode", ["Cash", "Bank"], horizontal=True, key=wk("mode"))
            bank_id = None
            if mode == "Bank":
                bank_opts = _bank_account_opts()
                if not bank_opts:
                    st.error("No bank accounts in chart of accounts.")
                    return
                bank_id = bank_opts[st.selectbox("Bank Account *", list(bank_opts.keys()), key=wk("bank"))]
            c3, c4, c5 = st.columns([1.6, 1.2, 2.2])
            ref = c3.text_input("Reference / Cheque No", key=wk("ref"))
            with c4:
                amt = money_input("Amount *", value=0.01, min_value=0.01, key=wk("amt"))
            desc = c5.text_input("Description", value=f"Payment to {sup['name']}", key=wk("desc"))
            cash_blocked = mode == "Cash" and db.is_cash_day_closed(str(pdate))
            if cash_blocked:
                st.warning(
                    f"Cash book for **{pdate}** is closed — choose another date or ask admin to reopen the day."
                )
            if st.button(
                "Post Supplier Payment", type="primary", key="sp_post", disabled=cash_blocked,
            ):
                try:
                    res = db.record_supplier_payment(
                        sup["id"], str(pdate), amt, ref, desc,
                        payment_mode=mode.lower(), bank_account_id=bank_id, user_id=uid(),
                    )
                    book = "Bank Book" if mode == "Bank" else "Cash Book"
                    retain = {"last_sp_print": res}
                    if (mode or "").lower() == "bank":
                        att = db.vch_source_to_attachment_type(res.get("vch_source"))
                        if att:
                            retain["sp_slip_preset"] = preset_from_voucher(att, res["id"], res.get("document_no"))
                    ff.finish_post_new_form(
                        fid,
                        f"Posted **{res['document_no']}** — appears in **{book}**, "
                        f"**Supplier Ledger**, and **General Ledger**.",
                        retain=retain,
                    )
                except Exception as e:
                    st.error(str(e))
        if st.session_state.get("last_sp_print"):
            res = st.session_state.pop("last_sp_print")
            document_print_toolbar(
                "Supplier Payment", res["id"], key_prefix="sp_new_print",
                vch_source=res.get("vch_source"),
            )
            if (res.get("payment_mode") or "").lower() == "bank":
                preset = st.session_state.get("sp_slip_preset")
                st.divider()
                slip_attachment_workspace(
                    ["bank_payment"], "sp_new_slip", preset=preset, title="Bank payment slip",
                )


def _expense_payment_register(key_prefix):
    from html import escape

    exp_opts = {
        f"{a['code']} - {a['name']}": a["id"]
        for a in db.get_accounts(active_only=True)
        if a.get("account_type") == "expense"
    }
    st.markdown('<div class="txn-filter-box">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    q = c1.text_input("Search", placeholder="Voucher, expense account, reference...", key=f"{key_prefix}_q")
    exp_lbl = c2.selectbox("Expense Account", ["All"] + list(exp_opts.keys()), key=f"{key_prefix}_exp")
    today = date.today()
    for _dk in (f"{key_prefix}_fd", f"{key_prefix}_td"):
        if st.session_state.get(_dk) is None:
            st.session_state[_dk] = today
    fd = c3.date_input("From", key=f"{key_prefix}_fd")
    td = c4.date_input("To", key=f"{key_prefix}_td")
    st.markdown("</div>", unsafe_allow_html=True)
    result = db.search_expense_payments(
        q=q or None,
        expense_account_id=exp_opts.get(exp_lbl) if exp_lbl != "All" else None,
        from_date=str(fd) if fd else None,
        to_date=str(td) if td else None,
        page=1,
        page_size=50,
    )
    rows = result.get("items") or []
    total_amt = sum(float(r.get("amount") or 0) for r in rows)
    k1, k2 = st.columns(2)
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Records</p>"
        f"<p class='txn-kpi-val'>{result.get('total', len(rows)):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Amount (this page)</p>"
        f"<p class='txn-kpi-val'>{fmt_money(total_amt)}</p></div>",
        unsafe_allow_html=True,
    )
    if rows:
        ths = "".join(
            f"<th>{h}</th>"
            for h in ("Date / Time", "Voucher", "Expense", "Mode", "Reference", "Description", "Amount")
        )
        body = []
        for r in rows:
            mode = (r.get("payment_mode") or "").lower()
            if mode == "cash":
                mode_html = '<span class="inv-badge inv-badge-approved">Cash</span>'
            elif mode == "bank":
                mode_html = '<span class="inv-badge inv-badge-pending">Bank</span>'
            else:
                mode_html = escape((r.get("payment_mode") or "—").title())
            exp_lbl = f"{r.get('expense_code') or ''} — {r.get('expense_name') or ''}"
            body.append(
                "<tr>"
                f"<td>{escape(fmt_datetime_from_record(r, 'txn_date'))}</td>"
                f"<td>{escape(str(r.get('document_no') or ''))}</td>"
                f"<td>{escape(exp_lbl)}</td>"
                f"<td>{mode_html}</td>"
                f"<td>{escape(str(r.get('reference_no') or ''))}</td>"
                f"<td>{escape(str(r.get('description') or ''))}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('amount')))}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Showing {len(rows)} of {result.get('total', len(rows))} record(s)")
        st.divider()
        _voucher_print_from_rows(
            rows, "Expense Payment", key_prefix,
            label_fn=lambda r: (
                f"{r['document_no']} — {r.get('expense_name','')} — "
                f"{fmt_datetime_from_record(r, 'txn_date')} — {fmt_money(r['amount'])}"
            ),
        )
    else:
        st.info("No expense payments found.")
        if st.button("New Expense Payment", type="primary", key=f"{key_prefix}_empty_cta"):
            st.session_state["ep_page_tab"] = "New Payment"
            st.rerun()


def page_expense_payment():
    from erp_ui.helpers import sticky_page_tabs
    peek = st.session_state.get("ep_page_tab") or "Register"
    std_page_header(
        "Expense Payment",
        status="register" if peek == "Register" else "posted",
        status_kind="shell",
    )
    tab = sticky_page_tabs(["Register", "New Payment"], "ep_page_tab")
    if tab == "Register":
        _expense_payment_register("exp_pay")
    else:
        fid = "exp_pay"
        wk = lambda n: ff.widget_key(fid, n)
        exp_opts = _expense_account_opts()
        if not exp_opts:
            st.warning("Add expense accounts in Chart of Accounts first.")
            return
        with form_compact("ep_new"):
            exp_lbl = st.selectbox("Expense Account *", list(exp_opts.keys()), key=wk("acct"))
            r1, r2 = st.columns([1.2, 1.6])
            pdate = r1.date_input("Payment Date", value=date.today(), key=wk("date"))
            mode = r2.radio("Payment Mode", ["Cash", "Bank"], horizontal=True, key=wk("mode"))
            bank_id = None
            if mode == "Bank":
                bank_opts = _bank_account_opts()
                if not bank_opts:
                    st.error("No bank accounts in chart of accounts.")
                    return
                bank_id = bank_opts[st.selectbox("Bank Account *", list(bank_opts.keys()), key=wk("bank"))]
            c3, c4, c5 = st.columns([1.6, 1.2, 2.2])
            ref = c3.text_input("Reference / Cheque No", key=wk("ref"))
            with c4:
                amt = money_input("Amount *", value=0.01, min_value=0.01, key=wk("amt"))
            desc = c5.text_input("Description", value=exp_lbl.split(" - ", 1)[-1], key=wk("desc"))
            cash_blocked = mode == "Cash" and db.is_cash_day_closed(str(pdate))
            if cash_blocked:
                st.warning(
                    f"Cash book for **{pdate}** is closed — choose another date or ask admin to reopen the day."
                )
            if st.button(
                "Post Expense Payment", type="primary", key="ep_post", disabled=cash_blocked,
            ):
                try:
                    res = db.record_expense_payment(
                        exp_opts[exp_lbl], str(pdate), amt, ref, desc,
                        payment_mode=mode.lower(), bank_account_id=bank_id, user_id=uid(),
                    )
                    book = "Bank Book" if mode == "Bank" else "Cash Book"
                    ff.finish_post_new_form(
                        fid,
                        f"Posted **{res['document_no']}** — appears in **{book}** and **General Ledger**.",
                        retain={"last_ep_print": res},
                    )
                except Exception as e:
                    st.error(str(e))
        if st.session_state.get("last_ep_print"):
            res = st.session_state.pop("last_ep_print")
            document_print_toolbar(
                "Expense Payment", res["id"], key_prefix="ep_new_print",
                vch_source=res.get("vch_source"),
            )


def page_expense_bill():
    from erp_ui.helpers import sticky_page_tabs
    peek = st.session_state.get("eb_page_tab") or "Register"
    std_page_header(
        "Expense Bill",
        subtitle="Multi expense heads / one bill",
        status="register" if peek == "Register" else "draft",
        status_kind="shell" if peek == "Register" else "invoice",
    )
    tab = sticky_page_tabs(["Register", "New Bill"], "eb_page_tab")
    if tab == "Register":
        _expense_bill_register("exp_bill")
    else:
        _expense_bill_form("exp_bill")


def _expense_bill_register(key_prefix):
    from html import escape

    st.markdown('<div class="txn-filter-box">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    q = c1.text_input("Search", placeholder="Bill no, reference, description…", key=f"{key_prefix}_q")
    pt = c2.selectbox("Party type", ["All", "Supplier", "Customer"], key=f"{key_prefix}_pt")
    fd = c3.date_input("From", value=None, key=f"{key_prefix}_fd")
    td = c4.date_input("To", value=None, key=f"{key_prefix}_td")
    st.markdown("</div>", unsafe_allow_html=True)
    result = db.search_expense_bills(
        q=q or None,
        party_type=None if pt == "All" else pt.lower(),
        from_date=str(fd) if fd else None,
        to_date=str(td) if td else None,
        page=1,
        page_size=50,
    )
    rows = result.get("items") or []
    if not rows:
        st.info("No expense bills found.")
        return
    total_amt = sum(float(r.get("total_amount") or 0) for r in rows)
    k1, k2 = st.columns(2)
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Bills</p>"
        f"<p class='txn-kpi-val'>{result.get('total', len(rows)):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Total (this page)</p>"
        f"<p class='txn-kpi-val'>{fmt_money(total_amt)}</p></div>",
        unsafe_allow_html=True,
    )
    ths = "".join(
        f"<th>{h}</th>"
        for h in ("Bill", "Date / Time", "Party", "Type", "Settlement", "Reference", "Total", "Note")
    )
    body = []
    for r in rows:
        settle = (r.get("settlement") or "").lower()
        if settle == "cash":
            settle_html = '<span class="inv-badge inv-badge-approved">Cash</span>'
        elif settle == "bank":
            settle_html = '<span class="inv-badge inv-badge-pending">Bank</span>'
        elif settle == "credit":
            settle_html = '<span class="inv-badge inv-badge-draft">Credit</span>'
        else:
            settle_html = escape((r.get("settlement") or "—").title())
        party = f"{r.get('party_code') or ''} — {r.get('party_name') or ''}"
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('document_no') or ''))}</td>"
            f"<td>{escape(fmt_datetime_from_record(r, 'bill_date'))}</td>"
            f"<td>{escape(party)}</td>"
            f"<td>{escape((r.get('party_type') or '').title())}</td>"
            f"<td>{settle_html}</td>"
            f"<td>{escape(str(r.get('reference_no') or ''))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(r.get('total_amount')))}</td>"
            f"<td>{escape(str((r.get('description') or '')[:60]))}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Showing {len(rows)} of {result.get('total', len(rows))} bill(s)")
    st.divider()
    labels = {
        str(r["id"]): (
            f"{r['document_no']} — {r.get('party_name','')} — "
            f"{fmt_datetime_from_record(r, 'bill_date')} — {fmt_money(r.get('total_amount'))}"
        )
        for r in rows
    }
    sel = st.selectbox(
        "Print bill", list(labels.keys()), format_func=lambda k: labels[k], key=f"{key_prefix}_print_sel",
    )
    if sel:
        document_print_toolbar("Expense Bill", int(sel), key_prefix=f"{key_prefix}_print")


def _expense_bill_form(key_prefix):
    from erp_ui.helpers import customer_select, supplier_select

    fid = key_prefix
    wk = lambda n: ff.widget_key(fid, n)
    exp_opts = _expense_account_opts()
    if not exp_opts:
        st.warning("Add expense accounts in Chart of Accounts first.")
        return

    default_aid = _default_expense_account_id(exp_opts)
    sk = f"{key_prefix}_lines"
    if sk not in st.session_state:
        st.session_state[sk] = [
            {"expense_account_id": default_aid, "narration": "", "amount": 0.0},
        ]

    with form_compact(f"{key_prefix}_bill"):
        st.caption(
            "Credit books the **party ledger**. Cash/Bank pays now and posts to Cash/Bank Book. "
            "Each expense head must be its own line."
        )
        c1, c2 = st.columns([1.4, 1.2])
        party_kind = c1.radio("Party type *", ["Supplier", "Customer"], horizontal=True, key=wk("ptype"))
        with c2:
            bdate = st.date_input("Bill date *", value=date.today(), key=wk("date"))
        # Separate keys so switching Supplier ↔ Customer does not keep a stale selection.
        if party_kind == "Supplier":
            party_id = supplier_select(wk("sup"))
        else:
            party_id = customer_select(wk("cust"))

        settle = st.radio(
            "Settlement *",
            ["Credit", "Cash", "Bank"],
            horizontal=True,
            key=wk("settle"),
            help="Credit books the party ledger. Cash/Bank pays now.",
        )
        bank_id = None
        if settle == "Bank":
            bank_opts = _bank_account_opts()
            if not bank_opts:
                st.error("No bank accounts in chart of accounts.")
                return
            bank_id = bank_opts[st.selectbox("Bank Account *", list(bank_opts.keys()), key=wk("bank"))]

        c3, c4 = st.columns([1.4, 2.2])
        ref = c3.text_input("Reference", key=wk("ref"))
        note = c4.text_input("Bill note (header only)", key=wk("note"), placeholder="Short note — not a merge of lines")

        st.markdown("**Expense lines** — each head on its own row (do not merge narrations).")
        lines = st.session_state[sk]
        exp_keys = list(exp_opts.keys())
        for i, ln in enumerate(lines):
            with form_line(f"{key_prefix}_el{i}"):
                cols = st.columns([2.6, 2.8, 1.15, 0.4])
                cur_id = ln.get("expense_account_id")
                if cur_id not in exp_opts.values():
                    cur_id = default_aid
                    lines[i]["expense_account_id"] = cur_id
                idx = 0
                for j, (_, aid) in enumerate(exp_opts.items()):
                    if aid == cur_id:
                        idx = j
                        break
                ak = cols[0].selectbox(
                    "Expense account", exp_keys, index=min(idx, len(exp_keys) - 1), key=f"{key_prefix}_ea_{i}",
                )
                lines[i]["expense_account_id"] = exp_opts[ak]
                narr_key = f"{key_prefix}_en_{i}"
                if narr_key not in st.session_state:
                    st.session_state[narr_key] = ln.get("narration") or ""
                lines[i]["narration"] = cols[1].text_input(
                    "Narration", key=narr_key,
                    placeholder="Narration for this expense only",
                )
                with cols[2]:
                    lines[i]["amount"] = money_input(
                        "Amount", value=float(ln.get("amount") or 0), min_value=0.0, key=f"{key_prefix}_em_{i}",
                    )
                if cols[3].button("✕", key=f"{key_prefix}_ex_{i}", help="Remove line") and len(lines) > 1:
                    lines.pop(i)
                    st.rerun()

        tot = sum(float(l.get("amount") or 0) for l in lines)
        st.metric("Bill total", fmt_money(tot))

        blockers = []
        if not party_id:
            blockers.append(f"select a **{party_kind}**")
        if tot <= 0 or any(float(l.get("amount") or 0) <= 0 for l in lines):
            blockers.append("enter an **amount greater than zero** on every line")
        if settle == "Cash" and db.is_cash_day_closed(str(bdate)):
            st.warning(f"Cash book for **{bdate}** is closed — choose another date or reopen the day.")
            blockers.append("cash day is closed")
        if blockers:
            st.info("To post: " + " · ".join(blockers) + ".")

        b1, b2, b3 = st.columns(3)
        if b1.button("Add expense line", key=f"{key_prefix}_add", use_container_width=True):
            lines.append({
                "expense_account_id": default_aid,
                "narration": "",
                "amount": 0.0,
            })
            st.rerun()
        if b2.button("Clear lines", key=f"{key_prefix}_clr", use_container_width=True):
            st.session_state[sk] = [
                {"expense_account_id": default_aid, "narration": "", "amount": 0.0},
            ]
            st.rerun()

        can_post = party_id and tot > 0 and all(float(l.get("amount") or 0) > 0 for l in lines)
        if settle == "Cash" and db.is_cash_day_closed(str(bdate)):
            can_post = False
        if b3.button(
            "Post Expense Bill", type="primary", key=f"{key_prefix}_post",
            disabled=not can_post, use_container_width=True,
        ):
            try:
                res = db.record_expense_bill(
                    party_kind.lower(),
                    party_id,
                    str(bdate),
                    lines,
                    settlement=settle.lower(),
                    bank_account_id=bank_id,
                    reference_no=ref,
                    description=note,
                    user_id=uid(),
                )
                del st.session_state[sk]
                ff.finish_post_new_form(
                    fid,
                    f"Posted **{res['document_no']}** — {len(lines)} expense line(s), "
                    f"settlement **{settle}**, total {fmt_money(res['total_amount'])}.",
                    retain={"last_eb_print": res["id"]},
                )
            except Exception as e:
                st.error(str(e))

    if st.session_state.get("last_eb_print"):
        bid = st.session_state.pop("last_eb_print")
        document_print_toolbar("Expense Bill", int(bid), key_prefix=f"{key_prefix}_new_print")


def page_party_transfer():
    from erp_ui.helpers import sticky_page_tabs
    peek = st.session_state.get("pt_page_tab") or "Register & Print"
    std_page_header(
        "Party Transfer",
        status="register" if "Register" in peek else "posted",
        status_kind="shell",
    )
    tab = sticky_page_tabs(
        ["New Transfer", "Register & Print", "Edit / Delete", "Slips"],
        "pt_page_tab",
    )
    if tab == "Register & Print":
        _party_transfer_register("pt_reg")
    elif tab == "New Transfer":
        _party_transfer_form()
    elif tab == "Edit / Delete":
        _party_transfer_edit_tab("pt_edit")
    else:
        preset = st.session_state.get("pt_slip_preset")
        slip_attachment_workspace(["party_transfer"], "pt_slips", preset=preset, title="Party transfer slips")


def _party_transfer_register(key_prefix):
    from html import escape

    st.markdown('<div class="txn-filter-box">', unsafe_allow_html=True)
    period_mode = st.radio(
        "Register period",
        ["Single day", "Date range"],
        horizontal=True,
        key=f"{key_prefix}_period_mode",
        help="Single day prints one day's register; Date range uses From–To.",
    )
    if period_mode.startswith("Single"):
        day = st.date_input("Date", value=date.today(), key=f"{key_prefix}_day")
        df, dt = day, day
        tt = st.selectbox(
            "Type",
            ["All"] + list(db.PARTY_TRANSFER_TYPES.keys()),
            format_func=lambda x: "All types" if x == "All" else db.PARTY_TRANSFER_TYPES[x],
            key=f"{key_prefix}_type",
        )
        period_lbl = str(day)
    else:
        c1, c2, c3 = st.columns(3)
        df = c1.date_input("From", value=date.today().replace(day=1), key=f"{key_prefix}_df")
        dt = c2.date_input("To", value=date.today(), key=f"{key_prefix}_dt")
        tt = c3.selectbox(
            "Type",
            ["All"] + list(db.PARTY_TRANSFER_TYPES.keys()),
            format_func=lambda x: "All types" if x == "All" else db.PARTY_TRANSFER_TYPES[x],
            key=f"{key_prefix}_type",
        )
        period_lbl = f"{df} to {dt}"
    st.markdown("</div>", unsafe_allow_html=True)

    result = db.search_party_transfers(
        from_date=str(df), to_date=str(dt), page_size=100, export_all=True,
    )
    rows = result.get("items") or []
    if tt != "All":
        rows = [r for r in rows if r["transfer_type"] == tt]
    if rows:
        total_amt = float(sum(float(r.get("amount") or 0) for r in rows))
        k1, k2 = st.columns(2)
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Transfers</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total amount</p>"
            f"<p class='txn-kpi-val'>{fmt_money(total_amt)}</p></div>",
            unsafe_allow_html=True,
        )
        ths = "".join(
            f"<th>{h}</th>"
            for h in ("Document", "Date / Time", "Type", "From", "To", "Amount", "Description")
        )
        body = []
        for r in rows:
            typ = db.PARTY_TRANSFER_TYPES.get(r["transfer_type"], r["transfer_type"])
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('document_no') or ''))}</td>"
                f"<td>{escape(fmt_datetime_from_record(r, 'txn_date'))}</td>"
                f"<td><span class='inv-badge inv-badge-draft'>{escape(str(typ))}</span></td>"
                f"<td>{escape(str(r.get('from_party_name') or ''))}</td>"
                f"<td>{escape(str(r.get('to_party_name') or ''))}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('amount')))}</td>"
                f"<td>{escape(str(r.get('description') or ''))}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Showing {len(rows)} of {result.get('total', len(rows))} record(s)")

        reg_df = pd.DataFrame([{
            "Document": r["document_no"],
            "Date / Time": fmt_datetime_from_record(r, "txn_date"),
            "Type": db.PARTY_TRANSFER_TYPES.get(r["transfer_type"], r["transfer_type"]),
            "From": r.get("from_party_name", ""),
            "To": r.get("to_party_name", ""),
            "Amount": round(float(r.get("amount") or 0), 2),
            "Description": r.get("description", ""),
        } for r in rows])
        filters = {}
        if tt != "All":
            filters["Type"] = db.PARTY_TRANSFER_TYPES.get(tt, tt)
        st.markdown("##### Print register")
        st.caption("Print or export the register for the selected day / date range above.")
        report_toolbar(
            reg_df,
            "Party Transfer Register",
            f"party_transfer_register_{df}_{dt}",
            period=period_lbl,
            filters=filters or None,
            summary={"Entries": len(rows), "Total Amount": total_amt},
            key_prefix=f"{key_prefix}_reg_print",
            layout="landscape",
        )

        st.divider()
        st.markdown("##### Print voucher")
        labels = {
            str(r["id"]): (
                f"{r['document_no']} — {db.PARTY_TRANSFER_TYPES.get(r['transfer_type'], r['transfer_type'])} — "
                f"{fmt_datetime_from_record(r, 'txn_date')} — {fmt_money(r['amount'])}"
            )
            for r in rows
        }
        sel = st.selectbox("Select voucher", list(labels.keys()), format_func=lambda k: labels[k], key=f"{key_prefix}_sel")
        if sel:
            document_print_toolbar("Party Transfer", int(sel), key_prefix=f"{key_prefix}_print")
    else:
        st.info("No party transfers found for this period.")


def _party_transfer_form():
    fid = "party_xfer"
    wk = lambda n: ff.widget_key(fid, n)
    with form_compact("pt_new"):
        r1, r2 = st.columns([2.2, 1.2])
        tt = r1.selectbox(
            "Transfer Type *",
            list(db.PARTY_TRANSFER_TYPES.keys()),
            format_func=lambda k: db.PARTY_TRANSFER_TYPES[k],
            key=wk("type"),
        )
        tdate = r2.date_input("Date *", value=date.today(), key=wk("date"))
        r3, r4, r5 = st.columns([1.2, 2.2, 1.6])
        with r3:
            amt = money_input("Amount *", value=0.01, min_value=0.01, key=wk("amt"))
        desc = r4.text_input("Description", key=wk("desc"))
        ref = r5.text_input("Reference", key=wk("ref"))

        cust_opts = _customer_opts()
        sup_opts = _supplier_opts()

        from_type = to_type = None
        if tt == "customer_to_customer":
            if len(cust_opts) < 2:
                st.warning("Need at least two customers.")
                return
            from_type = to_type = "customer"
            c1, c2 = st.columns(2)
            from_id = cust_opts[c1.selectbox("From Customer *", list(cust_opts.keys()), key=wk("fc"))]
            to_id = cust_opts[c2.selectbox("To Customer *", list(cust_opts.keys()), key=wk("tc"))]
        elif tt == "supplier_to_supplier":
            if len(sup_opts) < 2:
                st.warning("Need at least two suppliers.")
                return
            from_type = to_type = "supplier"
            c1, c2 = st.columns(2)
            from_id = sup_opts[c1.selectbox("From Supplier *", list(sup_opts.keys()), key=wk("fs"))]
            to_id = sup_opts[c2.selectbox("To Supplier *", list(sup_opts.keys()), key=wk("ts"))]
        elif tt == "customer_to_supplier":
            if not cust_opts or not sup_opts:
                st.warning("Need at least one customer and one supplier.")
                return
            from_type, to_type = "customer", "supplier"
            c1, c2 = st.columns(2)
            from_id = cust_opts[c1.selectbox("Customer (AR set-off) *", list(cust_opts.keys()), key=wk("cs"))]
            to_id = sup_opts[c2.selectbox("Supplier (AP set-off) *", list(sup_opts.keys()), key=wk("ss"))]

        if st.button("Post Party Transfer", type="primary", key="pt_post"):
            if from_type == to_type and from_id == to_id:
                st.error("From and To party must be different.")
                return
            try:
                res = db.record_party_transfer(
                    tt, from_type, from_id, to_type, to_id,
                    amt, str(tdate), ref, desc, user_id=uid(),
                )
                ff.finish_post_new_form(
                    fid,
                    f"Posted **{res['document_no']}** — sub-ledger updated.",
                    retain={
                        "last_pt_print": res,
                        "pt_slip_preset": preset_from_voucher("party_transfer", res["id"], res.get("document_no")),
                    },
                )
            except Exception as e:
                st.error(str(e))
    if st.session_state.get("last_pt_print"):
        res = st.session_state.pop("last_pt_print")
        document_print_toolbar("Party Transfer", res["id"], key_prefix="pt_new_print")
        st.caption("Attach signed slip in **Slips** tab (voucher pre-selected after search).")


def _party_transfer_edit_tab(key_prefix):
    """Edit or delete posted party transfer / general vouchers."""
    st.caption("Select any party transfer to change parties, amount, date — or delete it.")
    c1, c2 = st.columns(2)
    df = c1.date_input("From", value=date.today().replace(day=1), key=f"{key_prefix}_df")
    dt = c2.date_input("To", value=date.today(), key=f"{key_prefix}_dt")
    result = db.search_party_transfers(
        from_date=str(df), to_date=str(dt), page_size=100, export_all=True,
    )
    rows = result.get("items") or []
    if not rows:
        st.info("No party transfers in this period.")
        return

    labels = {
        int(r["id"]): (
            f"{r['document_no']} — {db.PARTY_TRANSFER_TYPES.get(r['transfer_type'], r['transfer_type'])} — "
            f"{fmt_datetime_from_record(r, 'txn_date')} — {fmt_money(r['amount'])}"
        )
        for r in rows
    }
    sel_id = st.selectbox(
        "Select voucher",
        list(labels.keys()),
        format_func=lambda i: labels.get(i, str(i)),
        key=f"{key_prefix}_sel",
    )
    t = db.get_party_transfer(sel_id)
    if not t:
        st.error("Voucher not found.")
        return

    st.info(f"**{t['document_no']}** · {db.PARTY_TRANSFER_TYPES.get(t['transfer_type'], t['transfer_type'])}")

    tt = st.selectbox(
        "Transfer Type *",
        list(db.PARTY_TRANSFER_TYPES.keys()),
        index=list(db.PARTY_TRANSFER_TYPES.keys()).index(t["transfer_type"])
        if t["transfer_type"] in db.PARTY_TRANSFER_TYPES else 0,
        format_func=lambda k: db.PARTY_TRANSFER_TYPES[k],
        key=f"{key_prefix}_type",
    )
    try:
        default_date = date.fromisoformat(str(t.get("transfer_date") or date.today())[:10])
    except ValueError:
        default_date = date.today()
    tdate = st.date_input("Date *", value=default_date, key=f"{key_prefix}_date")
    amt = money_input("Amount *", value=float(t.get("amount") or 0.01), min_value=0.01, key=f"{key_prefix}_amt")
    # Strip auto prefix from description for editing
    raw_desc = t.get("description") or ""
    if " — " in raw_desc:
        raw_desc = raw_desc.split(" — ", 1)[-1]
    desc = st.text_input("Description", value=raw_desc, key=f"{key_prefix}_desc")
    ref = st.text_input("Reference", value=t.get("reference_no") or "", key=f"{key_prefix}_ref")

    cust_opts = _customer_opts()
    sup_opts = _supplier_opts()
    cust_labels = list(cust_opts.keys())
    sup_labels = list(sup_opts.keys())

    def _party_index(opts, party_id):
        for i, (lbl, pid) in enumerate(opts.items()):
            if int(pid) == int(party_id):
                return i
        return 0

    from_type = to_type = None
    from_id = to_id = None
    if tt == "customer_to_customer":
        if len(cust_opts) < 2:
            st.warning("Need at least two customers.")
            return
        from_type = to_type = "customer"
        c1, c2 = st.columns(2)
        fi = _party_index(cust_opts, t["from_party_id"]) if t.get("from_party_type") == "customer" else 0
        ti = _party_index(cust_opts, t["to_party_id"]) if t.get("to_party_type") == "customer" else 0
        from_id = cust_opts[c1.selectbox("From Customer *", cust_labels, index=min(fi, len(cust_labels) - 1), key=f"{key_prefix}_fc")]
        to_id = cust_opts[c2.selectbox("To Customer *", cust_labels, index=min(ti, len(cust_labels) - 1), key=f"{key_prefix}_tc")]
    elif tt == "supplier_to_supplier":
        if len(sup_opts) < 2:
            st.warning("Need at least two suppliers.")
            return
        from_type = to_type = "supplier"
        c1, c2 = st.columns(2)
        fi = _party_index(sup_opts, t["from_party_id"]) if t.get("from_party_type") == "supplier" else 0
        ti = _party_index(sup_opts, t["to_party_id"]) if t.get("to_party_type") == "supplier" else 0
        from_id = sup_opts[c1.selectbox("From Supplier *", sup_labels, index=min(fi, len(sup_labels) - 1), key=f"{key_prefix}_fs")]
        to_id = sup_opts[c2.selectbox("To Supplier *", sup_labels, index=min(ti, len(sup_labels) - 1), key=f"{key_prefix}_ts")]
    else:
        if not cust_opts or not sup_opts:
            st.warning("Need at least one customer and one supplier.")
            return
        from_type, to_type = "customer", "supplier"
        c1, c2 = st.columns(2)
        cust_id = t["from_party_id"] if t.get("from_party_type") == "customer" else t.get("to_party_id")
        sup_id = t["from_party_id"] if t.get("from_party_type") == "supplier" else t.get("to_party_id")
        fi = _party_index(cust_opts, cust_id)
        ti = _party_index(sup_opts, sup_id)
        from_id = cust_opts[c1.selectbox("Customer (AR set-off) *", cust_labels, index=min(fi, len(cust_labels) - 1), key=f"{key_prefix}_cs")]
        to_id = sup_opts[c2.selectbox("Supplier (AP set-off) *", sup_labels, index=min(ti, len(sup_labels) - 1), key=f"{key_prefix}_ss")]

    b1, b2 = st.columns(2)
    if b1.button("Save changes", type="primary", key=f"{key_prefix}_save"):
        if from_type == to_type and from_id == to_id:
            st.error("From and To party must be different.")
        else:
            try:
                res = db.update_party_transfer(
                    sel_id, tt, from_type, from_id, to_type, to_id,
                    amt, str(tdate), ref, desc, user_id=uid(),
                )
                ff.action_done(f"Updated **{res['document_no']}**.")
            except Exception as e:
                st.error(str(e))
    if b2.button("Delete voucher", key=f"{key_prefix}_del"):
        try:
            doc = t.get("document_no")
            db.reverse_party_transfer(sel_id, uid(), reason="user delete")
            ff.action_done(f"Deleted **{doc}**.")
        except Exception as e:
            st.error(str(e))

    document_print_toolbar("Party Transfer", sel_id, key_prefix=f"{key_prefix}_print")


# ---------------------------------------------------------------------------
# Cash Advance — issue float to rider/driver, settle bills later
# ---------------------------------------------------------------------------

def page_cash_advance():
    from erp_ui.helpers import sticky_page_tabs

    std_page_header(
        "Cash Advance",
        subtitle="Issue shadow float → settle bills (Cash Book CP) or cash returned (GL only).",
        status="shadow",
        status_kind="shell",
    )
    aid = db.resolve_cash_advance_account_id()
    if not aid:
        st.error(
            "GL head **100193 — ADVANCE PAYMENT OTHERS** is missing. "
            "Create it under Assets in Chart of Accounts first."
        )
        return
    with db.get_connection() as conn:
        acc = conn.execute(
            "SELECT code, name FROM chart_of_accounts WHERE id=?", (aid,)
        ).fetchone()
    if acc:
        st.caption(
            f"Control account: **{acc['code']} — {acc['name']}** "
            "(riders / cash float). Employee advances use **100180 — ADVANCE PAYMENTS**."
        )

    open_res = db.search_cash_advances(open_only=True, page_size=200, export_all=False)
    open_items = open_res.get("items") or []
    open_amt = sum(float(r.get("outstanding_amount") or 0) for r in open_items)
    st.markdown(
        f'<div class="txn-status-strip">'
        f'<span class="erp-shell-badge erp-shell-badge-shadow">Shadow</span>&nbsp;'
        f'<strong>{len(open_items)}</strong> open · '
        f'<strong>{fmt_money(open_amt)}</strong> outstanding</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 1, 1])
    c1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Open advances</p>"
        f"<p class='txn-kpi-val'>{len(open_items)}</p></div>",
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Outstanding</p>"
        f"<p class='txn-kpi-val'>{fmt_money(open_amt)}</p></div>",
        unsafe_allow_html=True,
    )
    with c3:
        if open_items:
            st.markdown("<div style='height:0.55rem'></div>", unsafe_allow_html=True)
            if st.button("Settle outstanding", type="primary", key="ca_hdr_settle", use_container_width=True):
                st.session_state["ca_page_tab"] = "Settle Bills"
                st.rerun()
        else:
            st.markdown("<div style='height:0.55rem'></div>", unsafe_allow_html=True)
            if st.button("Issue Advance", type="primary", key="ca_hdr_issue", use_container_width=True):
                st.session_state["ca_page_tab"] = "Issue Advance"
                st.rerun()

    tab = sticky_page_tabs(
        ["Register", "Issue Advance", "Settle Bills"],
        "ca_page_tab",
    )
    if tab == "Register":
        _cash_advance_register("ca_reg")
    elif tab == "Issue Advance":
        _cash_advance_issue_form("ca_iss")
    else:
        _cash_advance_settle_form("ca_set")


def _cash_advance_register(key_prefix):
    from html import escape
    from erp_ui.invoice_status_ui import status_badge_html

    st.markdown('<div class="txn-filter-box">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2, 1.2, 1, 1])
    q = c1.text_input("Search", placeholder="CA no, person, purpose…", key=f"{key_prefix}_q")
    status = c2.selectbox(
        "Status",
        ["Open / Partial", "All", "open", "partial", "settled"],
        key=f"{key_prefix}_st",
    )
    fd = c3.date_input("From", value=None, key=f"{key_prefix}_fd")
    td = c4.date_input("To", value=None, key=f"{key_prefix}_td")
    st.markdown("</div>", unsafe_allow_html=True)
    open_only = status == "Open / Partial"
    st_filter = None if status in ("All", "Open / Partial") else status
    result = db.search_cash_advances(
        q=q or None,
        status=st_filter,
        open_only=open_only,
        from_date=str(fd) if fd else None,
        to_date=str(td) if td else None,
        page=1,
        page_size=100,
    )
    rows = result.get("items") or []
    if not rows:
        st.info("No cash advances found.")
        if st.button("Issue Advance", type="primary", key=f"{key_prefix}_empty_cta"):
            st.session_state["ca_page_tab"] = "Issue Advance"
            st.rerun()
        return
    ths = "".join(
        f"<th>{h}</th>"
        for h in (
            "Advance", "Date", "Person", "Purpose", "Issued", "Bills",
            "Cash back", "Outstanding", "Status", "Ref",
        )
    )
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('document_no') or ''))}</td>"
            f"<td>{escape(str(r.get('issue_date') or ''))}</td>"
            f"<td>{escape(str(r.get('person_name') or ''))}</td>"
            f"<td>{escape(str((r.get('purpose') or '')[:50]))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(r.get('amount')))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(r.get('settled_bills')))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(r.get('cash_returned')))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(r.get('outstanding_amount')))}</td>"
            f"<td class='txn-status-cell'>{status_badge_html(r.get('status'))}</td>"
            f"<td>{escape(str(r.get('issue_doc_no') or r.get('document_no') or ''))}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Showing {len(rows)} of {result.get('total', len(rows))} advance(s)")

    labels = {
        str(r["id"]): (
            f"{r['document_no']} — {r.get('person_name','')} — "
            f"out {fmt_money(r.get('outstanding_amount'))} — {(r.get('status') or '').title()}"
        )
        for r in rows
    }
    sel = st.selectbox(
        "View settlements", list(labels.keys()),
        format_func=lambda k: labels[k], key=f"{key_prefix}_view",
    )
    if not sel:
        return
    adv = db.get_cash_advance(int(sel))
    if not adv:
        return
    st.markdown(
        f"**{adv['document_no']}** · {adv.get('person_name')} · "
        f"issued {fmt_money(adv.get('amount'))} · outstanding **{fmt_money(adv.get('outstanding_amount'))}**"
    )
    settlements = adv.get("settlements") or []
    if not settlements:
        st.caption("No settlements yet.")
        if float(adv.get("outstanding_amount") or 0) > 0.01:
            if st.button("Settle this advance", type="primary", key=f"{key_prefix}_settle_cta"):
                st.session_state["ca_page_tab"] = "Settle Bills"
                st.session_state["ca_set_adv"] = str(adv["id"])
                st.rerun()
        return
    for s in settlements:
        with st.expander(
            f"{s['document_no']} · {s.get('settle_date')} · "
            f"bills {fmt_money(s.get('bills_total'))} · cash back {fmt_money(s.get('cash_returned'))}",
            expanded=False,
        ):
            lines = s.get("lines") or []
            if lines:
                from erp_ui.helpers import render_dataframe_html_table
                render_dataframe_html_table(pd.DataFrame([{
                    "Account": f"{ln.get('expense_code')} — {ln.get('expense_name')}",
                    "Narration": ln.get("narration") or "",
                    "Amount": ln.get("amount"),
                } for ln in lines]))
            if s.get("cash_doc_no"):
                st.caption(f"Cash payment voucher: **{s['cash_doc_no']}**")


def _cash_advance_issue_form(key_prefix):
    fid = key_prefix
    wk = lambda n: ff.widget_key(fid, n)
    with form_compact(f"{key_prefix}_issue"):
        c1, c2, c3 = st.columns([1.2, 1.6, 1.4])
        idate = c1.date_input("Issue date *", value=date.today(), key=wk("date"))
        person = c2.text_input(
            "Paid to (rider / driver) *",
            key=wk("person"),
            placeholder="e.g. Raza, Asad, Driver Imran",
        )
        with c3:
            amt = money_input("Amount *", value=0.0, min_value=0.0, key=wk("amt"))
        purpose = st.text_input(
            "Purpose / trip note",
            key=wk("purpose"),
            placeholder="e.g. Lahore trip, Bilty collection, fuel float",
        )
        c4, c5 = st.columns([1.2, 2])
        mode = c4.radio("Mode", ["Cash", "Bank"], horizontal=True, key=wk("mode"))
        ref = c5.text_input("Reference", key=wk("ref"))
        bank_id = None
        if mode == "Bank":
            bank_opts = _bank_account_opts()
            if not bank_opts:
                st.error("No bank accounts found.")
                return
            bank_id = bank_opts[st.selectbox("Bank account *", list(bank_opts.keys()), key=wk("bank"))]

    if mode == "Cash" and db.is_cash_day_closed(str(idate)):
        st.caption(
            f"Cash book for **{idate}** is closed — issue advance is still allowed "
            f"(shadow entry only; Cash Book posts when bills are settled)."
        )

    if st.button("Issue Advance", type="primary", key=f"{key_prefix}_post"):
        if not (person or "").strip() or amt <= 0:
            st.error("Person name and amount are required.")
            return
        try:
            res = db.issue_cash_advance(
                str(idate), amt, person,
                purpose=purpose,
                reference_no=ref,
                payment_mode=mode.lower(),
                bank_account_id=bank_id,
                user_id=uid(),
            )
            ff.finish_post_new_form(
                fid,
                f"Issued **{res['document_no']}** to **{res['person_name']}** — "
                f"{fmt_money(res['amount'])} (shadow — not in Cash Book). "
                f"Settle bills later from the **Settle Bills** tab.",
            )
        except Exception as e:
            st.error(str(e))


def _cash_advance_settle_form(key_prefix):
    open_res = db.search_cash_advances(open_only=True, page_size=200)
    opens = open_res.get("items") or []
    if not opens:
        st.info("No open advances to settle. Issue an advance first.")
        if st.button("Issue Advance", type="primary", key=f"{key_prefix}_empty_iss"):
            st.session_state["ca_page_tab"] = "Issue Advance"
            st.rerun()
        return

    opts = {
        str(r["id"]): (
            f"{r['document_no']} — {r.get('person_name')} — "
            f"out {fmt_money(r.get('outstanding_amount'))} "
            f"(issued {fmt_money(r.get('amount'))} on {r.get('issue_date')})"
        )
        for r in opens
    }
    sel = st.selectbox(
        "Open advance *", list(opts.keys()),
        format_func=lambda k: opts[k], key=f"{key_prefix}_adv",
    )
    adv = db.get_cash_advance(int(sel)) if sel else None
    if not adv:
        return
    outstanding = float(adv.get("outstanding_amount") or 0)
    from html import escape as _esc
    st.markdown(
        f'<div class="txn-status-strip">'
        f'<span class="erp-shell-badge erp-shell-badge-shadow">Outstanding</span>&nbsp;'
        f'<strong>{_esc(str(adv.get("document_no") or ""))}</strong> · '
        f'{_esc(str(adv.get("person_name") or ""))} · '
        f'<strong>{fmt_money(outstanding)}</strong></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Purpose: {adv.get('purpose') or '—'} · Issued {fmt_money(adv.get('amount'))} on {adv.get('issue_date')}")

    gl_rows = _cash_advance_settle_account_rows(adv.get("advance_account_id"))
    if not gl_rows:
        st.warning("Add GL accounts in Chart of Accounts first.")
        return

    sk = f"{key_prefix}_lines"
    if sk not in st.session_state:
        st.session_state[sk] = [
            {"expense_account_id": int(gl_rows[0]["id"]), "narration": "", "amount": 0.0},
        ]

    fid = key_prefix
    wk = lambda n: ff.widget_key(fid, n)
    with form_compact(f"{key_prefix}_settle"):
        c1, c2 = st.columns([1.2, 2])
        sdate = c1.date_input("Settle date *", value=date.today(), key=wk("date"))
        note = c2.text_input(
            "Settlement note",
            key=wk("note"),
            placeholder="Optional — e.g. bills collected on return",
        )
        st.markdown(
            "**Settlement lines** — expense bills or GL adjustments "
            "(fuel, inventory, clearing, etc.). Each line **debits the GL account** and "
            "**credits Cash** — a **CP voucher** is posted to the Cash Book."
        )
        lines = st.session_state[sk]
        for i, ln in enumerate(lines):
            with form_line(f"{key_prefix}_el{i}"):
                cols = st.columns([2.6, 2.8, 1.15, 0.4])
                cur_id = ln.get("expense_account_id")
                with cols[0]:
                    _lbl, acct_id, _rec = smart_select(
                        "GL account",
                        gl_rows,
                        key=f"{key_prefix}_ea_{i}",
                        placeholder="Type code or name — expense, clearing, liability…",
                        max_results=80,
                        default_id=cur_id,
                        layout="stack",
                    )
                lines[i]["expense_account_id"] = acct_id or cur_id
                lines[i]["narration"] = cols[1].text_input(
                    "Narration", value=ln.get("narration") or "",
                    key=f"{key_prefix}_en_{i}",
                    placeholder="e.g. Fuel bilty 4311, P&L clearing, customer adj.",
                )
                with cols[2]:
                    lines[i]["amount"] = money_input(
                        "Amount", value=float(ln.get("amount") or 0),
                        min_value=0.0, key=f"{key_prefix}_em_{i}",
                    )
                if cols[3].button("✕", key=f"{key_prefix}_ex_{i}", help="Remove line") and len(lines) > 1:
                    lines.pop(i)
                    st.rerun()

        bills_total = sum(float(l.get("amount") or 0) for l in lines)
        with st.columns([1.2, 2])[0]:
            cash_back = money_input(
                "Cash returned",
                value=0.0,
                min_value=0.0,
                key=wk("cashback"),
                help="Leftover cash returned — reduces advance only (GL Dr Cash / Cr Advance, not in Cash Book).",
            )
        cleared = bills_total + float(cash_back or 0)
        rem = outstanding - cleared
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Lines total", fmt_money(bills_total))
        m2.metric("Cash returned", fmt_money(cash_back))
        m3.metric("Clearing", fmt_money(cleared))
        m4.metric("Left after settle", fmt_money(max(0, rem)))

        pay_mode = (adv.get("payment_mode") or "cash").lower()
        cash_day_blocked = (
            bills_total > 0.005
            and pay_mode == "cash"
            and db.is_cash_day_closed(str(sdate))
        )
        if cash_day_blocked:
            st.warning(
                f"Cash book for **{sdate}** is closed — bill lines post a CP voucher. "
                f"Choose another settle date, reopen the day, or use **cash returned** only "
                f"(GL, no Cash Book)."
            )

        b1, b2, b3 = st.columns(3)
        if b1.button("Add line", key=f"{key_prefix}_add"):
            lines.append({
                "expense_account_id": int(gl_rows[0]["id"]),
                "narration": "",
                "amount": 0.0,
            })
            st.rerun()
        if b2.button("Clear lines", key=f"{key_prefix}_clr"):
            st.session_state[sk] = [
                {"expense_account_id": int(gl_rows[0]["id"]), "narration": "", "amount": 0.0},
            ]
            st.rerun()

        can_post = cleared > 0 and cleared <= outstanding + 0.01 and not cash_day_blocked
        if rem < -0.01:
            st.error("Settlement lines + cash return exceed outstanding advance.")
        if b3.button("Post Settlement", type="primary", key=f"{key_prefix}_post", disabled=not can_post):
            try:
                active_lines = [l for l in lines if float(l.get("amount") or 0) > 0]
                res = db.settle_cash_advance(
                    int(sel),
                    str(sdate),
                    active_lines,
                    cash_returned=float(cash_back or 0),
                    description=note,
                    user_id=uid(),
                )
                del st.session_state[sk]
                msg = (
                    f"Settled **{res['advance_no']}** as **{res['document_no']}** — "
                    f"bills {fmt_money(res['bills_total'])}, "
                    f"cash return {fmt_money(res['cash_returned'])}."
                )
                if res.get("cash_doc_no"):
                    docs = res.get("cash_doc_nos") or [res["cash_doc_no"]]
                    msg += f" Cash payment(s): **{', '.join(docs)}**."
                if res.get("status") == "settled":
                    msg += " Advance is **fully cleared**."
                else:
                    msg += f" Still outstanding **{fmt_money(res.get('outstanding_amount'))}**."
                ff.finish_post_new_form(fid, msg)
            except Exception as e:
                st.error(str(e))
