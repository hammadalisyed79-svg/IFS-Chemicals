"""IFS Industrial ERP — desktop application."""

import pandas as pd
import streamlit as st
from datetime import date
from pathlib import Path

import importlib
import sys

# Ensure project root is importable (Streamlit cwd can differ)
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Login screen branding (internal ERP entry — not distributor portal)
LOGIN_BRAND_TITLE = "IFS chemicals ERP"
LOGIN_BRAND_SUBTITLE = "Internal use only"
LOGIN_BRAND_CREDIT = "Development by Hammad Syed"


from application import data_gateway as db
from erp_ui import v3_pages as v3
from erp_ui import hr_pages as hr
from erp_ui import finance_pages as fin
from erp_ui import coa_pages as coa
from erp_ui import fiscal_pages as fiscal
from erp_ui import production_pages as prod
from erp_ui import stock_reval_pages as srv
from erp_ui import download_pages as dl
from erp_ui import job_card_pages as jc
from erp_ui import attendance_simple as att
from erp_ui import weighbridge_pages as wb
from erp_ui import gatepass_pages as gp
from erp_ui import approval_inbox as appr_inbox
from erp_ui import invoice_workflow_pages as iwf
from erp_ui import reports_pages as reports
from erp_ui import audit_pages as audit
from erp_ui import holiday_pages as hol
from erp_ui import groups_pages as mgrp
from erp_ui import draft_center
from erp_ui import health_check as erp_health
from erp_ui import approval_designer as appr_des
from erp_ui import portal_pages
from erp_ui import mobile_approvals
from erp_ui import price_list_pages
from erp_ui import distributor_admin
from erp_ui import distribution_pages
from erp_ui import helpers as hlp
from erp_ui import dashboard_pages as dash
from erp_ui import transaction_list as txn
from erp_ui import form_flow as ff
from erp_ui import industrial_pages as ind
from erp_ui import dispatch_planning as dsp
from erp_ui import sales_pages as sales_pg
from erp_ui import purchase_pages as purch_pg
from erp_ui import master_pages as master_pg
from erp_ui import inventory_pages as inv_pg
from erp_ui import return_pages as ret_pg
from erp_ui import plant_shift_dashboard as plant_shift
from erp_ui.nav import (
    apply_pending_nav,
    filtered_nav_groups,
    render_main_breadcrumb,
    sync_nav_state,
)
from erp_ui.layout_styles import inject_layout_styles








# ---------------------------------------------------------------------------
# Page config & styling
# ---------------------------------------------------------------------------
def _early_portal_sidebar() -> bool:
    """Distributor portal needs the left menu open by default."""
    try:
        if st.query_params.get("portal") == "1":
            return True
        u = st.session_state.get("user") if "user" in st.session_state else None
        if u and str(u.get("user_type") or "").lower().startswith("distributor"):
            return True
        if st.session_state.get("portal_mode"):
            return True
    except Exception:
        pass
    return False


try:
    st.set_page_config(
        page_title=LOGIN_BRAND_TITLE,
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded" if _early_portal_sidebar() else "collapsed",
    )
except Exception:
    # Already configured (e.g. health check importing app while main script is running)
    pass


inject_layout_styles()

db.init_db()

# Restore / re-validate login every run (one active session per user).
if "user" not in st.session_state:
    st.session_state.user = None
from erp_ui.auth_session import restore_session, enforce_active_session
if st.session_state.user:
    enforce_active_session()
else:
    restore_session()

# Professional action prompts (save / update / delete) queued across st.rerun()
ff.render_flash()

# Navigation & permissions: erp_ui/nav.py (shared with dashboard — avoids circular import)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def require_login():
    if "user" not in st.session_state:
        st.session_state.user = None
    from erp_ui.auth_session import restore_session, enforce_active_session
    if st.session_state.user:
        enforce_active_session()
    else:
        restore_session()


def fmt_money(val):
    return f"Rs. {float(val or 0):,.2f}"


def uid():
    u = st.session_state.get("user")
    return u["id"] if u else None


def export_df(df, name, title=None, period="", filters=None, summary=None):
    if df is None or df.empty:
        return
    from erp_ui.report_print import report_toolbar
    from erp_ui.report_profiles import report_layout, _report_profile_key
    lbl = title or name.replace("_", " ").title()
    # Prefer catalog key so column profiles / ledger layout resolve correctly
    layout_key = _report_profile_key(lbl) or lbl
    report_toolbar(
        df, lbl, name,
        period=period or "",
        filters=filters,
        summary=summary,
        key_prefix=f"ex_{name}",
        layout=report_layout(layout_key),
    )


def _attach_ledger_party(df, party, kind):
    """Store party block for professional ledger print."""
    if df is None:
        return df
    try:
        p = party or {}
        df.attrs["ledger_party"] = {
            "id": p.get("id"),
            "customer_id": p.get("id") if kind == "customer" else None,
            "supplier_id": p.get("id") if kind == "supplier" else None,
            "code": p.get("code") or "",
            "name": p.get("name") or "",
            "phone": p.get("phone") or "",
            "mobile": p.get("mobile") or "",
            "dispatch_phone": p.get("dispatch_phone") or "",
            "accounts_phone": p.get("accounts_phone") or "",
            "owner_phone": p.get("owner_phone") or "",
            "contact_person": p.get("contact_person") or "",
            "address": p.get("address") or p.get("city") or "",
            "kind": kind,
        }
        if p.get("ledger_summary"):
            df.attrs["ledger_summary"] = party["ledger_summary"]
    except Exception:
        pass
    return df


def customer_options(active_only=True):
    rows = db.get_customers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def supplier_options(active_only=True):
    rows = db.get_suppliers(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def item_options(active_only=True):
    rows = sorted(
        db.get_items(active_only=active_only),
        key=lambda r: hlp.natural_code_sort_key(r.get("code")),
    )
    return {f"{r['code']} - {r['name']} ({r['stock_qty']} {r['unit']})": r for r in rows}


def account_options(active_only=True):
    rows = db.get_accounts(active_only=active_only)
    return {f"{r['code']} - {r['name']}": r["id"] for r in rows}


def bank_account_options():
    rows = db.get_accounts_by_type("asset")
    bank = [r for r in rows if "bank" in r["name"].lower()]
    if not bank:
        bank = rows
    return {f"{r['code']} - {r['name']}": r["id"] for r in bank}


def line_item_editor(items_dict, key_prefix, default_lines=None):
    """Searchable line-item grid — delegates to smart_line_item_editor."""
    return hlp.smart_line_item_editor(items_dict, key_prefix, default_lines)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def page_login():
    from erp_ui.auth_session import bootstrap_session_from_client
    from erp_ui.mobile_layout import is_mobile_client, mobile_login_shell

    bootstrap_session_from_client()

    mobile = is_mobile_client()

    if mobile:
        st.markdown(
            mobile_login_shell(LOGIN_BRAND_TITLE, LOGIN_BRAND_SUBTITLE),
            unsafe_allow_html=True,
        )
        _render_login_form()
        st.markdown(
            f'</div><p class="erp-mobile-login-caption">{LOGIN_BRAND_CREDIT}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        login_html = (
            '<div style="text-align:center;padding:1.5rem 0 0.5rem;">'
            f'<p style="font-size:2rem;font-weight:700;color:#1D4ED8;margin:0;">{LOGIN_BRAND_TITLE}</p>'
            f'<p style="color:#334155;margin:0.3rem 0 0.5rem;font-weight:600;">{LOGIN_BRAND_SUBTITLE}</p>'
            f'<p style="color:#64748B;margin:0 0 1.25rem;font-size:0.85rem;">{LOGIN_BRAND_CREDIT}</p></div>'
        )
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            st.markdown(login_html, unsafe_allow_html=True)
            _render_login_form()


def _render_login_form():
    from erp_core.v15_security import client_context
    from erp_ui.auth_session import pop_session_ended_message

    ended = pop_session_ended_message()
    if ended:
        st.warning(ended)

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
        if submitted:
            ip, ua = client_context()
            user = db.authenticate(username, password, ip=ip, user_agent=ua)
            if user and user.get("_error"):
                st.error(user["_error"])
                if "locked" in user["_error"].lower():
                    st.info(
                        "Too many failed attempts triggered lockout. "
                        "Run **`reset_admin_password.bat`** (resets password and unlocks) "
                        "or **`unlock_admin.bat`** (unlock only) from the install folder."
                    )
            elif user:
                from erp_ui.auth_session import create_and_persist_session
                from erp_core.v15_security import is_portal_user
                create_and_persist_session(user)
                if is_portal_user(user):
                    st.session_state.nav_group = "Portal"
                    st.session_state.nav_screen = "Portal"
                else:
                    st.session_state.nav_group = "Overview"
                    st.session_state.nav_screen = "Dashboard"
                st.session_state.pop("launcher_group", None)
                st.rerun()
            else:
                st.error("Invalid username or password.")
                if (username or "").strip().lower() == "admin":
                    st.info(
                        "Default password **admin123** was removed in V17.3. "
                        "Run **`reset_admin_password.bat`** in the install folder, "
                        "then open **`ADMIN_BOOTSTRAP.txt`** for your new credentials."
                    )

    from erp_deploy import PUBLIC_URL_HTTPS, PUBLIC_URL_IP_HTTP
    st.caption(
        f"Secure access: [{PUBLIC_URL_HTTPS}/]({PUBLIC_URL_HTTPS}/) · "
        f"IP fallback: [{PUBLIC_URL_IP_HTTP}/]({PUBLIC_URL_IP_HTTP}/) · "
        "One login per user — signing in elsewhere signs out this device."
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def page_dashboard():
    dash.page_admin_dashboard()


def page_business_overview():
    dash.page_business_overview()


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
def page_customers():
    from erp_ui.master_pages import page_customers as _page
    return _page()



# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
def page_suppliers():
    from erp_ui.master_pages import page_suppliers as _page
    return _page()



# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
def page_items():
    from erp_ui.master_pages import page_items as _page
    return _page()



# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
def page_inventory():
    from erp_ui.inventory_pages import page_inventory as _page
    return _page()



# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------
def page_purchases():
    from erp_ui.purchase_pages import page_purchases as _page
    return _page()

def page_sales():
    from erp_ui.sales_pages import page_sales as _page
    return _page()

def page_purchase_return():
    from erp_ui.return_pages import page_purchase_return as _page
    return _page()



# ---------------------------------------------------------------------------
# Sale Return
# ---------------------------------------------------------------------------
def page_sale_return():
    from erp_ui.return_pages import page_sale_return as _page
    return _page()



# ---------------------------------------------------------------------------
# Customer Ledger
# ---------------------------------------------------------------------------
def page_customer_ledger():
    from erp_ui.ledger_shared import render_party_ledger

    render_party_ledger(
        "customer",
        page_title="Customer Ledger",
        party_select_key="cl_cust",
        from_key="cl_from",
        to_key="cl_to",
        tab_state_key="cl_ledger_tab",
        split_books_key="cl_split_books",
        export_summary_name="customer_ledger",
        export_detailed_name="customer_ledger_detailed",
        export_summary_title="Customer Ledger",
        export_detailed_title="Customer Ledger (Detailed)",
        attach_ledger_party_fn=_attach_ledger_party,
        export_df_fn=export_df,
    )


# ---------------------------------------------------------------------------
# Supplier Ledger
# ---------------------------------------------------------------------------
def page_supplier_ledger():
    from erp_ui.ledger_shared import render_party_ledger

    render_party_ledger(
        "supplier",
        page_title="Supplier Ledger",
        party_select_key="sl_sup",
        from_key="sl_from",
        to_key="sl_to",
        tab_state_key="sl_ledger_tab",
        split_books_key="sl_split_books",
        export_summary_name="supplier_ledger",
        export_detailed_name="supplier_ledger_detailed",
        export_summary_title="Supplier Ledger",
        export_detailed_title="Supplier Ledger (Detailed)",
        attach_ledger_party_fn=_attach_ledger_party,
        export_df_fn=export_df,
    )


# ---------------------------------------------------------------------------
# Account Ledger (any GL — income, expense, tax, bank, etc.)
# ---------------------------------------------------------------------------
def page_account_ledger():
    from erp_ui.helpers import render_ledger_summary_table

    hlp.std_page_header("Account Ledger", status="posted", status_kind="shell")
    st.caption(
        "Opening, period debit/credit, and closing for any chart account "
        "(income, expense, tax, cash, bank, and other GL heads)."
    )
    if not db.get_accounts(active_only=False):
        st.info("Add accounts in Chart of Accounts first.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        acc_id = hlp.account_select("al_acc")
    fd = c2.date_input("From", value=None, key="al_from")
    td = c3.date_input("To", value=None, key="al_to")
    if not acc_id:
        st.info("Select an account.")
        return
    fd_s = str(fd) if fd else None
    td_s = str(td) if td else None
    account, entries = db.get_account_ledger(acc_id, fd_s, td_s)
    if not account:
        st.warning("Account not found.")
        return
    summary = (account or {}).get("ledger_summary") or {}
    opening = float(summary.get("opening") or 0)
    pdeb = float(summary.get("period_debit") or 0)
    pcred = float(summary.get("period_credit") or 0)
    closing = float(summary.get("closing") if summary else (
        entries[-1]["balance"] if entries else account.get("balance") or 0
    ))
    type_lbl = (account.get("account_type") or "").title()
    st.subheader(f"{account['code']} — {account['name']}")
    if type_lbl:
        st.caption(f"Type: {type_lbl}")
    hlp.render_ledger_kpi_strip(opening, pdeb, pcred, closing, signed_open_close=False)
    if entries:
        df = pd.DataFrame(entries)[["date", "ref", "description", "debit", "credit", "balance"]]
        df.columns = ["Date", "Ref", "Description", "Debit", "Credit", "Balance"]
        render_ledger_summary_table(entries)
        export_df(df, "account_ledger", f"Account Ledger — {account['code']} {account['name']}")
    else:
        st.info("No ledger entries.")


# ---------------------------------------------------------------------------
# Stock Report
# ---------------------------------------------------------------------------
def page_stock_report():
    from erp_ui.inventory_pages import page_stock_report as _page
    return _page()



# ---------------------------------------------------------------------------
# Profit & Loss
# ---------------------------------------------------------------------------
def page_profit_loss():
    hlp.std_page_header("Profit & Loss Report", status="posted", status_kind="shell")
    c1, c2 = st.columns(2)
    fd = c1.date_input("From", value=date(date.today().year, 1, 1), key="pl_from")
    td = c2.date_input("To", value=date.today(), key="pl_to")
    pl = db.get_profit_loss(str(fd), str(td))

    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Sales</p>"
        f"<p class='txn-kpi-val'>{fmt_money(pl['net_sales'])}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Purchases</p>"
        f"<p class='txn-kpi-val'>{fmt_money(pl['net_purchases'])}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Gross Profit</p>"
        f"<p class='txn-kpi-val'>{fmt_money(pl['gross_profit'])}</p></div>",
        unsafe_allow_html=True,
    )
    net_cls = "inv-badge-approved" if pl["net_profit"] >= 0 else "inv-badge-rejected"
    k4.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Profit</p>"
        f"<p class='txn-kpi-val'>{fmt_money(pl['net_profit'])}</p>"
        f"<p><span class='inv-badge {net_cls}'>"
        f"{'Profit' if pl['net_profit'] >= 0 else 'Loss'}</span></p></div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown("**Income**")
        st.write(f"Gross Sales: **{fmt_money(pl['gross_sales'])}**")
        st.write(f"Less: Sale Returns: **({fmt_money(pl['sale_returns'])})**")
        st.write(f"**Net Sales: {fmt_money(pl['net_sales'])}**")
        st.markdown("**Cost of Goods**")
        st.write(f"Gross Purchases: **{fmt_money(pl['gross_purchases'])}**")
        st.write(f"Less: Purchase Returns: **({fmt_money(pl['purchase_returns'])})**")
        st.write(f"**Net Purchases: {fmt_money(pl['net_purchases'])}**")
        st.markdown("**Operating**")
        st.write(f"Operating Expenses: **{fmt_money(pl['operating_expenses'])}**")
    export_df(pd.DataFrame([pl]), "profit_loss", f"Profit & Loss {fd} to {td}")


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------
def page_users():
    from erp_ui.helpers import sticky_page_tabs
    from html import escape

    hlp.std_page_header("User Management")
    tab = sticky_page_tabs(["Users", "Add User", "Edit / Delete"], "users_page_tab")

    if tab == "Users":
        rows = db.get_users()
        if rows:
            ths = "".join(f"<th>{h}</th>" for h in ("Username", "Full Name", "Role", "Active"))
            body = []
            for r in rows:
                active = bool(r.get("is_active"))
                badge = (
                    '<span class="inv-badge inv-badge-approved">Active</span>'
                    if active
                    else '<span class="inv-badge inv-badge-cancelled">Inactive</span>'
                )
                body.append(
                    "<tr>"
                    f"<td>{escape(str(r.get('username') or ''))}</td>"
                    f"<td>{escape(str(r.get('full_name') or ''))}</td>"
                    f"<td>{escape(str(r.get('role') or ''))}</td>"
                    f"<td class='txn-status-cell'>{badge}</td>"
                    "</tr>"
                )
            st.markdown(
                f"<div class='txn-kpi-card'><p class='txn-kpi'>Users</p>"
                f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="txn-reg-wrap"><table class="txn-reg-table">'
                f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No users.")

    elif tab == "Add User":
        if st.session_state.pop("user_add_success", None):
            st.success("User created. Add another below.")
        form_key = f"add_user_{st.session_state.get('user_add_form_id', 0)}"
        with st.form(form_key):
            username = st.text_input("Username *")
            full_name = st.text_input("Full Name *")
            password = st.text_input("Password *", type="password")
            role = st.selectbox("Role", ["admin", "user"])
            if st.form_submit_button("Create User", type="primary"):
                if not username or not full_name or not password:
                    st.error("All fields required.")
                else:
                    try:
                        db.add_user(username, password, full_name, role)
                        st.session_state["user_add_success"] = True
                        st.session_state["user_add_form_id"] = st.session_state.get("user_add_form_id", 0) + 1
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    elif tab == "Edit / Delete":
        rows = db.get_users()
        if not rows:
            st.info("No users.")
            return
        opts = {f"{r['username']} - {r['full_name']}": r for r in rows}
        sel = st.selectbox("Select User", list(opts.keys()))
        u = opts[sel]
        with st.form("edit_user"):
            full_name = st.text_input("Full Name", value=u["full_name"])
            role = st.selectbox("Role", ["admin", "user"], index=0 if u["role"] == "admin" else 1)
            active = st.checkbox("Active", value=bool(u["is_active"]))
            new_pass = st.text_input("New Password (leave blank to keep)", type="password")
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Update"):
                db.update_user(u["id"], full_name, role, int(active), new_pass or None)
                ff.action_done("User updated.")
            if c2.form_submit_button("Delete") and u["username"] != "admin":
                db.delete_user(u["id"])
                ff.action_done("User deleted.")


def page_stock():
    from erp_ui.inventory_pages import page_stock as _page
    return _page()



def page_stock_adjustments():
    from erp_ui.inventory_pages import page_stock_adjustments as _page
    return _page()



def page_stock_transfers():
    from erp_ui.inventory_pages import page_stock_transfers as _page
    return _page()



def page_backup_restore():
    hlp.std_page_header("Backup & Restore")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Backup Database")
        if st.button("Create Backup Now"):
            path = db.backup_database()
            st.success(f"Backup saved: {path}")
    with c2:
        st.subheader("Restore Database")
        st.warning("Restore will overwrite the current database. Restart the app after restore.")
        uploaded = st.file_uploader("Select backup .db file", type=["db"])
        if uploaded and st.button("Restore from Upload"):
            import tempfile, os
            tmp = os.path.join(tempfile.gettempdir(), uploaded.name)
            with open(tmp, "wb") as f:
                f.write(uploaded.getbuffer())
            db.restore_database(tmp)
            st.success("Database restored. Please restart the application.")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
PAGES = {
    "Dashboard": page_dashboard,
    "Business Overview": page_business_overview,
    "Approval Inbox": appr_inbox.page_approval_inbox,
    "Customers": page_customers,
    "Suppliers": page_suppliers,
    "Products": page_items,
    "Items / Products": page_items,
    "Product Categories": v3.page_product_categories,
    "Account & Item Groups": mgrp.page_master_groups,
    "Custom Groups": mgrp.page_master_groups,
    "Units of Measure": v3.page_units,
    "Warehouses": v3.page_warehouses,
    "Employees": hr.page_hr_employees,
    "Employee Master": hr.page_hr_employees,
    "Attendance": att.page_attendance_simple,
    "Leave Management": hr.page_leave,
    "Payroll": hr.page_payroll,
    "Employee Advances": hr.page_advances,
    "Employee Ledger": hr.page_employee_ledger,
    "Tax Rates": v3.page_tax_rates,
    "Payment Terms": v3.page_payment_terms,
    "Vehicles": v3.page_vehicles,
    "Machines": v3.page_machines,
    "Stock": page_stock,
    "Inventory": page_inventory,
    "Stock Adjustments": page_stock_adjustments,
    "Stock Revaluation": srv.page_stock_revaluation,
    "Download App": dl.page_download_app,
    "Stock Transfers": page_stock_transfers,
    "Weight Entry": wb.page_weight_entry,
    "Weight Reports": wb.page_weight_reports,
    "Weight Slips": wb.page_weight_entry,
    "Batch Stock": v3.page_batch_stock,
    "Batch Manufacturing": prod.page_production_orders,
    "Quotations": v3.page_quotations,
    "Sales Orders": v3.page_sales_orders,
    "Delivery Notes": v3.page_delivery_notes,
    "Sales Invoices": sales_pg.page_sales,
    "Sale Approval": iwf.page_sale_approval,
    "Sales": sales_pg.page_sales,
    "Sales Returns": page_sale_return,
    "Sale Return": page_sale_return,
    "Purchase Requisition": v3.page_purchase_requisition,
    "Purchase Orders": v3.page_purchase_orders,
    "GRN": v3.page_grn,
    "Purchase Invoices": purch_pg.page_purchases,
    "Purchase Approval": iwf.page_purchase_approval,
    "Purchases": purch_pg.page_purchases,
    "Purchase Returns": page_purchase_return,
    "Purchase Return": page_purchase_return,
    "BOM": prod.page_bom_composition,
    "BOM / Formula": prod.page_bom_composition,
    "Daily Production": prod.page_daily_production,
    "Plant Shift": plant_shift.page_plant_shift,
    "Production Orders": prod.page_production_orders,
    "Job Cards": jc.page_job_cards,
    "Formula Master": ind.page_formulation,
    "Spray Dryer": ind.page_spray_dryer,
    "Batch Manufacturing": ind.page_batch_manufacturing,
    "Chemical Reactor": ind.page_reactor,
    "Corrugated Production": ind.page_corrugated,
    "Gravure / Packaging": ind.page_gravure_packaging,
    "PET Bottle Blowing": ind.page_pet_blowing,
    "QC Laboratory": ind.page_qc_lab,
    "Plant Maintenance": ind.page_plant_maintenance,
    "Energy Management": ind.page_energy,
    "Industrial Costing": ind.page_industrial_costing,
    "Toll Manufacturing": ind.page_toll_manufacturing,
    "Industrial Warehouse": ind.page_industrial_warehouse,
    "Dispatch Planning": dsp.page_dispatch_planning,
    "Industrial Dashboards": ind.page_industrial_dashboards,
    "Industrial Reports": ind.page_industrial_reports,
    "Gate Pass Entry": gp.page_gate_pass_entry,
    "Reports Center": reports.page_reports_center,
    "HR Reports": reports.page_hr_reports_hub,
    "Gate Pass Reports": reports.page_gate_pass_reports_hub,
    "Cash Book": fin.page_cash_book,
    "Bank Book": fin.page_bank_book,
    "Journal Voucher": v3.page_journal,
    "Chart of Accounts": coa.page_chart_of_accounts,
    "Customer Ledger": page_customer_ledger,
    "Supplier Ledger": page_supplier_ledger,
    "Account Ledger": page_account_ledger,
    "Customer Receipt": fin.page_customer_receipt,
    "Supplier Payment": fin.page_supplier_payment,
    "Expense Payment": fin.page_expense_payment,
    "Expense Bill": fin.page_expense_bill,
    "Cash Advance": fin.page_cash_advance,
    "Party Transfer": fin.page_party_transfer,
    "General Ledger": v3.page_general_ledger,
    "Trial Balance": v3.page_trial_balance,
    "Profit & Loss Report": page_profit_loss,
    "Balance Sheet": v3.page_balance_sheet,
    "Fiscal Year Closing": fiscal.page_fiscal_year_closing,
    "Stock Report": page_stock_report,
    "Tax Report": v3.page_tax_report,
    "Customer Outstanding": v3.page_customer_outstanding,
    "Customer Due Aging": v3.page_customer_due_aging,
    "Supplier Outstanding": v3.page_supplier_outstanding,
    "User Management": page_users,
    "Roles & Permissions": v3.page_roles,
    "System Settings": v3.page_settings,
    "Holidays": hol.page_holidays,
    "Draft Center": draft_center.page_draft_center,
    "ERP Health Check": erp_health.page_erp_health_check,
    "Approval Designer": appr_des.page_approval_designer,
    "Mobile Approvals": mobile_approvals.page_mobile_approvals,
    "Price Lists": price_list_pages.page_price_lists,
    "Distributor Orders": distributor_admin.page_distributor_orders,
    "Distribution": distribution_pages.page_distribution,
    "Audit Log": audit.page_audit_log,
    "Backup & Restore": page_backup_restore,
}


def _apply_pending_nav(nav):
    apply_pending_nav(nav)


def main():
    require_login()
    if not st.session_state.user:
        page_login()
        return

    from erp_ui.auth_session import sync_client_session
    sync_client_session()

    user = st.session_state.user
    from erp_core.v15_security import is_portal_user
    from erp_ui.change_password import render_change_password

    if user.get("must_change_password"):
        st.markdown("## Change password required")
        if render_change_password(user, force=True):
            st.rerun()
        return

    if is_portal_user(user) or st.query_params.get("portal") == "1":
        portal_pages.render_portal_app(user)
        return

    if st.session_state.get("show_change_password"):
        st.markdown("## Change password")
        col_back, _ = st.columns([1, 4])
        with col_back:
            if st.button("← Back", key="change_password_back", use_container_width=True):
                st.session_state.pop("show_change_password", None)
                st.rerun()
        if render_change_password(user, force=False):
            st.session_state.pop("show_change_password", None)
            st.rerun()
        return

    nav = filtered_nav_groups(st.session_state.user)
    if not nav:
        st.error("No modules available for your role.")
        return

    _apply_pending_nav(nav)
    sync_nav_state(nav)

    group = st.session_state["sidebar_group"]
    module = st.session_state["sidebar_screen"]
    on_desktop = module == "Dashboard"

    # Right-side sliding notification panel (ERP staff)
    from erp_ui.notification_sidebar import render_erp_notification_sidebar
    render_erp_notification_sidebar(user)

    if not on_desktop:
        from erp_ui.desktop_home import render_module_topbar

        st.markdown(
            '<div class="erp-module-root" aria-hidden="true">&#8203;</div>',
            unsafe_allow_html=True,
        )
        company = db.get_setting("company_name", "IFS Chemicals")
        render_module_topbar(nav, st.session_state.user, company, group, module)

    render_main_breadcrumb(nav, group, module)
    st.session_state["_page_header_rendered"] = False
    try:
        PAGES[module]()
    except Exception as exc:
        from erp_core.error_handler import log_exception, user_friendly_message
        uid = st.session_state.get("user", {}).get("id")
        log_id = log_exception(exc, screen=module, user_id=uid)
        st.error(f"**{module}** — {user_friendly_message(exc)}")
        if log_id and st.session_state.get("user", {}).get("role") == "admin":
            with st.expander("Developer diagnostics"):
                st.code(str(exc))
                st.caption(f"Error log id: {log_id}")


if __name__ == "__main__":
    main()
