"""Chart of Accounts — structure, posting links, and control-account reconciliation."""

from datetime import date
import pandas as pd
import streamlit as st
from application import data_gateway as db
from erp_ui.helpers import uid, std_page_header, fmt_money, money_input
from erp_ui import form_flow as ff


def _export_df(df, name, title=None):
    if df is not None and not df.empty:
        from erp_ui.report_print import report_toolbar
        from erp_ui.report_profiles import report_layout
        lbl = title or name.replace("_", " ").title()
        report_toolbar(df, lbl, name, key_prefix=f"coa_{name}", layout=report_layout(lbl))


def page_chart_of_accounts():
    from erp_ui.helpers import sticky_page_tabs
    from html import escape

    peek = st.session_state.get("coa_page_tab") or "Accounts"
    std_page_header(
        "Chart of Accounts",
        status="register" if peek == "Accounts" else "posted",
        status_kind="shell",
    )
    tab = sticky_page_tabs(
        ["Accounts", "Posting Setup", "Reconciliation", "How It Links"],
        "coa_page_tab",
    )

    def _render_coa_table(acct_rows):
        ths = "".join(f"<th>{h}</th>" for h in ("Code", "Name", "Opening", "GL Balance", "Active"))
        body = []
        for r in acct_rows:
            active = bool(r.get("is_active"))
            badge = (
                '<span class="inv-badge inv-badge-approved">Active</span>'
                if active
                else '<span class="inv-badge inv-badge-cancelled">Inactive</span>'
            )
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('code') or ''))}</td>"
                f"<td>{escape(str(r.get('name') or ''))}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('opening_balance')))}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('balance')))}</td>"
                f"<td class='txn-status-cell'>{badge}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )

    if tab == "Accounts":
        rows = db.get_accounts()
        if not rows:
            st.info("No accounts defined.")
        else:
            by_type = {}
            for r in rows:
                by_type.setdefault(r.get("account_type", "other"), []).append(r)
            st.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>GL Accounts</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            for gtype in ("asset", "liability", "equity", "income", "expense"):
                if gtype not in by_type:
                    continue
                st.markdown(f"##### {gtype.replace('_', ' ').title()}")
                _render_coa_table(by_type[gtype])
            _export_df(pd.DataFrame(rows), "chart_of_accounts", "Chart of Accounts")

        st.divider()
        st.markdown("**Add / edit accounts**")
        sub = sticky_page_tabs(["Add Account", "Edit Account"], "coa_sub_tab")
        if sub == "Add Account":
            parent_opts = {"— None —": None}
            parent_opts.update({f"{p['code']} - {p['name']}": p["id"] for p in db.get_accounts()})
            with st.form("coa_add"):
                code = st.text_input("Code", value=db.next_code("ACC", "accounts"))
                name = st.text_input("Name *")
                atype = st.selectbox("Account Type", ["asset", "liability", "equity", "income", "expense"])
                parent = st.selectbox("Parent Account", list(parent_opts.keys()))
                opening = money_input("Opening Balance", value=0.0, key="coa_add_ob")
                if st.form_submit_button("Save Account", type="primary"):
                    if not name:
                        st.error("Name is required.")
                    else:
                        db.add_account({
                            "code": code, "name": name, "account_type": atype,
                            "parent_id": parent_opts[parent], "opening_balance": opening,
                        })
                        ff.finish_new_entry(form_id="coa_add", message="Account added.")
        elif sub == "Edit Account":
            accts = db.get_accounts()
            if not accts:
                st.info("No accounts.")
            else:
                opts = {f"{r['code']} - {r['name']}": r["id"] for r in accts}
                aid = opts[st.selectbox("Account", list(opts.keys()), key="coa_edit_sel")]
                acc = db.get_account(aid)
                parent_opts = {"— None —": None}
                parent_opts.update({f"{p['code']} - {p['name']}": p["id"] for p in accts if p["id"] != aid})
                cur_parent = next((k for k, v in parent_opts.items() if v == acc.get("parent_id")), "— None —")
                with st.form("coa_edit"):
                    code = st.text_input("Code", value=acc["code"])
                    name = st.text_input("Name", value=acc["name"])
                    atype = st.selectbox(
                        "Type", ["asset", "liability", "equity", "income", "expense"],
                        index=["asset", "liability", "equity", "income", "expense"].index(acc["account_type"]),
                    )
                    parent = st.selectbox("Parent", list(parent_opts.keys()), index=list(parent_opts.keys()).index(cur_parent))
                    opening = money_input(
                        "Opening Balance",
                        value=float(acc.get("opening_balance") or 0),
                        key="coa_edit_ob",
                    )
                    active = st.checkbox("Active", value=bool(acc.get("is_active")))
                    c1, c2 = st.columns(2)
                    upd = c1.form_submit_button("Update")
                    dele = c2.form_submit_button("Delete")
                    if upd:
                        db.update_account(aid, {
                            "code": code, "name": name, "account_type": atype,
                            "parent_id": parent_opts[parent], "opening_balance": opening,
                            "is_active": int(active),
                        })
                        ff.action_done("Updated.")
                    if dele:
                        db.delete_account(aid)
                        ff.action_done("Deleted.")

    elif tab == "Posting Setup":
        st.markdown(
            "Each **posting role** below is the GL account used when the system auto-posts "
            "sales, purchases, receipts, production, etc. Change a link to use a different COA code."
        )
        setup = db.get_posting_setup()
        acct_opts = {f"{a['code']} - {a['name']}": a["code"] for a in db.get_accounts(active_only=True)}
        for row in setup:
            c1, c2 = st.columns([2, 2])
            c1.markdown(f"**{row['label']}**")
            c1.caption(row["hint"])
            cur = f"{row['account_code']} - {row['account_name']}"
            keys = list(acct_opts.keys())
            default_ix = next((i for i, k in enumerate(keys) if k.startswith(row["account_code"])), 0)
            pick = c2.selectbox(
                "GL Account", keys, index=default_ix, key=f"post_role_{row['role']}", label_visibility="collapsed",
            )
            if c2.button("Save link", key=f"save_role_{row['role']}"):
                try:
                    db.save_posting_role(row["role"], acct_opts[pick], uid())
                    ff.action_done(f"Linked **{row['label']}** → `{acct_opts[pick]}`")
                except Exception as e:
                    st.error(str(e))
        st.divider()
        if st.button("Reset all links to system defaults"):
            for row in setup:
                db.save_posting_role(row["role"], "", uid())
            ff.action_done("Posting links reset to defaults.")

    elif tab == "Reconciliation":
        st.markdown("Control accounts in GL should match the total of party sub-ledgers.")
        rec = db.get_control_account_reconciliation()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"Customers → GL {rec['ar_code']}")
            st.metric("AR control (GL)", fmt_money(rec["ar_gl_balance"]))
            st.metric("Customer sub-ledger total", fmt_money(rec["ar_subledger_total"]))
            diff = rec["ar_difference"]
            st.metric("Difference", fmt_money(diff), delta=None if abs(diff) < 0.01 else f"{diff:,.2f}")
            if abs(diff) >= 0.01:
                st.warning("Mismatch — check unposted invoices, manual cash book entries, or opening balances.")
        with c2:
            st.subheader(f"Suppliers → GL {rec['ap_code']}")
            st.metric("AP control (GL)", fmt_money(rec["ap_gl_balance"]))
            st.metric("Supplier sub-ledger total", fmt_money(rec["ap_subledger_total"]))
            diff = rec["ap_difference"]
            st.metric("Difference", fmt_money(diff))
            if abs(diff) >= 0.01:
                st.warning("Mismatch — check unposted purchases or payments not through Supplier Payment.")

        st.divider()
        st.subheader("Year-End Closing")
        st.info(
            "Use **Finance → Fiscal Year Closing** for the full workflow: pre-close checklist, "
            "P&L transfer to retained earnings, period lock, and audit log."
        )
        active = db.get_active_fiscal_year()
        if active:
            st.caption(f"Active FY: **{active['fy_code']}** ({active['start_date']} → {active['end_date']})")
        pl_preview = db.get_profit_loss(
            str(date(date.today().year, 1, 1)), str(date.today()),
        )
        st.metric("Net P/L (calendar YTD preview)", fmt_money(pl_preview["net_profit"]))

    elif tab == "How It Links":
        st.markdown("""
### How customers & suppliers link to Chart of Accounts

This ERP uses a **control account** pattern (standard in accounting software):

| Party | Sub-ledger (detail) | Control GL account | COA code (default) |
|-------|---------------------|--------------------|--------------------|
| **Customers** | Finance → **Customer Ledger** (per customer) | **Accounts Receivable** | `1200` |
| **Suppliers** | Finance → **Supplier Ledger** (per supplier) | **Accounts Payable** | `2000` |

- Each **customer does NOT get their own GL account code** — all post to **1200 AR**.
- Each **supplier does NOT get their own GL code** — all post to **2000 AP**.
- **Customer Ledger** / **Supplier Ledger** hold the **party-wise detail** (who owes what).
- **General Ledger** on account `1200` / `2000` holds the **financial total**.

### What posts where (automatic)

| Transaction | Sub-ledger | Income / Expense GL | Cash/Bank GL |
|-------------|------------|---------------------|--------------|
| Approve **sale invoice** | Customer balance ↑ | **4000 Sales** (credit) | **1000 Cash** if paid on invoice |
| **Customer receipt** | Customer balance ↓ | — | **1000 Cash** or **1100 Bank** (debit) + **1200 AR** (credit) |
| Approve **purchase invoice** | Supplier balance ↑ | **1310 Raw Inv** / inventory | **1000 Cash** if paid |
| **Supplier payment** | Supplier balance ↓ | — | **1000/1100** (credit) + **2000 AP** (debit) |
| **Production** | Stock only | **1340 WIP**, **1330 FG**, **5000 COGS** | — |
| **Journal voucher** | — | Any income/expense account you pick | Any asset account |
| **Cash Book → Post Voucher** (generic) | **Not linked** to parties | **Not posted to GL** unless you use JV | Cash book only |

### Income & expense accounts

- **Income** (type `income`): e.g. **4000 Sales Revenue** — credited on approved sales.
- **Expense** (type `expense`): e.g. **5000 COGS**, **5200 Labour**, **6100 Admin** — debited on purchases, production, or journal vouchers.
- Add more accounts under **Accounts** tab (e.g. `6101 Electricity`, `6102 Salaries`) and link via **Journal Voucher** or future expense payment screen.

### Why Balance Sheet may look odd

- **Liabilities** now display as **positive** when you owe money (AP credit balance).
- **Equity** increases when you run **Finance → Fiscal Year Closing** (P&L transfer to retained earnings).
- **Cash GL (1000)** can differ from **Cash Book** if you post generic cash vouchers without GL — use **Customer Receipt** / **Supplier Payment** for party-linked cash.
        """)
