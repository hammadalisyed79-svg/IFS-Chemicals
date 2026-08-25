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
from erp_ui import plant_shift_dashboard as plant_shift
from erp_ui.nav import (
    apply_pending_nav,
    filtered_nav_groups,
    render_main_breadcrumb,
    sync_nav_state,
)
from erp_ui.layout_styles import inject_layout_styles


def _seed_pr_edit(ret, sup_opts, *, sup=None, ret_no=None, rdate=None, notes=None, from_form=False):
    st.session_state["pr_edit_id"] = ret["id"]
    st.session_state["pr_edit_header"] = {
        "return_no": ret_no if from_form else ret["return_no"],
        "supplier_id": sup_opts[sup] if from_form and sup else ret["supplier_id"],
        "purchase_id": ret.get("purchase_id"),
        "return_date": str(rdate) if from_form else ret["return_date"],
        "notes": notes if from_form else (ret.get("notes") or ""),
    }
    st.session_state["pr_edit_lines"] = hlp._pad_line_rows([
        {"item_id": li["item_id"], "quantity": li["quantity"], "rate": li["rate"],
         "amount": li["amount"], "net_weight": li.get("net_weight", 0)}
        for li in ret["items"]
    ])


def _seed_sr_edit(ret, cust_opts, *, cust=None, ret_no=None, rdate=None, notes=None, from_form=False):
    st.session_state["sr_edit_id"] = ret["id"]
    st.session_state["sr_edit_header"] = {
        "return_no": ret_no if from_form else ret["return_no"],
        "customer_id": cust_opts[cust] if from_form and cust else ret["customer_id"],
        "sale_id": ret.get("sale_id"),
        "return_date": str(rdate) if from_form else ret["return_date"],
        "notes": notes if from_form else (ret.get("notes") or ""),
    }
    st.session_state["sr_edit_lines"] = hlp._pad_line_rows([
        {"item_id": li["item_id"], "quantity": li["quantity"], "rate": li["rate"],
         "amount": li["amount"], "net_weight": li.get("net_weight", 0)}
        for li in ret["items"]
    ])


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
    peek = st.session_state.get("cust_page_tab") or "List"
    hlp.std_page_header(
        "Customers",
        status="register" if peek == "List" else ("draft" if peek == "Add New" else None),
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab_list_lbl = hlp.sticky_page_tabs(
        ["List", "Add New", "Edit / Delete"],
        "cust_page_tab",
    )

    if tab_list_lbl == "List":
        gid = hlp.master_group_filter("customer", "cust")
        rows = db.get_customers(group_id=gid)
        if rows:
            hlp.master_list_search(
                "Customers", rows, "cust",
                ["code", "name", "group_name", "phone", "city", "province", "credit_limit", "balance", "is_active"],
                {"code": "Code", "name": "Name", "group_name": "Group", "phone": "Phone", "city": "City",
                 "province": "Province", "credit_limit": "Credit Limit", "balance": "Balance", "is_active": "Active"},
            )
        else:
            st.info("No customers yet. Add one in the Add New tab.")

    elif tab_list_lbl == "Add New":
        hlp.section_header("Location")
        fid = "cust_add"
        province, city = hlp.province_city_fields(
            fid, reset_token=ff.form_generation(fid),
        )
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_customer_{gen}"):
            code = st.text_input("Code", value=db.next_code("CUS", "customers"), key=wk("code"))
            name = st.text_input("Name *", key=wk("name"))
            contact = st.text_input("Contact Person", key=wk("contact"))
            phone = st.text_input("Phone", key=wk("phone"))
            email = st.text_input("Email", key=wk("email"))
            address = st.text_area("Address", key=wk("address"))
            ntn = st.text_input("NTN", key=wk("ntn"))
            strn = st.text_input("STRN", key=wk("strn"))
            credit = hlp.money_input(
                "Credit Limit", value=0.0, min_value=0.0, key=wk("credit"),
            )
            opening = hlp.money_input(
                "Opening Balance",
                value=0.0,
                key=wk("opening"),
                help="+ receivable (customer owes you). − credit/advance balance.",
            )
            group_id = hlp.master_group_select("customer", wk("grp"))
            if st.form_submit_button("Save Customer"):
                if not name:
                    st.error("Name is required.")
                else:
                    db.add_customer({"code": code, "name": name, "contact_person": contact, "phone": phone,
                                     "email": email, "address": address, "city": city, "province": province,
                                     "ntn": ntn, "strn": strn,
                                     "credit_limit": credit, "opening_balance": opening, "group_id": group_id}, uid())
                    ff.finish_new_entry(
                        form_id=fid,
                        message=f"Customer **{name}** saved successfully. Form cleared for the next entry.",
                    )

    elif tab_list_lbl == "Edit / Delete":
        rows = db.get_customers(active_only=False)
        if not rows:
            st.info("No customers to edit.")
            return
        _, cid, _ = hlp.smart_select(
            "Customer", rows, "cust_edit", "id",
            lambda r: f"{r['code']} - {r['name']}" + (f" | {r['city']}" if r.get('city') else "") + (f" | {r['phone']}" if r.get('phone') else ""),
            placeholder="Type customer code, name, phone, city, or NTN...",
        )
        if not cid:
            return
        c = db.get_customer(cid)
        hlp.section_header("Location")
        province, city = hlp.province_city_fields(
            "cust_edit",
            province=c.get("province") or "",
            city=c.get("city") or "",
            reset_token=cid,
        )
        with st.form("edit_customer"):
            code = st.text_input("Code", value=c["code"])
            name = st.text_input("Name", value=c["name"])
            contact = st.text_input("Contact Person", value=c["contact_person"] or "")
            phone = st.text_input("Phone", value=c["phone"] or "")
            email = st.text_input("Email", value=c["email"] or "")
            address = st.text_area("Address", value=c["address"] or "")
            ntn = st.text_input("NTN", value=c.get("ntn") or "")
            strn = st.text_input("STRN", value=c.get("strn") or "")
            st.markdown("**Portal / operations contacts** *(updated by distributor on portal Profile)*")
            pc1, pc2, pc3 = st.columns(3)
            dispatch_phone = pc1.text_input(
                "Dispatch phone", value=c.get("dispatch_phone") or "", key="cust_edit_dispatch",
            )
            accounts_phone = pc2.text_input(
                "Accounts phone", value=c.get("accounts_phone") or "", key="cust_edit_accounts",
            )
            owner_phone = pc3.text_input(
                "Owner phone", value=c.get("owner_phone") or "", key="cust_edit_owner",
            )
            credit = hlp.money_input("Credit Limit", value=float(c["credit_limit"]), min_value=0.0, key="cust_edit_credit")
            opening = hlp.money_input("Opening Balance", value=float(c["opening_balance"]), key="cust_edit_opening")
            st.caption("Signed: **positive = Dr**, **negative = Cr** (Finance Manager).")
            group_id = hlp.master_group_select("customer", "cust_edit", c.get("group_id"))
            active = st.checkbox("Active", value=bool(c["is_active"]))
            c1, c2 = st.columns(2)
            update = c1.form_submit_button("Update")
            delete = c2.form_submit_button("Delete", type="secondary")
            if update:
                db.update_customer(cid, {"code": code, "name": name, "contact_person": contact, "phone": phone,
                                         "email": email, "address": address, "city": city, "province": province,
                                         "ntn": ntn, "strn": strn,
                                         "dispatch_phone": dispatch_phone or None,
                                         "accounts_phone": accounts_phone or None,
                                         "owner_phone": owner_phone or None,
                                         "credit_limit": credit, "opening_balance": opening, "group_id": group_id,
                                         "is_active": int(active)})
                ff.action_done(f"Customer **{name}** updated successfully.")
            if delete:
                db.delete_customer(cid)
                ff.action_done(f"Customer **{code}** deleted successfully.")


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
def page_suppliers():
    peek = st.session_state.get("sup_page_tab") or "List"
    hlp.std_page_header(
        "Suppliers",
        status="register" if peek == "List" else ("draft" if peek == "Add New" else None),
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab = hlp.sticky_page_tabs(["List", "Add New", "Edit / Delete"], "sup_page_tab")

    if tab == "List":
        gid = hlp.master_group_filter("supplier", "sup")
        rows = db.get_suppliers(group_id=gid)
        if rows:
            hlp.master_list_search(
                "Suppliers", rows, "sup",
                ["code", "name", "group_name", "phone", "city", "balance", "is_active"],
                {"code": "Code", "name": "Name", "group_name": "Group", "phone": "Phone", "city": "City",
                 "balance": "Balance", "is_active": "Active"},
            )
        else:
            st.info("No suppliers yet.")

    elif tab == "Add New":
        fid = "sup_add"
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_supplier_{gen}"):
            code = st.text_input("Code", value=db.next_code("SUP", "suppliers"), key=wk("code"))
            name = st.text_input("Name *", key=wk("name"))
            contact = st.text_input("Contact Person", key=wk("contact"))
            phone = st.text_input("Phone", key=wk("phone"))
            email = st.text_input("Email", key=wk("email"))
            address = st.text_area("Address", key=wk("address"))
            city = st.text_input("City", key=wk("city"))
            opening = hlp.money_input(
                "Opening Balance",
                value=0.0,
                key=wk("opening"),
                help="+ payable (you owe supplier).",
            )
            group_id = hlp.master_group_select("supplier", wk("grp"))
            if st.form_submit_button("Save Supplier"):
                if not name:
                    st.error("Name is required.")
                else:
                    db.add_supplier({"code": code, "name": name, "contact_person": contact, "phone": phone,
                                     "email": email, "address": address, "city": city,
                                     "opening_balance": opening, "group_id": group_id})
                    ff.finish_new_entry(
                        form_id=fid,
                        message=f"Supplier **{name}** saved successfully. Form cleared for the next entry.",
                    )

    elif tab == "Edit / Delete":
        rows = db.get_suppliers(active_only=False)
        if not rows:
            st.info("No suppliers to edit.")
            return
        _, sid, _ = hlp.smart_select(
            "Supplier", rows, "sup_edit", "id",
            lambda r: f"{r['code']} - {r['name']}" + (f" | {r['city']}" if r.get('city') else "") + (f" | {r['phone']}" if r.get('phone') else ""),
            placeholder="Type supplier code, name, phone, or city...",
        )
        if not sid:
            return
        s = db.get_supplier(sid)
        with st.form("edit_supplier"):
            code = st.text_input("Code", value=s["code"])
            name = st.text_input("Name", value=s["name"])
            contact = st.text_input("Contact Person", value=s["contact_person"] or "")
            phone = st.text_input("Phone", value=s["phone"] or "")
            email = st.text_input("Email", value=s["email"] or "")
            address = st.text_area("Address", value=s["address"] or "")
            city = st.text_input("City", value=s["city"] or "")
            opening = hlp.money_input("Opening Balance", value=float(s["opening_balance"]), key="sup_edit_opening")
            st.caption("Signed: **positive = Dr**, **negative = Cr** (Finance Manager — suppliers can be either).")
            group_id = hlp.master_group_select("supplier", "sup_edit", s.get("group_id"))
            active = st.checkbox("Active", value=bool(s["is_active"]))
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Update"):
                db.update_supplier(sid, {"code": code, "name": name, "contact_person": contact, "phone": phone,
                                         "email": email, "address": address, "city": city,
                                         "opening_balance": opening, "group_id": group_id,
                                         "is_active": int(active)})
                ff.action_done(f"Supplier **{name}** updated successfully.")
            if c2.form_submit_button("Delete"):
                db.delete_supplier(sid)
                ff.action_done(f"Supplier **{code}** deleted successfully.")


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
def page_items():
    peek = st.session_state.get("prod_page_tab") or "List"
    hlp.std_page_header(
        "Products",
        status="register" if peek == "List" else ("draft" if peek == "Add New" else None),
        status_kind="shell" if peek == "List" else "invoice",
    )
    tab = hlp.sticky_page_tabs(
        ["List", "Add New", "Edit / Delete", "Import Weights"],
        "prod_page_tab",
    )

    cats = db.get_product_categories()
    cat_opts = {f"{r['code']} - {r['name']}": r["id"] for r in cats}
    units = db.get_units_of_measure()
    unit_opts = {f"{r['symbol']} - {r['name']}": r["id"] for r in units}
    tax_rates = db.get_tax_rates()
    tax_opts = {f"{t['code']} - {t['name']}": t["id"] for t in tax_rates}
    item_types = ["raw", "finished", "packaging", "trading", "service"]
    weight_units = ["kg", "gram", "liter", "ml", "ton", "piece", "carton", "bag", "drum"]

    if tab == "List":
        gid = hlp.master_group_filter("product", "prod")
        rows = db.get_items(group_id=gid)
        if rows:
            hlp.master_list_search(
                "Products", rows, "prod",
                [
                    "code", "name", "group_name", "category", "unit", "item_type",
                    "standard_weight", "weight_unit", "packing_size",
                    "purchase_price", "sale_price", "stock_qty", "reorder_level",
                ],
                {
                    "code": "Code", "name": "Name", "group_name": "Group", "category": "Category", "unit": "Unit",
                    "item_type": "Type", "standard_weight": "Std Weight", "weight_unit": "Wt Unit",
                    "packing_size": "Packing",
                    "purchase_price": "Purchase Price", "sale_price": "Sale Price",
                    "stock_qty": "Stock", "reorder_level": "Reorder Level",
                },
                extra_fields=["packing_size", "standard_weight", "weight_unit"],
            )
        else:
            st.info("No items yet.")

    elif tab == "Add New":
        fid = "item_add"
        gen = ff.form_generation(fid)
        wk = lambda n: ff.widget_key(fid, n)
        with st.form(f"add_item_{gen}"):
            code = st.text_input("Code", value=db.next_code("ITM", "items"), key=wk("code"))
            name = st.text_input("Name *", key=wk("name"))
            category = st.selectbox("Category", list(cat_opts.keys()), key=wk("cat"))
            cat_id = cat_opts[category]
            unit_lbl = st.selectbox("Unit", list(unit_opts.keys()), key=wk("unit"))
            unit_id = unit_opts[unit_lbl]
            item_type = st.selectbox("Type", item_types, key=wk("type"))
            weight_unit = st.selectbox("Weight Unit", weight_units, key=wk("wunit"))
            standard_weight = st.number_input(
                "Standard Weight per Unit", min_value=0.0, value=0.0, key=wk("stdw"),
            )
            packing_size = st.text_input("Packing Size", key=wk("pack"))
            tax_lbl = st.selectbox("Tax Category", ["—"] + list(tax_opts.keys()), key=wk("tax"))
            tax_id = tax_opts.get(tax_lbl) if tax_lbl != "—" else None
            pp = hlp.money_input("Purchase Price", value=0.0, min_value=0.0, key=wk("pp"))
            sp = hlp.money_input("Sale Price", value=0.0, min_value=0.0, key=wk("sp"))
            reorder = st.number_input("Reorder Level", min_value=0.0, value=0.0, key=wk("reorder"))
            min_stock = st.number_input("Minimum Stock", min_value=0.0, value=0.0, key=wk("min"))
            stock = st.number_input("Opening Stock", min_value=0.0, value=0.0, key=wk("stock"))
            group_id = hlp.master_group_select("product", wk("grp"))
            if st.form_submit_button("Save Item"):
                if not name:
                    st.error("Name is required.")
                else:
                    db.add_item({"code": code, "name": name, "category_id": cat_id, "unit_id": unit_id,
                                 "item_type": item_type, "weight_unit": weight_unit, "standard_weight": standard_weight,
                                 "packing_size": packing_size, "tax_rate_id": tax_id,
                                 "purchase_price": pp, "sale_price": sp,
                                 "reorder_level": reorder, "min_stock": min_stock, "stock_qty": stock,
                                 "group_id": group_id}, uid())
                    ff.finish_new_entry(
                        form_id=fid,
                        message=f"Item **{name}** saved successfully. Form cleared for the next entry.",
                    )

    elif tab == "Import Weights":
        from import_product_weights import (
            DEFAULT_ACCDB,
            apply_weights,
            load_pairs,
            load_weights_from_sales_inventory,
            write_weight_template_csv,
        )

        st.markdown("**Sync missing sale / purchase rates (old database)**")
        st.caption(
            "Fills **Sale Price** and **Purchase Price** on products that are zero, using: "
            "last ERP invoice rate → FMYE ItemInformation / last invoice → Sales & Inventory .accdb."
        )
        if st.button("Sync rates from old data", type="primary", key="rate_legacy_sync"):
            try:
                from product_rates_legacy import sync_missing_product_rates, clear_rate_cache
                clear_rate_cache()
                stats = sync_missing_product_rates(user_id=uid(), dry_run=False)
                ff.action_done(
                    f"Updated sale price on **{stats['sale_updated']}** products, "
                    f"purchase price on **{stats['purchase_updated']}**. "
                    f"Already had rates: **{stats['skipped']}**."
                )
            except Exception as e:
                st.error(str(e))

        st.divider()
        st.markdown("**Import standard weight from Sales & Inventory (Access)**")
        st.caption(
            "Reads **ProductID** + **Weight** from `tblProduct`. "
            "Updates ERP **Std Weight** only where the product **code** already exists and weight > 0."
        )
        acc_path = st.text_input("Access file", value=str(DEFAULT_ACCDB), key="wt_import_path")
        if st.button("Import weights now", type="primary", key="wt_accdb_run"):
            try:
                pairs, ex = load_weights_from_sales_inventory(Path(acc_path.strip()))
                stats = apply_weights(pairs, dry_run=False, user_id=uid())
                detail = (
                    f"Access products: **{ex['access_rows']}** | "
                    f"No weight: **{ex['skipped_no_weight']}** | "
                    f"Code not in ERP: **{stats['skipped_no_product']}**"
                )
                ff.action_done(
                    f"Updated **{stats['updated']}** products "
                    f"({len(pairs)} rows with code + weight in Access). {detail}"
                )
            except Exception as e:
                st.error(str(e))

        with st.expander("CSV template or other file"):
            tpl = Path(__file__).parent / "import" / "product_weights_template.csv"
            n_tpl = write_weight_template_csv(tpl)
            st.download_button(
                f"Download CSV template ({n_tpl} products)",
                data=tpl.read_bytes(),
                file_name="product_weights_template.csv",
                mime="text/csv",
                key="wt_tpl_save",
            )
            up = st.file_uploader("Upload CSV", type=["csv"], key="wt_csv_up")
            if up and st.button("Import from CSV", key="wt_csv_run"):
                try:
                    import tempfile

                    tmp = Path(tempfile.gettempdir()) / "product_weights_upload.csv"
                    tmp.write_bytes(up.getvalue())
                    _, _, _, pairs, _ex = load_pairs(
                        accdb=None, csv_path=tmp, table=None, code_col=None, weight_col=None
                    )
                    stats = apply_weights(pairs, dry_run=False, user_id=uid())
                    ff.action_done(f"Updated **{stats['updated']}** products.")
                except Exception as e:
                    st.error(str(e))

    elif tab == "Edit / Delete":
        items = db.get_items()
        if not items:
            st.info("No items to edit.")
            return
        _, iid, _ = hlp.smart_select(
            "Product", items, "item_edit", "id",
            lambda r: f"{r['code']} - {r['name']} ({r.get('stock_qty', 0)} {r.get('unit', '')})",
            placeholder="Type product code or name (e.g. SF0017 or BRILLO)...",
        )
        if not iid:
            return
        it = db.get_item(iid)
        cat_labels = list(cat_opts.keys()) or [it.get("category") or "—"]
        default_cat = next((k for k, v in cat_opts.items() if v == it.get("category_id")), cat_labels[0])
        unit_labels = list(unit_opts.keys()) or [it.get("unit") or "—"]
        default_unit = next((k for k, v in unit_opts.items() if v == it.get("unit_id")), unit_labels[0])
        wu = (it.get("weight_unit") or "kg").lower()
        tax_labels = ["—"] + list(tax_opts.keys())
        default_tax = next((k for k, v in tax_opts.items() if v == it.get("tax_rate_id")), "—")

        with st.form("edit_item"):
            code = st.text_input("Code", value=it["code"])
            name = st.text_input("Name", value=it["name"])
            category = st.selectbox(
                "Category", cat_labels,
                index=cat_labels.index(default_cat) if default_cat in cat_labels else 0,
            )
            cat_id = cat_opts.get(category)
            unit_lbl = st.selectbox(
                "Unit", unit_labels,
                index=unit_labels.index(default_unit) if default_unit in unit_labels else 0,
            )
            unit_id = unit_opts.get(unit_lbl)
            item_type = st.selectbox(
                "Type", item_types,
                index=item_types.index(it["item_type"]) if it.get("item_type") in item_types else 0,
            )
            c1, c2 = st.columns(2)
            weight_unit = c1.selectbox(
                "Weight Unit", weight_units,
                index=weight_units.index(wu) if wu in weight_units else 0,
            )
            standard_weight = c2.number_input(
                "Standard Weight per Unit", min_value=0.0,
                value=float(it.get("standard_weight") or 0),
            )
            packing_size = st.text_input("Packing Size", value=it.get("packing_size") or "")
            tax_lbl = st.selectbox(
                "Tax Category", tax_labels,
                index=tax_labels.index(default_tax) if default_tax in tax_labels else 0,
            )
            tax_id = tax_opts.get(tax_lbl) if tax_lbl != "—" else None
            group_id = hlp.master_group_select("product", "item_edit", it.get("group_id"))
            c3, c4 = st.columns(2)
            with c3:
                pp = hlp.money_input("Purchase Price", value=float(it["purchase_price"]), min_value=0.0, key="item_edit_pp")
            with c4:
                sp = hlp.money_input("Sale Price", value=float(it["sale_price"]), min_value=0.0, key="item_edit_sp")
            c5, c6 = st.columns(2)
            reorder = c5.number_input("Reorder Level", min_value=0.0, value=float(it["reorder_level"]))
            min_stock = c6.number_input("Minimum Stock", min_value=0.0, value=float(it.get("min_stock") or 0))
            active = st.checkbox("Active", value=bool(it["is_active"]))
            st.info(f"Current Stock: {it['stock_qty']} {it['unit']} (adjust via Inventory module)")
            blockers = db.get_product_delete_blockers(iid)
            if blockers:
                st.warning(
                    "This product is used in: **"
                    + "**, **".join(blockers)
                    + "**. It cannot be permanently deleted — use **Deactivate** instead."
                )
            c7, c8, c9 = st.columns(3)
            if c7.form_submit_button("Update"):
                db.update_item(iid, {
                    "code": code, "name": name, "category_id": cat_id, "unit_id": unit_id,
                    "item_type": item_type, "weight_unit": weight_unit, "standard_weight": standard_weight,
                    "packing_size": packing_size, "tax_rate_id": tax_id,
                    "purchase_price": pp, "sale_price": sp,
                    "reorder_level": reorder, "min_stock": min_stock, "group_id": group_id,
                    "is_active": int(active),
                }, uid())
                ff.action_done(f"Item **{name}** updated successfully.")
            if c8.form_submit_button("Delete Permanently", disabled=bool(blockers)):
                try:
                    db.delete_item(iid, uid())
                    ff.action_done(
                        f"Item **{code}** deleted successfully.",
                        prefixes=("item_edit",),
                        also=("item_edit_srch", "item_edit_sel", "srch_item_edit", "sel_item_edit"),
                    )
                except ValueError as e:
                    st.error(str(e))
            if c9.form_submit_button("Deactivate"):
                db.deactivate_item(iid, uid())
                ff.action_done(f"Item **{name}** deactivated — hidden from new transactions.")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
def page_inventory():
    from erp_ui.helpers import sticky_page_tabs, render_stock_kpi_strip, render_stock_html_table

    peek = st.session_state.get("inv_page_tab") or "Current Stock"
    hlp.std_page_header(
        "Stock",
        title="Inventory",
        status="register" if peek == "Current Stock" else None,
        status_kind="shell" if peek == "Current Stock" else "invoice",
    )
    tab = sticky_page_tabs(
        ["Current Stock", "Stock Adjustment", "Adjustment History"],
        "inv_page_tab",
    )

    if tab == "Current Stock":
        rows = db.get_inventory()
        if rows:
            render_stock_kpi_strip(rows)
            render_stock_html_table(rows)
        else:
            st.info("No inventory data.")

    elif tab == "Stock Adjustment":
        items_dict = item_options()
        if not items_dict:
            st.warning("Add items first.")
            return
        with st.form("stock_adjust"):
            item_lbl = st.selectbox("Item", list(items_dict.keys()))
            adj_date = st.date_input("Date", value=date.today())
            adj_type = st.selectbox("Adjustment Type", ["in", "out"])
            qty = st.number_input("Quantity", min_value=0.01, value=1.0)
            reason = st.text_input("Reason")
            if st.form_submit_button("Apply Adjustment"):
                item = items_dict[item_lbl]
                db.add_inventory_adjustment(item["id"], str(adj_date), adj_type, qty, reason)
                ff.finish_new_entry(form_id="inv_adj", message="Stock adjusted.")

    elif tab == "Adjustment History":
        from erp_ui.helpers import render_adjustment_html_table

        hist = db.get_inventory_adjustments()
        if hist:
            render_adjustment_html_table(hist)
            del_sel = st.selectbox("Delete adjustment", ["—"] + [f"{h['id']} - {h['item_name']} ({h['adjustment_date']})" for h in hist])
            if del_sel != "—" and st.button("Delete Selected Adjustment"):
                adj_id = int(del_sel.split(" - ")[0])
                db.delete_inventory_adjustment(adj_id)
                ff.action_done("Adjustment deleted.")
        else:
            st.info("No adjustments recorded.")


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
    from erp_ui.helpers import sticky_page_tabs
    from erp_ui.document_print import document_print_toolbar
    from erp_ui.gatepass_pages import invoice_gate_pass_panel

    peek = st.session_state.get("pr_page_tab") or "Register"
    hlp.std_page_header(
        "Purchase Returns",
        subtitle="Register · Open · New · Edit — print, linked invoice & gate pass",
        status="register" if peek == "Register" else ("draft" if peek == "New" else None),
        status_kind="shell" if peek == "Register" else "invoice",
    )
    _pr_tab = sticky_page_tabs(
        ["Register", "Open", "New", "Edit"],
        "pr_page_tab",
        open_alias_key="pr_open_tab",
    )

    if _pr_tab == "Register":
        def _pr_actions(row):
            inv_id = row.get("purchase_id")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Print return**")
                document_print_toolbar("Purchase Return", row["id"], key_prefix=f"pr_doc_{row['id']}")
                if inv_id:
                    st.markdown("**Print linked invoice**")
                    st.caption(f"Invoice: {row.get('invoice_no') or inv_id}")
                    document_print_toolbar(
                        "Purchase Invoice", inv_id, key_prefix=f"pr_inv_{row['id']}",
                    )
                else:
                    st.caption("No purchase invoice linked to this return.")
            with c2:
                st.markdown("**Gate pass (via linked invoice)**")
                if inv_id:
                    invoice_gate_pass_panel("purchase", inv_id, key_prefix=f"pr_gp_{row['id']}")
                else:
                    st.caption("Link a purchase invoice on the return to manage gate pass here.")

        txn.purchase_return_register_list(action_panel=_pr_actions)

    elif _pr_tab == "Open":
        from erp_ui.document_hub import render_document_hub
        render_document_hub("purchase_return", "pr_hub")

    elif _pr_tab == "New":
        sup_opts = supplier_options()
        items_dict = item_options()
        if not sup_opts or not items_dict:
            st.warning("Add suppliers and items first.")
            return
        with st.form("new_pur_ret"):
            default_ret = (st.session_state.get("pr_header") or {}).get("return_no") or db.peek_invoice("PR", "purchase_returns", "return_no")
            ret_no = st.text_input("Return No", value=default_ret)
            sup_labels, blank = hlp.options_with_blank(sup_opts.keys())
            sup_lbl = st.selectbox("Supplier", sup_labels)
            submitted_hdr = st.form_submit_button("Continue")
        if submitted_hdr:
            if not hlp.require_selected("supplier", sup_lbl, blank):
                return
            sup_id = sup_opts[sup_lbl]
            st.session_state["pr_header"] = {
                "return_no": ret_no, "supplier_id": sup_id,
                "return_date": str(date.today()), "notes": "",
            }
            st.session_state["pr_lines"] = [{"item_id": None, "quantity": 1.0, "rate": 0.0, "amount": 0.0}]
        if "pr_lines" in st.session_state:
            header = st.session_state.get("pr_header", {})
            rdate = st.date_input("Return Date", value=date.fromisoformat(header.get("return_date", str(date.today()))), key="pr_new_dt")
            notes = st.text_input("Notes", value=header.get("notes") or "", key="pr_new_notes")
            header["return_date"] = str(rdate)
            header["notes"] = notes
            purchase_id = txn.linked_invoice_picker(
                "pr_new", db.search_purchases, header["supplier_id"], "supplier_id",
                lambda r: f"{r['invoice_no']} - {r['supplier_name']}",
            )
            header["purchase_id"] = purchase_id
            if purchase_id and st.button("Load lines from purchase invoice", key="pr_load_inv"):
                try:
                    lines, inv = hlp.return_lines_from_invoice(purchase_id, "purchase")
                    st.session_state["pr_lines"] = lines
                    ff.action_done(f"Loaded {len(lines)} line(s) from **{inv['invoice_no']}**.")
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "pr", show_weight=True, party_id=header.get("supplier_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "pr_tax", lines, header,
                party_id=header.get("supplier_id"), party_kind="purchase",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {fmt_money(totals['total'])}")
            if st.button("Save Purchase Return", key="save_pr"):
                if not lines:
                    st.error("Add at least one line item.")
                else:
                    try:
                        db.save_purchase_return(header, lines)
                        ff.finish_new_entry("pr", message="Purchase return saved.")
                    except Exception as e:
                        st.error(str(e))

    elif _pr_tab == "Edit":
        party_opts = supplier_options()
        rid, _ = txn.document_picker(
            "pr_edit", db.search_purchase_returns,
            lambda r: f"{r['return_no']} — {r['supplier_name']} ({r['return_date']})",
            "Supplier", party_opts, "supplier_id",
        )
        if not rid:
            return
        ret = db.get_purchase_return(rid)
        st.markdown("##### Print / Gate Pass")
        c1, c2 = st.columns(2)
        with c1:
            document_print_toolbar("Purchase Return", rid, key_prefix=f"pr_edit_doc_{rid}")
            if ret.get("purchase_id"):
                document_print_toolbar(
                    "Purchase Invoice", ret["purchase_id"], key_prefix=f"pr_edit_inv_{rid}",
                )
        with c2:
            if ret.get("purchase_id"):
                invoice_gate_pass_panel("purchase", ret["purchase_id"], key_prefix=f"pr_edit_gp_{rid}")
            else:
                st.caption("No linked purchase invoice for gate pass.")
        st.divider()
        sup_opts = supplier_options()
        items_dict = item_options()
        sup_lbl = next((k for k, v in sup_opts.items() if v == ret["supplier_id"]), list(sup_opts.keys())[0])
        with st.form("edit_pr_hdr"):
            ret_no = st.text_input("Return No", value=ret["return_no"])
            sup = st.selectbox("Supplier", list(sup_opts.keys()), index=list(sup_opts.keys()).index(sup_lbl) if sup_lbl in sup_opts else 0)
            rdate = st.date_input("Date", value=date.fromisoformat(ret["return_date"]))
            notes = st.text_input("Notes", value=ret["notes"] or "")
            load = st.form_submit_button("Load for Edit")
        if ff.edit_panel_active("pr_edit", rid, load_clicked=load):
            if load:
                _seed_pr_edit(ret, sup_opts, sup=sup, ret_no=ret_no, rdate=rdate, notes=notes, from_form=True)
            elif ff.consume_edit_reload("pr_edit", rid):
                ret = db.get_purchase_return(rid)
                _seed_pr_edit(ret, sup_opts)
            header = st.session_state.get("pr_edit_header", {})
            header["purchase_id"] = txn.linked_invoice_picker(
                "pr_edit_lnk", db.search_purchases, header.get("supplier_id"), "supplier_id",
                lambda r: f"{r['invoice_no']} - {r['supplier_name']}",
            )
            if header.get("purchase_id") and st.button("Reload lines from invoice", key="pr_edit_load"):
                try:
                    lines, _ = hlp.return_lines_from_invoice(header["purchase_id"], "purchase")
                    st.session_state["pr_edit_lines"] = hlp._pad_line_rows(lines)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "pr_edit", st.session_state.get("pr_edit_lines", []),
                show_weight=True, party_id=header.get("supplier_id") or ret.get("supplier_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "pr_edit_tax", lines, header,
                party_id=header.get("supplier_id") or ret.get("supplier_id"),
                party_kind="purchase",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {fmt_money(totals['total'])}")
            c1, c2 = st.columns(2)
            if c1.button("Update Return", key="upd_pr"):
                if lines:
                    try:
                        db.save_purchase_return(header, lines, return_id=rid)
                        ff.finish_edit_refresh("pr_edit", rid, "pr_edit", "Updated.")
                    except Exception as e:
                        st.error(str(e))
            if c2.button("Delete Return", key="del_pr"):
                db.delete_purchase_return(rid)
                ff.finish_after_delete("pr_edit", "pr_edit")


# ---------------------------------------------------------------------------
# Sale Return
# ---------------------------------------------------------------------------
def page_sale_return():
    from erp_ui.helpers import sticky_page_tabs
    from erp_ui.document_print import document_print_toolbar
    from erp_ui.gatepass_pages import invoice_gate_pass_panel

    peek = st.session_state.get("sr_page_tab") or "Register"
    hlp.std_page_header(
        "Sales Returns",
        subtitle="Register · Open · New · Edit — print, linked invoice & gate pass",
        status="register" if peek == "Register" else ("draft" if peek == "New" else None),
        status_kind="shell" if peek == "Register" else "invoice",
    )
    _sr_tab = sticky_page_tabs(
        ["Register", "Open", "New", "Edit"],
        "sr_page_tab",
        open_alias_key="sr_open_tab",
    )

    if _sr_tab == "Register":
        def _sr_actions(row):
            inv_id = row.get("sale_id")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Print return**")
                document_print_toolbar("Sale Return", row["id"], key_prefix=f"sr_doc_{row['id']}")
                if inv_id:
                    st.markdown("**Print linked invoice**")
                    st.caption(f"Invoice: {row.get('invoice_no') or inv_id}")
                    ptype = st.selectbox(
                        "Invoice format", ["Sales Invoice", "Sales Tax Invoice"],
                        key=f"sr_inv_print_type_{row['id']}",
                    )
                    document_print_toolbar(ptype, inv_id, key_prefix=f"sr_inv_{row['id']}")
                else:
                    st.caption("No sales invoice linked to this return.")
            with c2:
                st.markdown("**Gate pass (via linked invoice)**")
                if inv_id:
                    invoice_gate_pass_panel("sales", inv_id, key_prefix=f"sr_gp_{row['id']}")
                else:
                    st.caption("Link a sales invoice on the return to manage gate pass here.")

        txn.sale_return_register_list(action_panel=_sr_actions)

    elif _sr_tab == "Open":
        from erp_ui.document_hub import render_document_hub
        render_document_hub("sales_return", "sr_hub")

    elif _sr_tab == "New":
        cust_opts = customer_options()
        items_dict = item_options()
        if not cust_opts or not items_dict:
            st.warning("Add customers and items first.")
            return
        with st.form("new_sal_ret"):
            default_ret = (st.session_state.get("sr_header") or {}).get("return_no") or db.peek_invoice("SR", "sales_returns", "return_no")
            ret_no = st.text_input("Return No", value=default_ret)
            cust_labels, blank = hlp.options_with_blank(cust_opts.keys())
            cust_lbl = st.selectbox("Customer", cust_labels)
            submitted_hdr = st.form_submit_button("Continue")
        if submitted_hdr:
            if not hlp.require_selected("customer", cust_lbl, blank):
                return
            cust_id = cust_opts[cust_lbl]
            st.session_state["sr_header"] = {
                "return_no": ret_no, "customer_id": cust_id,
                "return_date": str(date.today()), "notes": "",
            }
            st.session_state["sr_lines"] = [{"item_id": None, "quantity": 1.0, "rate": 0.0, "amount": 0.0}]
        if "sr_lines" in st.session_state:
            header = st.session_state.get("sr_header", {})
            cust_id = header.get("customer_id")
            rdate = st.date_input("Return Date", value=date.fromisoformat(header.get("return_date", str(date.today()))), key="sr_new_dt")
            notes = st.text_input("Notes", value=header.get("notes") or "", key="sr_new_notes")
            header["return_date"] = str(rdate)
            header["notes"] = notes
            sale_id = txn.linked_invoice_picker(
                "sr_new", db.search_sales_invoices, header["customer_id"], "customer_id",
                lambda r: f"{r['invoice_no']} - {r['customer_name']}",
                label="Linked sale (optional)",
            )
            header["sale_id"] = sale_id
            if sale_id and st.button("Load lines from sales invoice", key="sr_load_inv"):
                try:
                    lines, inv = hlp.return_lines_from_invoice(sale_id, "sale")
                    st.session_state["sr_lines"] = lines
                    ff.action_done(f"Loaded {len(lines)} line(s) from **{inv['invoice_no']}**.")
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "sr", show_weight=True, party_id=header.get("customer_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "sr_tax", lines, header,
                party_id=header.get("customer_id"), party_kind="sale",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {fmt_money(totals['total'])}")
            if st.button("Save Sale Return", key="save_sr"):
                if not lines:
                    st.error("Add at least one line item.")
                else:
                    try:
                        db.save_sale_return(header, lines)
                        ff.finish_new_entry("sr", message="Sale return saved.")
                    except Exception as e:
                        st.error(str(e))

    elif _sr_tab == "Edit":
        party_opts = customer_options()
        rid, _ = txn.document_picker(
            "sr_edit", db.search_sale_returns,
            lambda r: f"{r['return_no']} — {r['customer_name']} ({r['return_date']})",
            "Customer", party_opts, "customer_id",
        )
        if not rid:
            return
        ret = db.get_sale_return(rid)
        st.markdown("##### Print / Gate Pass")
        c1, c2 = st.columns(2)
        with c1:
            document_print_toolbar("Sale Return", rid, key_prefix=f"sr_edit_doc_{rid}")
            if ret.get("sale_id"):
                ptype = st.selectbox(
                    "Invoice format", ["Sales Invoice", "Sales Tax Invoice"],
                    key=f"sr_edit_inv_type_{rid}",
                )
                document_print_toolbar(ptype, ret["sale_id"], key_prefix=f"sr_edit_inv_{rid}")
        with c2:
            if ret.get("sale_id"):
                invoice_gate_pass_panel("sales", ret["sale_id"], key_prefix=f"sr_edit_gp_{rid}")
            else:
                st.caption("No linked sales invoice for gate pass.")
        st.divider()
        cust_opts = customer_options()
        items_dict = item_options()
        cust_lbl = next((k for k, v in cust_opts.items() if v == ret["customer_id"]), list(cust_opts.keys())[0])
        with st.form("edit_sr_hdr"):
            ret_no = st.text_input("Return No", value=ret["return_no"])
            cust = st.selectbox("Customer", list(cust_opts.keys()), index=list(cust_opts.keys()).index(cust_lbl) if cust_lbl in cust_opts else 0)
            rdate = st.date_input("Date", value=date.fromisoformat(ret["return_date"]))
            notes = st.text_input("Notes", value=ret["notes"] or "")
            load = st.form_submit_button("Load for Edit")
        if ff.edit_panel_active("sr_edit", rid, load_clicked=load):
            if load:
                _seed_sr_edit(ret, cust_opts, cust=cust, ret_no=ret_no, rdate=rdate, notes=notes, from_form=True)
            elif ff.consume_edit_reload("sr_edit", rid):
                ret = db.get_sale_return(rid)
                _seed_sr_edit(ret, cust_opts)
            header = st.session_state.get("sr_edit_header", {})
            header["sale_id"] = txn.linked_invoice_picker(
                "sr_edit_lnk", db.search_sales_invoices, header.get("customer_id"), "customer_id",
                lambda r: f"{r['invoice_no']} - {r['customer_name']}",
                label="Linked sale (optional)",
            )
            if header.get("sale_id") and st.button("Reload lines from invoice", key="sr_edit_load"):
                try:
                    lines, _ = hlp.return_lines_from_invoice(header["sale_id"], "sale")
                    st.session_state["sr_edit_lines"] = hlp._pad_line_rows(lines)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            header.setdefault("tax_rate_id", db.default_tax_rate_id())
            header.setdefault("discount_pct", 0)
            lines, subtotal = hlp.smart_line_item_editor(
                items_dict, "sr_edit", st.session_state.get("sr_edit_lines", []),
                show_weight=True, party_id=header.get("customer_id") or ret.get("customer_id"),
                default_discount_pct=float(header.get("discount_pct") or 0),
            )
            tax_hdr, totals = hlp.invoice_tax_form(
                "sr_edit_tax", lines, header,
                party_id=header.get("customer_id") or ret.get("customer_id"),
                party_kind="sale",
            )
            header.update(tax_hdr)
            st.write(f"**Net Return:** {fmt_money(totals['total'])}")
            c1, c2 = st.columns(2)
            if c1.button("Update Return", key="upd_sr"):
                if lines:
                    try:
                        db.save_sale_return(header, lines, return_id=rid)
                        ff.finish_edit_refresh("sr_edit", rid, "sr_edit", "Updated.")
                    except Exception as e:
                        st.error(str(e))
            if c2.button("Delete Return", key="del_sr"):
                db.delete_sale_return(rid)
                ff.finish_after_delete("sr_edit", "sr_edit")


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
    hlp.std_page_header("Stock Report", status="register", status_kind="shell")
    st.caption("View stock **item-wise**, **group-wise**, or **BOM / composition-wise**.")

    from erp_ui.helpers import form_compact, master_group_filter, render_stock_report_item_table
    from application.data_gateway import COMPOSITION_TYPES

    with form_compact("stock_rpt"):
        c1, c2, c3 = st.columns([1.8, 1.3, 1.3])
        view = c1.radio(
            "View",
            ["Item wise", "Group wise", "BOM wise"],
            horizontal=True,
            key="stock_rpt_view",
        )
        with c2:
            gid = master_group_filter("product", "sr") if view != "BOM wise" else None
        sort_opts = {
            "Item wise": ["Code", "Name", "Stock qty", "Stock value", "Status"],
            "Group wise": ["Group code", "Group name", "Items", "Stock value"],
            "BOM wise": ["BOM", "Finished code", "Role", "Item code", "Stock qty", "Stock value"],
        }
        sort_by = c3.selectbox("Sort by", sort_opts[view], key=f"stock_rpt_sort_{view}")

        q = st.text_input(
            "Search",
            key="stock_rpt_q",
            placeholder="Code, name, group, BOM…",
        ).strip().lower()

        bom_type = None
        bom_status = "approved"
        if view == "BOM wise":
            b1, b2 = st.columns(2)
            type_opts = {"All compositions": None}
            for code, label in COMPOSITION_TYPES.items():
                type_opts[label] = code
            bom_lbl = b1.selectbox("Composition type", list(type_opts.keys()), key="stock_rpt_bom_type")
            bom_type = type_opts[bom_lbl]
            bom_status = b2.selectbox(
                "BOM status",
                ["approved", "All", "draft", "inactive"],
                key="stock_rpt_bom_st",
            )

    if view == "Item wise":
        rows = db.get_stock_report(product_group_id=gid)
        if q:
            rows = [
                r for r in rows
                if q in " ".join(
                    str(r.get(k) or "") for k in ("code", "name", "category", "group_code", "group_name", "item_type")
                ).lower()
            ]
        sort_key = {
            "Code": lambda r: str(r.get("code") or ""),
            "Name": lambda r: str(r.get("name") or "").lower(),
            "Stock qty": lambda r: float(r.get("stock_qty") or 0),
            "Stock value": lambda r: float(r.get("stock_value") or 0),
            "Status": lambda r: str(r.get("status") or ""),
        }[sort_by]
        reverse = sort_by in ("Stock qty", "Stock value")
        rows = sorted(rows, key=sort_key, reverse=reverse)

        if not rows:
            st.info("No stock data for this view.")
            return
        low_n = sum(1 for r in rows if (r.get("status") or "OK") == "Low")
        neg_n = sum(1 for r in rows if float(r.get("stock_qty") or 0) < 0)
        total_val = sum(float(r.get("stock_value") or 0) for r in rows)
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Items</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Stock Value</p>"
            f"<p class='txn-kpi-val'>{fmt_money(total_val)}</p></div>",
            unsafe_allow_html=True,
        )
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Below Reorder</p>"
            f"<p class='txn-kpi-val'>{low_n:,}</p></div>",
            unsafe_allow_html=True,
        )
        if low_n or neg_n:
            parts = []
            if low_n:
                parts.append(
                    f'<span class="inv-badge inv-badge-pending">Low</span>&nbsp;<strong>{low_n}</strong>'
                )
            if neg_n:
                parts.append(
                    f'<span class="inv-badge inv-badge-rejected">Negative</span>&nbsp;<strong>{neg_n}</strong>'
                )
            st.markdown(
                f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
                unsafe_allow_html=True,
            )
        render_stock_report_item_table(rows)
        df = pd.DataFrame([{
            "Code": r.get("code"),
            "Name": r.get("name"),
            "Category": r.get("category") or "—",
            "Group": r.get("group_name") or "Unassigned",
            "Type": r.get("item_type") or "",
            "Unit": r.get("unit") or "",
            "Stock Qty": round(float(r.get("stock_qty") or 0), 4),
            "Unit Cost": round(float(r.get("unit_cost") or r.get("purchase_price") or 0), 2),
            "Stock Value": round(float(r.get("stock_value") or 0), 2),
            "Reorder": round(float(r.get("reorder_level") or 0), 4),
            "Status": r.get("status") or "OK",
        } for r in rows])
        export_df(df, "stock_report_item", "Stock Report — Item wise")
        if low_n:
            st.warning(f"{low_n} item(s) below reorder level.")

    elif view == "Group wise":
        rows = db.get_stock_report_group_wise(product_group_id=gid)
        if q:
            rows = [
                r for r in rows
                if q in f"{r.get('group_code')} {r.get('group_name')}".lower()
            ]
        sort_key = {
            "Group code": lambda r: str(r.get("group_code") or ""),
            "Group name": lambda r: str(r.get("group_name") or "").lower(),
            "Items": lambda r: int(r.get("items") or 0),
            "Stock value": lambda r: float(r.get("stock_value") or 0),
        }[sort_by]
        reverse = sort_by in ("Items", "Stock value")
        rows = sorted(rows, key=sort_key, reverse=reverse)
        if not rows:
            st.info("No group stock data.")
            return
        total_val = sum(float(r.get("stock_value") or 0) for r in rows)
        low_groups = sum(1 for r in rows if int(r.get("low_items") or 0) > 0)
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Groups</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Stock Value</p>"
            f"<p class='txn-kpi-val'>{fmt_money(total_val)}</p></div>",
            unsafe_allow_html=True,
        )
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Groups with Low Items</p>"
            f"<p class='txn-kpi-val'>{low_groups:,}</p></div>",
            unsafe_allow_html=True,
        )
        from html import escape
        ths = "".join(
            f"<th>{h}</th>"
            for h in ("Group Code", "Group Name", "Items", "Stock Qty", "Stock Value", "Low Items")
        )
        body = []
        for r in rows:
            low_i = int(r.get("low_items") or 0)
            low_badge = (
                f'<span class="inv-badge inv-badge-pending">{low_i}</span>'
                if low_i
                else '<span class="inv-badge inv-badge-approved">0</span>'
            )
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('group_code') or ''))}</td>"
                f"<td>{escape(str(r.get('group_name') or ''))}</td>"
                f"<td class='txn-num'>{int(r.get('items') or 0):,}</td>"
                f"<td class='txn-num'>{float(r.get('stock_qty') or 0):,.4f}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('stock_value')))}</td>"
                f"<td class='txn-status-cell'>{low_badge}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        df = pd.DataFrame([{
            "Group Code": r.get("group_code"),
            "Group Name": r.get("group_name"),
            "Items": int(r.get("items") or 0),
            "Stock Qty": round(float(r.get("stock_qty") or 0), 4),
            "Stock Value": round(float(r.get("stock_value") or 0), 2),
            "Low Items": int(r.get("low_items") or 0),
        } for r in rows])
        export_df(df, "stock_report_group", "Stock Report — Group wise")

    else:  # BOM wise
        rows = db.get_stock_report_bom_wise(
            composition_type=bom_type,
            status=bom_status or "approved",
        )
        if q:
            rows = [
                r for r in rows
                if q in " ".join(
                    str(r.get(k) or "")
                    for k in ("bom_no", "finished_code", "finished_name", "code", "name", "composition_type")
                ).lower()
            ]
        sort_key = {
            "BOM": lambda r: str(r.get("bom_no") or ""),
            "Finished code": lambda r: str(r.get("finished_code") or ""),
            "Role": lambda r: str(r.get("role") or ""),
            "Item code": lambda r: str(r.get("code") or ""),
            "Stock qty": lambda r: float(r.get("stock_qty") or 0),
            "Stock value": lambda r: float(r.get("stock_value") or 0),
        }[sort_by]
        reverse = sort_by in ("Stock qty", "Stock value")
        # Stable: keep BOM then role (Finished first) when sorting by BOM/finished
        if sort_by in ("BOM", "Finished code"):
            rows = sorted(
                rows,
                key=lambda r: (
                    sort_key(r),
                    0 if r.get("role") == "Finished" else 1,
                    str(r.get("code") or ""),
                ),
                reverse=reverse,
            )
        else:
            rows = sorted(rows, key=sort_key, reverse=reverse)

        if not rows:
            st.info("No BOM / composition stock data. Approve compositions under Production → BOM.")
            return
        fg_val = sum(float(r.get("stock_value") or 0) for r in rows if r.get("role") == "Finished")
        k1, k2, k3 = st.columns(3, gap="small")
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>BOM Lines</p>"
            f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Finished Goods Value</p>"
            f"<p class='txn-kpi-val'>{fmt_money(fg_val)}</p></div>",
            unsafe_allow_html=True,
        )
        bom_n = len({r.get("bom_no") for r in rows if r.get("bom_no")})
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Compositions</p>"
            f"<p class='txn-kpi-val'>{bom_n:,}</p></div>",
            unsafe_allow_html=True,
        )
        from html import escape
        ths = "".join(
            f"<th>{h}</th>"
            for h in (
                "BOM", "Ver", "Composition", "Finished", "Role", "Item",
                "BOM Qty", "Unit", "Stock Qty", "Unit Cost", "Stock Value",
            )
        )
        body = []
        for r in rows:
            role = r.get("role") or ""
            role_badge = (
                '<span class="inv-badge inv-badge-approved">Finished</span>'
                if role == "Finished"
                else f'<span class="inv-badge inv-badge-draft">{escape(role)}</span>'
            )
            body.append(
                "<tr>"
                f"<td>{escape(str(r.get('bom_no') or ''))}</td>"
                f"<td>{escape(str(r.get('version') or ''))}</td>"
                f"<td>{escape(str(r.get('composition_type') or ''))}</td>"
                f"<td>{escape(str(r.get('finished_code') or ''))} — {escape(str(r.get('finished_name') or ''))}</td>"
                f"<td class='txn-status-cell'>{role_badge}</td>"
                f"<td>{escape(str(r.get('code') or ''))} — {escape(str(r.get('name') or ''))}</td>"
                f"<td class='txn-num'>{float(r.get('bom_qty') or 0):,.4f}</td>"
                f"<td>{escape(str(r.get('unit') or ''))}</td>"
                f"<td class='txn-num'>{float(r.get('stock_qty') or 0):,.4f}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('unit_cost')))}</td>"
                f"<td class='txn-num'>{escape(fmt_money(r.get('stock_value')))}</td>"
                "</tr>"
            )
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        df = pd.DataFrame([{
            "BOM": r.get("bom_no"),
            "Ver": r.get("version"),
            "Composition": r.get("composition_type"),
            "Finished Code": r.get("finished_code"),
            "Finished Name": r.get("finished_name"),
            "Role": r.get("role"),
            "Item Code": r.get("code"),
            "Item Name": r.get("name"),
            "BOM Qty": round(float(r.get("bom_qty") or 0), 4),
            "Unit": r.get("unit") or "",
            "Stock Qty": round(float(r.get("stock_qty") or 0), 4),
            "Unit Cost": round(float(r.get("unit_cost") or 0), 2),
            "Stock Value": round(float(r.get("stock_value") or 0), 2),
        } for r in rows])
        export_df(df, "stock_report_bom", "Stock Report — BOM wise")


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
    from erp_ui.helpers import render_stock_kpi_strip

    hlp.std_page_header("Stock", status="register", status_kind="shell")
    rows = db.get_inventory()
    if not rows:
        st.info("No inventory data.")
        return

    render_stock_kpi_strip(rows)

    q = st.text_input(
        "Search stock / item",
        key="stock_page_search",
        placeholder="Type code, name, category, or unit…",
    ).strip()
    filtered = hlp.filter_master_records(rows, q) if q else rows
    filtered = sorted(filtered, key=lambda r: hlp.natural_code_sort_key(r.get("code")))

    c_f1, c_f2, c_f3 = st.columns([1, 1, 2])
    only_neg = c_f1.checkbox("Negative qty only", key="stock_page_neg", value=False)
    only_pos = c_f2.checkbox("Positive qty only", key="stock_page_pos", value=False)
    if only_neg:
        filtered = [r for r in filtered if float(r.get("stock_qty") or 0) < 0]
    elif only_pos:
        filtered = [r for r in filtered if float(r.get("stock_qty") or 0) > 0]

    if q:
        st.caption(f"**{len(filtered):,}** match(es) of **{len(rows):,}** items")
    else:
        st.caption(f"Showing **{len(filtered):,}** items — type above to search")

    if not filtered:
        st.warning("No items match this search.")
        return

    df = pd.DataFrame(filtered)[
        ["code", "name", "category", "unit", "stock_qty", "purchase_price", "reorder_level"]
    ]
    df["stock_value"] = df["stock_qty"] * df["purchase_price"]
    df.columns = ["Code", "Name", "Category", "Unit", "Qty", "Cost Price", "Reorder Level", "Stock Value"]

    sel_key = "stock_page_sel_codes"
    editor_ver_key = "stock_page_editor_ver"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = []
    if editor_ver_key not in st.session_state:
        st.session_state[editor_ver_key] = 0

    shown_codes = set(df["Code"].astype(str).tolist())
    # Drop selections that are no longer in the filtered view
    st.session_state[sel_key] = [c for c in st.session_state[sel_key] if c in shown_codes]

    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("Select all shown", key="stock_page_sel_all"):
        st.session_state[sel_key] = list(df["Code"].astype(str))
        st.session_state[editor_ver_key] = int(st.session_state[editor_ver_key]) + 1
        st.rerun()
    if b2.button("Clear selection", key="stock_page_sel_clr"):
        st.session_state[sel_key] = []
        st.session_state[editor_ver_key] = int(st.session_state[editor_ver_key]) + 1
        st.rerun()
    b3.caption(f"Selected: **{len(st.session_state[sel_key])}**")

    # Checkbox column for multi-select download
    edit_df = df.copy()
    edit_df.insert(0, "Select", edit_df["Code"].astype(str).isin(st.session_state[sel_key]))
    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[c for c in edit_df.columns if c != "Select"],
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "Qty": st.column_config.NumberColumn(format="%.3f"),
            "Cost Price": st.column_config.NumberColumn(format="%.2f"),
            "Stock Value": st.column_config.NumberColumn(format="%.2f"),
        },
        key=f"stock_page_editor_{st.session_state[editor_ver_key]}",
    )
    picked = edited["Select"].fillna(False).astype(bool)
    st.session_state[sel_key] = edited.loc[picked, "Code"].astype(str).tolist()

    selected_codes = set(st.session_state[sel_key])
    df_selected = df[df["Code"].astype(str).isin(selected_codes)] if selected_codes else df.iloc[0:0]
    value_scope = df_selected if len(df_selected) else df
    scope_lbl = "selected" if len(df_selected) else "shown"
    st.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Stock Value ({scope_lbl})</p>"
        f"<p class='txn-kpi-val'>{fmt_money(value_scope['Stock Value'].sum())}</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown("**Download**")
    d1, d2 = st.columns(2)
    with d1:
        st.caption("Selected items" if len(df_selected) else "Select rows above (or Select all shown)")
        if len(df_selected):
            hlp.export_buttons(df_selected, "stock_selected", title="Stock — Selected Items")
        else:
            st.info("Tick items to download a selection.")
    with d2:
        st.caption("All shown (search / filter result)")
        hlp.export_buttons(df, "stock_filtered", title="Stock — Filtered List")


def page_stock_adjustments():
    from erp_ui.helpers import sticky_page_tabs, render_adjustment_html_table

    hlp.std_page_header("Stock Adjustments")
    tab = sticky_page_tabs(["New Adjustment", "History"], "stock_adj_tab")
    if tab == "New Adjustment":
        _, item_id, item_row = hlp.smart_select("Product", db.get_items(), "adj_item", "id",
                                                lambda r: f"{r['code']} - {r['name']} ({r.get('stock_qty',0)})")
        if item_id:
            with st.form("stock_adjust"):
                adj_date = st.date_input("Date", value=date.today())
                adj_type = st.selectbox("Adjustment Type", ["in", "out"])
                qty = st.number_input("Quantity", min_value=0.01, value=1.0)
                reason = st.text_input("Reason")
                if st.form_submit_button("Apply Adjustment"):
                    db.add_inventory_adjustment(item_id, str(adj_date), adj_type, qty, reason)
                    ff.finish_new_entry(form_id="inv_adj", message="Stock adjusted.")
    elif tab == "History":
        hist = db.get_inventory_adjustments()
        if hist:
            render_adjustment_html_table(hist)
        else:
            st.info("No adjustments recorded.")


def page_stock_transfers():
    hlp.std_page_header("Stock Transfers", status="posted", status_kind="shell")
    wh_opts = hlp.warehouse_opts()
    if len(wh_opts) < 2:
        st.warning("Add at least two warehouses to transfer stock.")
        return
    with st.container(border=True):
        _, pid, _ = hlp.smart_select("Product", db.get_items(), "xfer_prod", "id",
                                     lambda r: f"{r['code']} - {r['name']}")
        wh_keys = list(wh_opts.keys())
        c1, c2 = st.columns(2)
        from_wh = c1.selectbox("From Warehouse", wh_keys)
        to_wh = c2.selectbox("To Warehouse", wh_keys)
        qty = st.number_input("Quantity", min_value=0.01, value=1.0)
        xfer_date = st.date_input("Transfer Date", value=date.today())
        if st.button("Transfer Stock", type="primary") and pid and from_wh != to_wh:
            db.add_inventory_adjustment(pid, str(xfer_date), "out", qty, f"Transfer to {to_wh}")
            db.add_inventory_adjustment(pid, str(xfer_date), "in", qty, f"Transfer from {from_wh}")
            ff.action_done("Transfer recorded.")


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
