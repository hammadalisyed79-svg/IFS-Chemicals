"""One-shot migration: legacy main-header -> std_page_header."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (file, old_title_in_main-header, screen_key_for_nav, optional_custom_title)
MIGRATIONS = [
    ("app.py", "Customers", "Customers", None),
    ("app.py", "Suppliers", "Suppliers", None),
    ("app.py", "Items / Products", "Products", None),
    ("app.py", "Inventory", "Stock", "Inventory"),
    ("app.py", "Customer Ledger", "Customer Ledger", None),
    ("app.py", "Supplier Ledger", "Supplier Ledger", None),
    ("app.py", "Account Ledger", "Account Ledger", None),
    ("app.py", "Stock Report", "Stock Report", None),
    ("app.py", "Profit & Loss Report", "Profit & Loss Report", None),
    ("app.py", "User Management", "User Management", None),
    ("app.py", "Stock", "Stock", None),
    ("app.py", "Stock Adjustments", "Stock Adjustments", None),
    ("app.py", "Stock Transfers", "Stock Transfers", None),
    ("app.py", "Backup & Restore", "Backup & Restore", None),
    ("erp_ui/hr_pages.py", "Employee Master", "Employees", "Employee Master"),
    ("erp_ui/hr_pages.py", "Designation Master", "Employees", "Designation Master"),
    ("erp_ui/hr_pages.py", "Attendance", "Attendance", None),
    ("erp_ui/hr_pages.py", "Leave Management", "Leave Management", None),
    ("erp_ui/hr_pages.py", "Payroll Processing", "Payroll", "Payroll Processing"),
    ("erp_ui/hr_pages.py", "Employee Advances", "Employee Advances", None),
    ("erp_ui/hr_pages.py", "Employee Loans", "Employee Advances", "Employee Loans"),
    ("erp_ui/hr_pages.py", "Expense Claims", "Employee Advances", "Expense Claims"),
    ("erp_ui/hr_pages.py", "Employee Ledger", "Employee Ledger", None),
    ("erp_ui/hr_pages.py", "HR Reports", "Reports Center", "HR Reports"),
    ("erp_ui/v3_pages.py", "Employees", "Employees", None),
    ("erp_ui/v3_pages.py", "Tax Rates", "Tax Rates", None),
    ("erp_ui/v3_pages.py", "Delivery Notes", "Delivery Notes", None),
    ("erp_ui/v3_pages.py", "Purchase Orders", "Purchase Orders", None),
    ("erp_ui/v3_pages.py", "Goods Receipt Notes", "GRN", "Goods Receipt Notes"),
    ("erp_ui/v3_pages.py", "Weight Slips", "Weight Slips", None),
    ("erp_ui/v3_pages.py", "Batch Stock", "Batch Stock", None),
    ("erp_ui/v3_pages.py", "BOM / Formula", "BOM", "BOM / Formula"),
    ("erp_ui/v3_pages.py", "Production Orders", "Production Orders", None),
    ("erp_ui/v3_pages.py", "Journal Voucher", "Journal Voucher", None),
    ("erp_ui/v3_pages.py", "General Ledger", "General Ledger", None),
    ("erp_ui/v3_pages.py", "Trial Balance", "Trial Balance", None),
    ("erp_ui/v3_pages.py", "Balance Sheet", "Balance Sheet", None),
    ("erp_ui/v3_pages.py", "Tax Report", "Tax Report", None),
    ("erp_ui/v3_pages.py", "Customer Outstanding", "Customer Outstanding", None),
    ("erp_ui/v3_pages.py", "Customer Due Aging", "Customer Due Aging", None),
    ("erp_ui/v3_pages.py", "Supplier Outstanding", "Supplier Outstanding", None),
    ("erp_ui/v3_pages.py", "Roles & Permissions", "Roles & Permissions", None),
    ("erp_ui/v3_pages.py", "System Settings", "System Settings", None),
    ("erp_ui/distributor_admin.py", "Distributor Portal Orders", "Distributor Orders", None),
    ("erp_ui/distribution_pages.py", "Distribution Product Lists", "Distribution", None),
    ("erp_ui/price_list_pages.py", "Price Lists", "Price Lists", None),
]

PAT = re.compile(
    r"st\.markdown\('<p class=\"main-header\">([^<]*)</p>', unsafe_allow_html=True\)"
)


def migrate_file(rel_path: str, replacements: list[tuple]) -> int:
    path = ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    n = 0
    for _file, old_title, screen, custom in replacements:
        if _file != rel_path:
            continue
        old_line = f"st.markdown('<p class=\"main-header\">{old_title}</p>', unsafe_allow_html=True)"
        if custom:
            new_line = f'std_page_header("{screen}", title="{custom}")'.replace("td_page_header", "std_page_header")
        else:
            new_line = f'std_page_header("{screen}")'.replace("td_page_header", "std_page_header")
        if old_line in text:
            text = text.replace(old_line, new_line)
            n += 1
    if n:
        if "std_page_header" in text and "from erp_ui.helpers import" in text:
            text = text.replace(
                "from erp_ui.helpers import",
                "from erp_ui.helpers import std_page_header, ",
                1,
            )
        elif "std_page_header" in text and "import erp_ui.helpers as hlp" in text:
            pass  # hlp.std_page_header
        elif "std_page_header" in text and "hlp." in text:
            pass
        elif "std_page_header" in text:
            if "import streamlit" in text and "from erp_ui.helpers import std_page_header" not in text:
                text = text.replace(
                    "import streamlit as st\n",
                    "import streamlit as st\nfrom erp_ui.helpers import std_page_header\n",
                    1,
                )
        path.write_text(text, encoding="utf-8")
    return n


def main():
    by_file: dict[str, list] = {}
    for m in MIGRATIONS:
        by_file.setdefault(m[0], []).append(m)
    total = 0
    for rel, items in by_file.items():
        total += migrate_file(rel, MIGRATIONS)
    print("migrated", total, "headers")


if __name__ == "__main__":
    main()
