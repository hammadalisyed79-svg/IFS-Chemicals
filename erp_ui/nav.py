"""Navigation groups and screen permission checks (shared — no Streamlit page config)."""

from application import data_gateway as db

_SIDEBAR_FILTER_MIN = 7
_NAV_GRID_COLS_GROUPS = 3
_NAV_GRID_COLS_SCREENS = 2

# ---------------------------------------------------------------------------
# Professional display names (internal keys in NAV_GROUPS / PAGES stay stable)
# ---------------------------------------------------------------------------
MODULE_TITLES = {
    "Overview": "Executive",
    "Masters": "Master Data",
    "Sales": "Sales",
    "Purchases": "Purchasing",
    "Inventory": "Inventory",
    "Production": "Manufacturing",
    "Finance": "Financial Accounting",
    "HR": "Human Resources",
    "Weight Scale": "Weighbridge",
    "Gate Pass": "Gate Control",
    "Reports": "Reports & Analytics",
    "Administration": "System Administration",
}

MODULE_TAGLINES = {
    "Overview": "Executive KPIs and business health",
    "Masters": "Customers, suppliers, products & warehouses",
    "Sales": "Orders, invoices, returns & approvals",
    "Purchases": "POs, GRN, bills, returns & approvals",
    "Inventory": "Stock positions, adjustments & reports",
    "Production": "BOM, production orders & plant operations",
    "Finance": "Cash, bank, ledgers & financial statements",
    "HR": "Attendance, leave, payroll & advances",
    "Weight Scale": "Weighbridge tickets & weight reports",
    "Gate Pass": "Inbound and outbound gate passes",
    "Reports": "Operational and management reports",
    "Administration": "Users, roles, settings & system tools",
}

SCREEN_TITLES = {
    "Dashboard": "Home",
    "Business Overview": "Business Intelligence",
    "Customers": "Customer",
    "Suppliers": "Supplier",
    "Products": "Product",
    "Account & Item Groups": "Groups",
    "Warehouses": "Warehouse",
    "Employees": "Employee",
    "Price Lists": "Price List",
    "Product Categories": "Product Category",
    "Units of Measure": "Unit of Measure",
    "Departments": "Department",
    "Tax Rates": "Tax Rate",
    "Payment Terms": "Payment Term",
    "Vehicles": "Vehicle",
    "Delivery Notes": "Delivery Note",
    "Batch Stock": "Batch Stock",
    "Weight Slips": "Weight Slip",
    "General Ledger": "General Ledger",
    "Tax Report": "Tax Report",
    "Sales Invoices": "Sale",
    "Sale Approval": "Sale Approval",
    "Sales Returns": "Sale Return",
    "Sales Orders": "Sale Order",
    "Quotations": "Quotation",
    "Distributor Orders": "Distributor Orders",
    "Distribution": "Distribution",
    "Purchase Invoices": "Purchase",
    "Purchase Approval": "Purchase Approval",
    "Purchase Returns": "Purchase Return",
    "GRN": "GRN",
    "Purchase Orders": "Purchase Order",
    "Stock": "Stock",
    "Stock Adjustments": "Stock Adjustment",
    "Stock Revaluation": "Stock Revaluation",
    "Stock Report": "Stock Report",
    "BOM": "BOM",
    "Daily Production": "Daily Production",
    "Production Orders": "Production Order",
    "Job Cards": "Job Card",
    "Machines": "Machine",
    "Formula Master": "Formula",
    "Spray Dryer": "Spray Dryer",
    "Batch Manufacturing": "Batch",
    "Chemical Reactor": "Reactor",
    "Corrugated Production": "Corrugated",
    "Gravure / Packaging": "Gravure",
    "PET Bottle Blowing": "PET Blowing",
    "QC Laboratory": "QC Lab",
    "Plant Maintenance": "Maintenance",
    "Energy Management": "Energy",
    "Industrial Costing": "Costing",
    "Toll Manufacturing": "Toll Mfg",
    "Industrial Warehouse": "Ind. Warehouse",
    "Dispatch Planning": "Dispatch Plan",
    "Industrial Dashboards": "Plant Dashboard",
    "Industrial Reports": "Plant Reports",
    "Cash Book": "Cash Book",
    "Bank Book": "Bank Book",
    "Customer Receipt": "Customer Receipt",
    "Supplier Payment": "Supplier Payment",
    "Expense Payment": "Expense Payment",
    "Expense Bill": "Expense Bill",
    "Cash Advance": "Cash Advance",
    "Party Transfer": "Party Transfer",
    "Chart of Accounts": "Chart of Accounts",
    "Journal Voucher": "Journal",
    "Customer Ledger": "Customer Ledger",
    "Supplier Ledger": "Supplier Ledger",
    "Account Ledger": "Account Ledger",
    "Trial Balance": "Trial Balance",
    "Profit & Loss Report": "Profit & Loss",
    "Balance Sheet": "Balance Sheet",
    "Fiscal Year Closing": "Year Closing",
    "Attendance": "Attendance",
    "Leave Management": "Leave",
    "Payroll": "Payroll",
    "Employee Advances": "Advance",
    "Employee Ledger": "Employee Ledger",
    "Weight Entry": "Weight Entry",
    "Weight Reports": "Weight Report",
    "Gate Pass Entry": "Gate Pass",
    "Reports Center": "Reports",
    "Customer Outstanding": "Cust. Outstanding",
    "Customer Due Aging": "Cust. Due Aging",
    "Supplier Outstanding": "Supp. Outstanding",
    "User Management": "Users",
    "Roles & Permissions": "Roles",
    "System Settings": "Settings",
    "Holidays": "Holidays",
    "Draft Center": "Drafts",
    "Approval Designer": "Approvals Setup",
    "Mobile Approvals": "Mobile Approve",
    "Download App": "Download App",
    "ERP Health Check": "Health Check",
    "Audit Log": "Audit Log",
    "Backup & Restore": "Backup",
}

SCREEN_TAGLINES = {
    "Dashboard": "Main workspace",
    "Business Overview": "Live KPIs and alerts",
    "Customers": "Create and maintain records",
    "Suppliers": "Create and maintain records",
    "Products": "Items, rates and codes",
    "Account & Item Groups": "Classify accounts and products",
    "Warehouses": "Define storage locations",
    "Employees": "HR employee master",
    "Price Lists": "Pricing policies",
    "Product Categories": "Classify finished goods and materials",
    "Units of Measure": "Kg, litre, piece and other units",
    "Departments": "Organisational departments",
    "Tax Rates": "Sales tax and other rates",
    "Payment Terms": "Credit days and terms",
    "Vehicles": "Fleet and transport vehicles",
    "Delivery Notes": "Outbound delivery documents",
    "Batch Stock": "Batch-wise inventory view",
    "Weight Slips": "Weighbridge slip register",
    "General Ledger": "Full GL enquiry",
    "Tax Report": "Tax summaries and returns",
    "Sales Invoices": "Issue and manage",
    "Sale Approval": "Review and approve",
    "Sales Returns": "Process customer returns",
    "Sales Orders": "Capture confirmed orders",
    "Quotations": "Prepare and track",
    "Distributor Orders": "Portal order handling",
    "Distribution": "Per-customer portal product lists & prices",
    "Purchase Invoices": "Record supplier bills",
    "Purchase Approval": "Review and approve",
    "Purchase Returns": "Returns to suppliers",
    "GRN": "Inbound goods receipts",
    "Purchase Orders": "Raise and track orders",
    "Stock": "On-hand by warehouse",
    "Stock Adjustments": "Correct quantities",
    "Stock Revaluation": "Revalue on-hand stock",
    "Stock Report": "Valuation and movement",
    "Daily Production": "Post FG output",
    "BOM": "Composition formulas",
    "Production Orders": "Issue materials / receive FG",
    "Job Cards": "Shop-floor execution",
    "Machines": "Plant machine master",
    "Formula Master": "Process formulas",
    "Spray Dryer": "Production entries",
    "Batch Manufacturing": "Batch tracking",
    "Chemical Reactor": "Reactor batches",
    "Corrugated Production": "Line production",
    "Gravure / Packaging": "Packaging runs",
    "PET Bottle Blowing": "Blowing production",
    "QC Laboratory": "Tests and inspections",
    "Plant Maintenance": "Work orders",
    "Energy Management": "Utilities consumption",
    "Industrial Costing": "Product costing",
    "Toll Manufacturing": "Third-party jobs",
    "Industrial Warehouse": "Material warehouse",
    "Dispatch Planning": "Combine SO requirements & net weight by destination",
    "Industrial Dashboards": "Plant performance",
    "Industrial Reports": "Manufacturing analysis",
    "Cash Book": "Receipts and payments",
    "Bank Book": "Deposits and cheques",
    "Customer Receipt": "Receive payments",
    "Supplier Payment": "Pay outstanding",
    "Expense Payment": "Operating expenses",
    "Expense Bill": "Multi expense heads / one bill",
    "Cash Advance": "Rider/driver float → settle bills later",
    "Party Transfer": "Balance transfers",
    "Chart of Accounts": "General ledger chart",
    "Journal Voucher": "Manual journals",
    "Customer Ledger": "AR statement",
    "Supplier Ledger": "AP statement",
    "Account Ledger": "GL account statement",
    "Trial Balance": "Period balances",
    "Profit & Loss Report": "Income statement",
    "Balance Sheet": "Financial position",
    "Fiscal Year Closing": "Close and carry forward",
    "Attendance": "Daily attendance",
    "Leave Management": "Requests and approvals",
    "Payroll": "Salary runs",
    "Employee Advances": "Advances and recoveries",
    "Employee Ledger": "Staff ledger",
    "Weight Entry": "Weighbridge tickets",
    "Weight Reports": "History and summaries",
    "Gate Pass Entry": "Issue and close",
    "Reports Center": "Report library",
    "User Management": "Users and roles",
    "Roles & Permissions": "Module access",
    "System Settings": "Company options",
    "Holidays": "Holiday calendar",
    "Draft Center": "Unfinished documents",
    "Approval Designer": "Approval flows",
    "Mobile Approvals": "Approve on mobile",
    "Download App": "Windows client shortcut",
    "ERP Health Check": "System diagnostics",
    "Audit Log": "Change history",
    "Backup & Restore": "Backup tools",
}


def module_title(group: str) -> str:
    return MODULE_TITLES.get(group, group)


def module_tagline(group: str) -> str:
    return MODULE_TAGLINES.get(group, f"{module_title(group)} module")


def screen_title(screen: str) -> str:
    return SCREEN_TITLES.get(screen, screen)


def screen_tagline(screen: str) -> str:
    return SCREEN_TAGLINES.get(screen, screen_title(screen))


GROUP_ICONS = {
    "Overview": "📊",
    "Masters": "📚",
    "Sales": "🛒",
    "Purchases": "📥",
    "Inventory": "📦",
    "Production": "🏭",
    "Finance": "💰",
    "HR": "👥",
    "Weight Scale": "⚖️",
    "Gate Pass": "🚪",
    "Reports": "📈",
    "Administration": "⚙️",
}

# Odoo-style app tile colours — red / blue brand only
GROUP_COLORS = {
    "Overview": ("#DBEAFE", "#1D4ED8"),
    "Masters": ("#FFFFFF", "#1D4ED8"),
    "Sales": ("#FEE2E2", "#DC2626"),
    "Purchases": ("#DBEAFE", "#1D4ED8"),
    "Inventory": ("#FFFFFF", "#1D4ED8"),
    "Production": ("#FEE2E2", "#DC2626"),
    "Finance": ("#DBEAFE", "#1D4ED8"),
    "HR": ("#FFFFFF", "#1D4ED8"),
    "Weight Scale": ("#FEE2E2", "#DC2626"),
    "Gate Pass": ("#DBEAFE", "#1D4ED8"),
    "Reports": ("#FFFFFF", "#1D4ED8"),
    "Administration": ("#FEE2E2", "#DC2626"),
}

SCREEN_COLORS = {
    "Dashboard": ("#DBEAFE", "#1D4ED8"),
    "Business Overview": ("#FEE2E2", "#DC2626"),
}

_ODOO_GRID_COLS = 4

SCREEN_ICONS = {
    "Dashboard": "📊",
    "Business Overview": "📈",
    "Customers": "👤",
    "Suppliers": "🏢",
    "Products": "📦",
    "Account & Item Groups": "🗂️",
    "Warehouses": "🏭",
    "Employees": "👥",
    "Sales Invoices": "🧾",
    "Sale Approval": "✅",
    "Sales Returns": "↩️",
    "Sales Orders": "📋",
    "Quotations": "💬",
    "Purchase Invoices": "🧾",
    "Purchase Approval": "✅",
    "Purchase Returns": "↩️",
    "GRN": "📥",
    "Purchase Orders": "📋",
    "Stock": "📦",
    "Stock Adjustments": "🔧",
    "Stock Revaluation": "💹",
    "Stock Report": "📊",
    "Daily Production": "🏭",
    "BOM": "🧪",
    "Stock Report": "📈",
    "BOM": "🧪",
    "Production Orders": "⚙️",
    "Job Cards": "📝",
    "Machines": "🔩",
    "Formula Master": "🧬",
    "Spray Dryer": "💨",
    "Batch Manufacturing": "🏷️",
    "Chemical Reactor": "⚗️",
    "Corrugated Production": "📦",
    "Gravure / Packaging": "🎨",
    "PET Bottle Blowing": "🍾",
    "QC Laboratory": "🔬",
    "Plant Maintenance": "🔧",
    "Energy Management": "⚡",
    "Industrial Costing": "💹",
    "Toll Manufacturing": "🤝",
    "Industrial Warehouse": "🏪",
    "Dispatch Planning": "🚚",
    "Industrial Dashboards": "📊",
    "Industrial Reports": "📋",
    "Cash Book": "💵",
    "Bank Book": "🏦",
    "Customer Receipt": "💳",
    "Supplier Payment": "💸",
    "Expense Payment": "🧾",
    "Expense Bill": "📑",
    "Cash Advance": "🪙",
    "Party Transfer": "🔁",
    "Chart of Accounts": "📒",
    "Journal Voucher": "📓",
    "Customer Ledger": "📖",
    "Supplier Ledger": "📖",
    "Account Ledger": "📖",
    "Trial Balance": "⚖️",
    "Profit & Loss Report": "📉",
    "Balance Sheet": "📊",
    "Fiscal Year Closing": "🔒",
    "Attendance": "📅",
    "Leave Management": "🏖️",
    "Payroll": "💰",
    "Employee Advances": "💵",
    "Employee Ledger": "📖",
    "Weight Entry": "⚖️",
    "Weight Reports": "📈",
    "Gate Pass Entry": "🚪",
    "Reports Center": "📊",
    "User Management": "👤",
    "Roles & Permissions": "🔐",
    "System Settings": "⚙️",
    "Holidays": "📅",
    "Audit Log": "📜",
    "Backup & Restore": "💾",
    "Draft Center": "📋",
    "ERP Health Check": "🩺",
    "Download App": "⬇️",
    "Approval Designer": "✅",
    "Mobile Approvals": "📱",
    "Price Lists": "💲",
    "Distributor Orders": "🏪",
    "Distribution": "📦",
}

NAV_GROUPS = {
    "Overview": ["Dashboard", "Business Overview", "Download App"],
    "Masters": ["Customers", "Suppliers", "Products", "Account & Item Groups", "Warehouses", "Employees", "Price Lists"],
    "Sales": ["Sales Invoices", "Sale Approval", "Sales Returns", "Sales Orders", "Quotations", "Distributor Orders", "Distribution"],
    "Purchases": ["Purchase Invoices", "Purchase Approval", "Purchase Returns", "GRN", "Purchase Orders"],
    "Inventory": ["Stock", "Stock Adjustments", "Stock Revaluation", "Stock Report"],
    "Production": ["BOM", "Daily Production", "Production Orders", "Job Cards",
                   "Corrugated Production", "Gravure / Packaging", "PET Bottle Blowing",
                   "Plant Maintenance", "Industrial Warehouse", "Dispatch Planning",
                   "Industrial Dashboards", "Industrial Reports"],
    "Finance": ["Cash Book", "Bank Book", "Customer Receipt", "Supplier Payment", "Expense Payment",
                "Expense Bill", "Cash Advance",
                "Party Transfer",
                "Chart of Accounts", "Journal Voucher",
                "Customer Ledger", "Supplier Ledger", "Account Ledger",
                "Trial Balance", "Profit & Loss Report", "Balance Sheet",
                "Fiscal Year Closing"],
    "HR": ["Employees", "Attendance", "Leave Management", "Payroll", "Employee Advances", "Employee Ledger"],
    "Weight Scale": ["Weight Entry", "Weight Reports"],
    "Gate Pass": ["Gate Pass Entry"],
    "Reports": ["Reports Center", "Customer Outstanding", "Customer Due Aging", "Supplier Outstanding"],
    "Administration": ["User Management", "Roles & Permissions", "System Settings", "Holidays",
                       "Draft Center", "Approval Designer", "Mobile Approvals",
                       "ERP Health Check", "Audit Log", "Backup & Restore"],
}

SCREEN_PERMISSION = {
    "Dashboard": "Dashboard",
    "Business Overview": "Dashboard",
    "Download App": "Dashboard",
    "Customers": "Masters", "Suppliers": "Masters", "Products": "Masters", "Items / Products": "Masters",
    "Product Categories": "Masters", "Account & Item Groups": "Masters", "Custom Groups": "Masters",
    "Units of Measure": "Masters",
    "Warehouses": "Masters",
    "Employees": "HR", "Employee Master": "HR", "Attendance": "HR", "Leave Management": "HR",
    "Payroll": "HR", "Employee Advances": "HR", "Employee Loans": "HR", "Employee Ledger": "HR",
    "Expense Claims": "HR",
    "Weight Entry": "Inventory", "Weight Reports": "Reports", "Weight Scale": "Inventory",
    "Gate Pass Entry": "Inventory",
    "Quotations": "Sales", "Sales Orders": "Sales", "Delivery Notes": "Sales",
    "Sales Invoices": "Sales", "Sale Approval": "Sales", "Sales": "Sales", "Sales Returns": "Sales", "Sale Return": "Sales",
    "Customer Outstanding": "Reports",
    "Customer Due Aging": "Reports",
    "Purchase Requisition": "Purchase", "Purchase Orders": "Purchase", "GRN": "Purchase",
    "Purchase Invoices": "Purchase", "Purchase Approval": "Purchase", "Purchases": "Purchase",
    "Purchase Returns": "Purchase", "Purchase Return": "Purchase",
    "Supplier Outstanding": "Reports",
    "Stock": "Inventory", "Inventory": "Inventory", "Stock Transfers": "Inventory",
    "Stock Adjustments": "Inventory", "Stock Revaluation": "Inventory",
    "Batch Stock": "Inventory", "Stock Report": "Reports",
    "Weight Slips": "Inventory",
    "BOM": "Production", "BOM / Formula": "Production", "Daily Production": "Production",
    "Production Orders": "Production", "Batch Manufacturing": "Production",
    "Job Cards": "Production", "Machines": "Production",
    "Formula Master": "Production", "Spray Dryer": "Production",
    "Chemical Reactor": "Production", "Corrugated Production": "Production",
    "Gravure / Packaging": "Production", "PET Bottle Blowing": "Production",
    "QC Laboratory": "Production", "Plant Maintenance": "Production",
    "Energy Management": "Production", "Industrial Costing": "Production",
    "Toll Manufacturing": "Production", "Industrial Warehouse": "Inventory",
    "Dispatch Planning": "Production",
    "Industrial Dashboards": "Production", "Industrial Reports": "Reports",
    "Journal Voucher": "Finance", "Cash Book": "Finance", "Bank Book": "Finance",
    "Chart of Accounts": "Finance", "Customer Ledger": "Finance", "Supplier Ledger": "Finance",
    "Account Ledger": "Finance",
    "Customer Receipt": "Finance", "Supplier Payment": "Finance", "Expense Payment": "Finance",
    "Expense Bill": "Finance",
    "Cash Advance": "Finance",
    "Party Transfer": "Finance",
    "General Ledger": "Finance", "Trial Balance": "Finance", "Profit & Loss Report": "Finance",
    "Balance Sheet": "Finance", "Tax Report": "Finance", "Fiscal Year Closing": "Finance",
    "Gate Pass Reports": "Reports",
    "Reports Center": "Reports", "HR Reports": "Reports",
    "User Management": "Admin", "Roles & Permissions": "Admin", "System Settings": "Admin",
    "Holidays": "Admin",
    "Draft Center": "Admin",
    "Approval Designer": "Admin",
    "ERP Health Check": "Admin",
    "Audit Log": "Admin",
    "Backup & Restore": "Admin",
    "Mobile Approvals": "Sales",
    "Price Lists": "PriceLists",
    "Distributor Orders": "Portal",
    "Distribution": "Portal",
}


def can_view_screen(user, screen):
    if not user:
        return False
    from erp_core.v15_security import is_portal_user
    if is_portal_user(user):
        return False
    if user.get("role") == "admin":
        return True
    module = SCREEN_PERMISSION.get(screen, "Masters")
    if module == "HR":
        return db.user_can(user, "HR", "view") or db.user_can(user, "Admin", "view")
    return db.user_can(user, module, "view")


def filtered_nav_groups(user):
    out = {}
    for group, screens in NAV_GROUPS.items():
        visible = [s for s in screens if can_view_screen(user, s)]
        if visible:
            out[group] = visible
    return out


def _icon_for(name: str, icons_map: dict) -> str:
    from erp_ui.icons import icon_for
    return icons_map.get(name) or icon_for(name, icons_map)


def _tile_colors(name: str, *, group: bool = True) -> tuple[str, str]:
    if group:
        return GROUP_COLORS.get(name, ("#4B5563", "#6B7280"))
    return SCREEN_COLORS.get(name, GROUP_COLORS.get(name, ("#4B5563", "#6B7280")))


def _home_group(nav: dict) -> str:
    """Module that owns the CEO Dashboard screen."""
    for group, screens in nav.items():
        if "Dashboard" in screens:
            return group
    return next(iter(nav))


def _clear_transient_nav() -> None:
    import streamlit as st

    for key in ("nav_group", "nav_screen", "launcher_group", "rpt_nav_to"):
        st.session_state.pop(key, None)


def reset_to_desktop(nav: dict) -> None:
    """Set session state for CEO home (caller may rerun)."""
    import streamlit as st

    _clear_transient_nav()
    st.session_state["sidebar_group"] = _home_group(nav)
    st.session_state["sidebar_screen"] = "Dashboard"


def request_nav(group: str, screen: str) -> None:
    """One-shot navigation (e.g. dashboard quick-launch)."""
    import streamlit as st

    st.session_state["nav_group"] = group
    st.session_state["nav_screen"] = screen
    st.rerun()


def go_home() -> None:
    import streamlit as st

    user = st.session_state.get("user")
    nav = filtered_nav_groups(user) if user else {}
    if nav:
        reset_to_desktop(nav)
    else:
        _clear_transient_nav()
        st.session_state["sidebar_screen"] = "Dashboard"
    st.rerun()


def go_module(group: str) -> None:
    import streamlit as st

    nav = filtered_nav_groups(st.session_state.get("user") or {})
    if group not in nav:
        go_home()
        return
    st.session_state.pop("nav_group", None)
    st.session_state.pop("nav_screen", None)
    st.session_state.pop("rpt_nav_to", None)
    st.session_state["sidebar_group"] = group
    st.session_state["launcher_group"] = group
    st.session_state["sidebar_screen"] = "Dashboard"
    st.rerun()


def go_screen(group: str, screen: str) -> None:
    import streamlit as st

    nav = filtered_nav_groups(st.session_state.get("user") or {})
    if group not in nav or screen not in nav.get(group, []):
        return
    st.session_state.pop("nav_group", None)
    st.session_state.pop("nav_screen", None)
    st.session_state["sidebar_group"] = group
    st.session_state["sidebar_screen"] = screen
    st.session_state.pop("launcher_group", None)
    try:
        from erp_ui.user_prefs import track_recent_screen
        track_recent_screen(group, screen)
    except Exception:
        pass
    st.rerun()


def apply_pending_nav(nav: dict) -> None:
    """Apply one-shot navigation from dashboard quick-launch."""
    import streamlit as st

    target_group = st.session_state.pop("nav_group", None)
    target_screen = st.session_state.pop("nav_screen", None)
    if not target_group or target_group not in nav:
        return
    st.session_state["sidebar_group"] = target_group
    screens = nav[target_group]
    if target_screen and target_screen in screens:
        st.session_state["sidebar_screen"] = target_screen
        if target_screen != "Dashboard":
            st.session_state.pop("launcher_group", None)
    elif screens:
        st.session_state["sidebar_screen"] = screens[0]


def sync_nav_state(nav: dict) -> None:
    import streamlit as st

    if not nav:
        return
    group_keys = list(nav.keys())

    if "sidebar_group" not in st.session_state or st.session_state["sidebar_group"] not in nav:
        st.session_state["sidebar_group"] = group_keys[0]

    screen = st.session_state.get("sidebar_screen")

    # CEO desktop — keep a group that actually contains Dashboard
    if screen == "Dashboard":
        if "Dashboard" not in nav.get(st.session_state["sidebar_group"], []):
            st.session_state["sidebar_group"] = _home_group(nav)
        st.session_state["sidebar_screen"] = "Dashboard"
    else:
        group = st.session_state["sidebar_group"]
        screens = nav[group]
        if screen not in screens:
            st.session_state["sidebar_screen"] = screens[0]

    launcher = st.session_state.get("launcher_group")
    if launcher and launcher not in nav:
        st.session_state.pop("launcher_group", None)


def render_odoo_tile_grid(
    items: list[str],
    key_prefix: str,
    icons_map: dict,
    on_pick,
    *,
    cols: int = _ODOO_GRID_COLS,
    color_for=None,
) -> None:
    """Odoo-style large desktop app icons in the main content area."""
    import streamlit as st

    if not items:
        st.info("No items available for your role.")
        return
    color_for = color_for or (lambda n: _tile_colors(n))
    with st.container(key=f"{key_prefix}_odoo_grid"):
        for row_start in range(0, len(items), cols):
            row = items[row_start: row_start + cols]
            columns = st.columns(cols)
            for col, item in zip(columns, row):
                with col:
                    icon = _icon_for(item, icons_map)
                    c1, c2 = color_for(item)
                    st.markdown(
                        f'<div class="erp-odoo-tile" style="'
                        f'background:linear-gradient(145deg,{c1} 0%,{c2} 100%);">'
                        f'<span class="erp-odoo-tile-icon">{icon}</span></div>'
                        f'<p class="erp-odoo-tile-label">{item}</p>',
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "Open",
                        key=f"{key_prefix}_{item}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        on_pick(item)


def render_apps_home(nav: dict, company: str) -> None:
    """Home screen — CEO-style dark desktop launcher."""
    import streamlit as st

    from erp_ui.desktop_home import render_ceo_desktop

    user = st.session_state.get("user") or {}
    render_ceo_desktop(nav, user, company)


def render_module_launcher(group: str, screens: list[str]) -> None:
    """Second level — screens inside a module (dark desktop theme)."""
    import streamlit as st
    from application import data_gateway as db

    from erp_ui.desktop_home import render_desktop_module_launcher

    user = st.session_state.get("user") or {}
    company = db.get_setting("company_name", "IFS Chemicals")
    nav = filtered_nav_groups(user)
    render_desktop_module_launcher(nav, user, company, group, screens)


def render_main_breadcrumb(nav: dict, group: str, screen: str) -> None:
    """Screen chips for switching within the active module."""
    import streamlit as st

    if screen == "Dashboard":
        return

    from erp_ui.desktop_home import render_module_screen_chips

    render_module_screen_chips(nav, group, screen)


def _render_nav_icon_grid(
    items: list[str],
    session_key: str,
    key_prefix: str,
    icons_map: dict,
    *,
    cols: int = 3,
    on_select=None,
    label_fn=None,
) -> str:
    """Desktop-style icon tiles; returns current session_key value."""
    import streamlit as st

    if not items:
        return st.session_state.get(session_key, "")
    current = st.session_state.get(session_key)
    if current not in items:
        current = items[0]
        st.session_state[session_key] = current

    with st.container(key=f"{key_prefix}_grid"):
        for row_start in range(0, len(items), cols):
            row = items[row_start: row_start + cols]
            columns = st.columns(cols)
            for col, item in zip(columns, row):
                with col:
                    icon = _icon_for(item, icons_map)
                    label = label_fn(item) if label_fn else item
                    st.markdown(
                        f'<p class="erp-nav-ico">{icon}</p>',
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        label,
                        key=f"{key_prefix}_{item}",
                        use_container_width=True,
                        type="primary" if item == current else "secondary",
                    ):
                        if item != current:
                            st.session_state[session_key] = item
                            if on_select:
                                on_select(item)
                            st.rerun()
    return st.session_state[session_key]


def render_sidebar_groups(group_keys: list[str], nav: dict) -> str:
    """Module groups as desktop-style icon tiles."""
    import streamlit as st

    def _on_group(g: str) -> None:
        screens = nav.get(g) or []
        if screens:
            st.session_state["sidebar_screen"] = screens[0]

    st.caption("Modules")
    return _render_nav_icon_grid(
        group_keys,
        "sidebar_group",
        "nav_grp",
        GROUP_ICONS,
        cols=_NAV_GRID_COLS_GROUPS,
        on_select=_on_group,
        label_fn=module_title,
    )


def render_sidebar_screen(screens: list[str]) -> str:
    """Screens in the active module as desktop-style icon tiles."""
    import streamlit as st

    visible = list(screens)
    if len(visible) >= _SIDEBAR_FILTER_MIN:
        q = st.text_input(
            "Find screen",
            key="sidebar_screen_filter",
            placeholder="Filter screens…",
            label_visibility="collapsed",
        )
        if q.strip():
            qlo = q.strip().lower()
            filtered = [
                s for s in visible
                if qlo in s.lower()
                or qlo in screen_title(s).lower()
                or qlo in screen_tagline(s).lower()
            ]
            if filtered:
                visible = filtered
            else:
                st.caption("No match — showing all screens")
                visible = list(screens)
    st.caption("Functions")
    return _render_nav_icon_grid(
        visible,
        "sidebar_screen",
        "nav_scr",
        SCREEN_ICONS,
        cols=_NAV_GRID_COLS_SCREENS,
        label_fn=screen_title,
    )
