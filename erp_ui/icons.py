"""Professional navigation glyphs — replaces emoji in desktop tiles."""

from __future__ import annotations

# Compact Unicode symbols (render consistently on Windows / web)
GROUP_ICONS = {
    "Overview": "◈",
    "Masters": "▣",
    "Sales": "◆",
    "Purchases": "◇",
    "Inventory": "▤",
    "Production": "⚙",
    "Finance": "₨",
    "HR": "◎",
    "Weight Scale": "⚖",
    "Gate Pass": "⛊",
    "Reports": "▥",
    "Administration": "⚙",
}

SCREEN_ICONS = {
    "Dashboard": "⌂",
    "Business Overview": "◈",
    "Cash Book": "₨",
    "Bank Book": "▣",
    "Cash Receipts": "↓",
    "Cash Payments": "↑",
    "Cash Advance": "◎",
    "Sales Invoices": "◆",
    "Sale Approval": "✓",
    "Purchase Invoices": "◇",
    "Purchase Approval": "✓",
    "Customers": "▣",
    "Suppliers": "▣",
    "Products": "▤",
    "General Ledger": "▥",
    "Trial Balance": "▥",
    "Gate Pass": "⛊",
    "Weighbridge": "⚖",
}

_DEFAULT = "•"


def icon_for(name: str, icons_map: dict | None = None) -> str:
    icons_map = icons_map or {}
    return icons_map.get(name) or GROUP_ICONS.get(name) or SCREEN_ICONS.get(name) or _DEFAULT
