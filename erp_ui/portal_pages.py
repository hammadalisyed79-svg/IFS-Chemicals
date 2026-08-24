"""V15 — Distributor portal UI (isolated from internal ERP)."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from application import data_gateway as db
from erp_core import portal_service as ps
from erp_core import notifications as ntf
from erp_core.v15_security import is_portal_user
from db_v15 import PORTAL_ORDER_STATUSES
from erp_ui.helpers import money_input, sticky_page_tabs, render_dataframe_html_table


def _cart_key():
    return "portal_cart"


def _ensure_cart():
    if _cart_key() not in st.session_state:
        st.session_state[_cart_key()] = []


def _cart_lines() -> list:
    _ensure_cart()
    return list(st.session_state.get(_cart_key()) or [])


def _cart_qty_by_product() -> dict[int, float]:
    """Total qty in the current order cart, keyed by product_id."""
    out: dict[int, float] = {}
    for ln in _cart_lines():
        try:
            pid = int(ln.get("product_id"))
        except (TypeError, ValueError):
            continue
        out[pid] = out.get(pid, 0.0) + float(ln.get("quantity") or 0)
    return out


def _cart_order_summary() -> dict:
    lines = _cart_lines()
    n_lines = len(lines)
    products = set()
    qty = 0.0
    total = 0.0
    for ln in lines:
        try:
            products.add(int(ln.get("product_id")))
        except (TypeError, ValueError):
            pass
        q = float(ln.get("quantity") or 0)
        rate = float(ln.get("rate") or 0)
        disc = float(ln.get("discount_pct") or 0)
        qty += q
        total += q * rate * (1 - disc / 100.0)
    return {
        "lines": n_lines,
        "products": len(products),
        "qty": qty,
        "total": total,
    }


def _merge_into_cart(line: dict) -> float:
    """Add/update a cart line by product_id; returns new total qty for that product."""
    _ensure_cart()
    cart = st.session_state[_cart_key()]
    pid = int(line["product_id"])
    add_qty = float(line.get("quantity") or 0)
    for existing in cart:
        try:
            if int(existing.get("product_id")) == pid:
                existing["quantity"] = float(existing.get("quantity") or 0) + add_qty
                existing["rate"] = float(line.get("rate") or existing.get("rate") or 0)
                existing["discount_pct"] = float(
                    line.get("discount_pct")
                    if line.get("discount_pct") is not None
                    else existing.get("discount_pct")
                    or 0
                )
                existing["code"] = line.get("code") or existing.get("code")
                existing["name"] = line.get("name") or existing.get("name")
                return float(existing["quantity"])
        except (TypeError, ValueError):
            continue
    cart.append(dict(line))
    return add_qty


def _restore_saved_cart(user: dict) -> None:
    """Load DB draft into session once per login/session if cart is empty."""
    _ensure_cart()
    if st.session_state.get("_portal_cart_restored"):
        return
    st.session_state["_portal_cart_restored"] = True
    if st.session_state[_cart_key()]:
        return
    draft = ps.load_portal_cart(user)
    if draft.get("cart"):
        st.session_state[_cart_key()] = list(draft["cart"])
        if draft.get("notes"):
            st.session_state["portal_cart_notes"] = draft["notes"]
        if draft.get("dispatch_town"):
            st.session_state["portal_cart_town"] = draft["dispatch_town"]


@st.dialog("Save to cart")
def _confirm_add_to_cart(item: dict):
    from html import escape
    qty = float(item.get("quantity") or 0)
    disc = float(item.get("discount_pct") or 0)
    rate = float(item.get("rate") or 0)
    net = rate * (1 - disc / 100.0)
    code = escape(str(item.get("code") or ""))
    name = escape(str(item.get("name") or ""))
    already = _cart_qty_by_product().get(int(item["product_id"]), 0.0)
    rate_line = f"Rate: Rs. {rate:,.2f}"
    if disc:
        rate_line += f" (disc {disc:.2f}% → net Rs. {net:,.2f})"
    already_html = ""
    if already > 0:
        already_html = (
            f'<p style="margin:0.45rem 0;padding:0.45rem 0.55rem;background:#ECFDF5;'
            f'border:1px solid #A7F3D0;border-radius:8px;color:#065F46;font-size:0.92rem;">'
            f'Already in this order: <strong>{already:g}</strong> — '
            f'will become <strong>{already + qty:g}</strong></p>'
        )
    st.markdown(
        f"""
<div class="portal-dialog-card" style="background:#FFFFFF;color:#0F172A;border-radius:12px;padding:0.2rem 0.1rem 0.4rem;">
  <h4 style="margin:0 0 0.55rem 0;color:#1E3A8A;font-size:1.05rem;font-weight:800;line-height:1.3;">{code} — {name}</h4>
  <p style="margin:0.35rem 0;color:#0F172A;font-size:0.95rem;">Adding quantity: <strong style="color:#0F172A;">{qty:g}</strong></p>
  {already_html}
  <p class="muted" style="margin:0.35rem 0;color:#475569;font-size:0.95rem;">{escape(rate_line)}</p>
  <p class="total" style="margin-top:0.55rem;padding-top:0.45rem;border-top:1px solid #E2E8F0;font-weight:800;color:#1E3A8A;font-size:1.05rem;">This add: Rs. {qty * net:,.2f}</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    btn_lbl = "Add to order" if already > 0 else "Save to cart"
    if c1.button(btn_lbl, type="primary", use_container_width=True, key="portal_cart_confirm_yes"):
        line = {
            "product_id": item["product_id"],
            "code": item["code"],
            "name": item["name"],
            "quantity": qty,
            "rate": rate,
            "discount_pct": disc,
        }
        new_qty = _merge_into_cart(line)
        try:
            user = st.session_state.get("user") or {}
            ps.save_portal_cart(user, st.session_state[_cart_key()])
        except Exception:
            pass
        st.session_state.pop("_portal_add_pending", None)
        st.session_state["_portal_cart_flash"] = (
            f"Added **{item.get('code')}** — now **{new_qty:g}** in this order. "
            "Stay on Product List to add more."
        )
        st.session_state["_portal_keep_page"] = "Product List"
        st.rerun()
    if c2.button("Cancel", use_container_width=True, key="portal_cart_confirm_no"):
        st.session_state.pop("_portal_add_pending", None)
        st.rerun()


# Portal brand tokens (readable on phones; high-contrast toggle)
_PORTAL_BLUE = "#1D4ED8"
_PORTAL_BLUE_DARK = "#1E3A8A"
_PORTAL_RED = "#DC2626"
_PORTAL_BG = "#F0F4FA"
_PORTAL_CARD = "#FFFFFF"
_PORTAL_TEXT = "#0F172A"
_PORTAL_MUTED = "#475569"

PORTAL_CSS = f"""
<style>
/* ===== Distributor portal shell ===== */
body:has(.erp-portal-root) [data-testid="stAppViewContainer"] > section.main,
body:has(.erp-portal-root) [data-testid="stMainBlockContainer"] {{
  background: {_PORTAL_BG} !important;
}}
body:has(.erp-portal-root) section.main h1,
body:has(.erp-portal-root) section.main h2,
body:has(.erp-portal-root) section.main h3 {{
  color: {_PORTAL_BLUE_DARK} !important;
  font-weight: 800 !important;
  letter-spacing: -0.01em !important;
  line-height: 1.25 !important;
}}
body:has(.erp-portal-root) section.main p,
body:has(.erp-portal-root) section.main label,
body:has(.erp-portal-root) section.main span,
body:has(.erp-portal-root) [data-testid="stCaptionContainer"] p {{
  color: {_PORTAL_TEXT} !important;
}}
body:has(.erp-portal-root) [data-testid="stCaptionContainer"] p {{
  color: {_PORTAL_MUTED} !important;
  font-size: 0.92rem !important;
  line-height: 1.45 !important;
}}
body:has(.erp-portal-root) [data-testid="stMetric"] {{
  background: {_PORTAL_CARD} !important;
  border: 1px solid #Dbeafe !important;
  border-left: 4px solid {_PORTAL_RED} !important;
  border-radius: 14px !important;
  padding: 0.85rem 1rem !important;
  box-shadow: 0 2px 10px rgba(29, 78, 216, 0.08) !important;
}}
body:has(.erp-portal-root) [data-testid="stMetricLabel"],
body:has(.erp-portal-root) [data-testid="stMetricLabel"] p {{
  color: {_PORTAL_MUTED} !important;
  font-weight: 700 !important;
  font-size: 0.78rem !important;
  text-transform: uppercase !important;
  letter-spacing: 0.04em !important;
}}
body:has(.erp-portal-root) [data-testid="stMetricValue"],
body:has(.erp-portal-root) [data-testid="stMetricValue"] * {{
  color: {_PORTAL_BLUE_DARK} !important;
  font-weight: 800 !important;
}}
body:has(.erp-portal-root) .stButton > button {{
  border-radius: 12px !important;
  font-weight: 700 !important;
  min-height: 2.85rem !important;
}}
body:has(.erp-portal-root) .stButton > button[kind="primary"],
body:has(.erp-portal-root) .stButton > button[data-testid="baseButton-primary"] {{
  background: {_PORTAL_RED} !important;
  border: 2px solid #B91C1C !important;
  color: #fff !important;
}}
body:has(.erp-portal-root) [data-testid="stForm"] {{
  background: {_PORTAL_CARD} !important;
  border: 1px solid #E2E8F0 !important;
  border-radius: 16px !important;
  padding: 1rem !important;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.05) !important;
}}
body:has(.erp-portal-root) [data-testid="stAlert"] {{
  border-radius: 12px !important;
}}
.portal-hero {{
  background: linear-gradient(135deg, {_PORTAL_BLUE_DARK} 0%, {_PORTAL_BLUE} 70%);
  color: #fff !important;
  border-radius: 16px;
  padding: 1.1rem 1.15rem;
  margin: 0 0 0.85rem 0;
  box-shadow: 0 8px 24px rgba(30, 58, 138, 0.22);
}}
.portal-hero h2 {{
  color: #fff !important;
  margin: 0 0 0.25rem 0 !important;
  font-size: 1.25rem !important;
  font-weight: 800 !important;
}}
.portal-hero p {{
  color: rgba(255,255,255,0.92) !important;
  margin: 0 !important;
  font-size: 0.92rem !important;
  line-height: 1.4 !important;
}}
.portal-cart-strip {{
  background: #F0FDF4;
  border: 1px solid #86EFAC;
  border-radius: 12px;
  padding: 0.75rem 0.95rem;
  margin: 0 0 0.85rem 0;
  color: #14532D !important;
}}
.portal-cart-strip strong {{ color: #14532D !important; }}
.portal-cart-strip .muted {{ color: #166534 !important; font-size: 0.88rem; }}
.portal-in-cart-badge {{
  display: inline-block;
  background: #059669;
  color: #fff !important;
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  margin: 0 0 0.35rem 0;
}}
.portal-product-in-cart {{
  border-left: 4px solid #059669 !important;
  background: #F0FDF4 !important;
}}
.portal-side-brand {{
  background: linear-gradient(160deg, {_PORTAL_BLUE_DARK}, {_PORTAL_BLUE});
  color: #fff !important;
  border-radius: 14px;
  padding: 0.85rem 0.9rem;
  margin: 0 0 0.75rem 0;
}}
.portal-side-brand h3 {{
  color: #fff !important;
  margin: 0 0 0.2rem 0 !important;
  font-size: 1.05rem !important;
  font-weight: 800 !important;
  line-height: 1.25 !important;
}}
.portal-side-brand p {{
  color: rgba(255,255,255,0.9) !important;
  margin: 0 !important;
  font-size: 0.8rem !important;
}}

/* Dialogs / modals (Save to cart) — light card + dark text (fixes dark theme contrast) */
body:has(.erp-portal-root) [data-testid="stDialog"],
body:has(.erp-portal-root) div[role="dialog"],
body:has(.erp-portal-root) [data-baseweb="modal"],
body:has(.erp-portal-root) [data-testid="stModal"],
[data-testid="stDialog"]:has(.portal-dialog-card),
div[role="dialog"]:has(.portal-dialog-card) {{
  color: {_PORTAL_TEXT} !important;
}}
body:has(.erp-portal-root) [data-testid="stDialog"] > div,
body:has(.erp-portal-root) div[role="dialog"] > div,
body:has(.erp-portal-root) [data-baseweb="modal"] > div,
[data-testid="stDialog"]:has(.portal-dialog-card) > div,
div[role="dialog"]:has(.portal-dialog-card) > div,
[data-testid="stDialog"]:has(.portal-dialog-card) [data-testid="stVerticalBlockBorderWrapper"],
div[role="dialog"]:has(.portal-dialog-card) [data-testid="stVerticalBlockBorderWrapper"] {{
  background: {_PORTAL_CARD} !important;
  background-color: {_PORTAL_CARD} !important;
  color: {_PORTAL_TEXT} !important;
  border-color: #E2E8F0 !important;
}}
body:has(.erp-portal-root) [data-testid="stDialog"] [data-testid="stMarkdownContainer"],
body:has(.erp-portal-root) div[role="dialog"] [data-testid="stMarkdownContainer"],
[data-testid="stDialog"]:has(.portal-dialog-card) [data-testid="stMarkdownContainer"],
div[role="dialog"]:has(.portal-dialog-card) [data-testid="stMarkdownContainer"],
body:has(.erp-portal-root) [data-testid="stDialog"] [data-testid="stMarkdownContainer"] p,
body:has(.erp-portal-root) [data-testid="stDialog"] [data-testid="stMarkdownContainer"] span,
body:has(.erp-portal-root) [data-testid="stDialog"] [data-testid="stMarkdownContainer"] strong,
body:has(.erp-portal-root) div[role="dialog"] [data-testid="stMarkdownContainer"] p,
body:has(.erp-portal-root) div[role="dialog"] [data-testid="stMarkdownContainer"] span,
body:has(.erp-portal-root) div[role="dialog"] [data-testid="stMarkdownContainer"] strong,
[data-testid="stDialog"]:has(.portal-dialog-card) *,
div[role="dialog"]:has(.portal-dialog-card) * {{
  color: {_PORTAL_TEXT} !important;
}}
body:has(.erp-portal-root) [data-testid="stDialog"] h1,
body:has(.erp-portal-root) [data-testid="stDialog"] h2,
body:has(.erp-portal-root) [data-testid="stDialog"] h3,
body:has(.erp-portal-root) div[role="dialog"] h1,
body:has(.erp-portal-root) div[role="dialog"] h2,
[data-testid="stDialog"]:has(.portal-dialog-card) h1,
[data-testid="stDialog"]:has(.portal-dialog-card) h2,
[data-testid="stDialog"]:has(.portal-dialog-card) h3 {{
  color: {_PORTAL_BLUE_DARK} !important;
}}
body:has(.erp-portal-root) [data-testid="stDialog"] .stButton > button[kind="primary"],
body:has(.erp-portal-root) div[role="dialog"] .stButton > button[kind="primary"],
body:has(.erp-portal-root) div[role="dialog"] .stButton > button[data-testid="baseButton-primary"],
[data-testid="stDialog"]:has(.portal-dialog-card) .stButton > button[kind="primary"],
[data-testid="stDialog"]:has(.portal-dialog-card) .stButton > button[data-testid="baseButton-primary"] {{
  background: {_PORTAL_RED} !important;
  border: 2px solid #B91C1C !important;
  color: #FFFFFF !important;
}}
body:has(.erp-portal-root) [data-testid="stDialog"] .stButton > button[kind="primary"] *,
body:has(.erp-portal-root) div[role="dialog"] .stButton > button[kind="primary"] *,
body:has(.erp-portal-root) div[role="dialog"] .stButton > button[data-testid="baseButton-primary"] *,
[data-testid="stDialog"]:has(.portal-dialog-card) .stButton > button[kind="primary"] *,
[data-testid="stDialog"]:has(.portal-dialog-card) .stButton > button[data-testid="baseButton-primary"] * {{
  color: #FFFFFF !important;
}}
body:has(.erp-portal-root) div[role="dialog"] .stButton > button[kind="secondary"],
body:has(.erp-portal-root) div[role="dialog"] .stButton > button[data-testid="baseButton-secondary"],
[data-testid="stDialog"]:has(.portal-dialog-card) .stButton > button[kind="secondary"],
[data-testid="stDialog"]:has(.portal-dialog-card) .stButton > button[data-testid="baseButton-secondary"] {{
  background: #F8FAFC !important;
  border: 1px solid #CBD5E1 !important;
  color: {_PORTAL_TEXT} !important;
}}
.portal-dialog-card {{
  background: {_PORTAL_CARD} !important;
  color: {_PORTAL_TEXT} !important;
  border-radius: 12px;
  padding: 0.15rem 0.1rem 0.35rem;
}}
.portal-dialog-card h4 {{
  margin: 0 0 0.55rem 0;
  color: {_PORTAL_BLUE_DARK} !important;
  font-size: 1.05rem;
  font-weight: 800;
  line-height: 1.3;
}}
.portal-dialog-card p,
.portal-dialog-card strong {{
  margin: 0.35rem 0;
  color: {_PORTAL_TEXT} !important;
  font-size: 0.95rem;
  line-height: 1.45;
}}
.portal-dialog-card .muted {{
  color: {_PORTAL_MUTED} !important;
}}
.portal-dialog-card .total {{
  margin-top: 0.55rem;
  padding-top: 0.45rem;
  border-top: 1px solid #E2E8F0;
  font-weight: 800;
  color: {_PORTAL_BLUE_DARK} !important;
  font-size: 1.05rem;
}}

/* Sidebar panel */
body:has(.erp-portal-root) section[data-testid="stSidebar"] {{
  background: {_PORTAL_CARD} !important;
  border-right: 2px solid {_PORTAL_BLUE} !important;
}}
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-baseweb="radio"] label {{
  padding: 0.55rem 0.65rem !important;
  margin: 0.15rem 0 !important;
  border-radius: 10px !important;
  background: {_PORTAL_BG} !important;
  border: 1px solid #E2E8F0 !important;
}}
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-baseweb="radio"] label p,
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-baseweb="radio"] label span {{
  color: {_PORTAL_TEXT} !important;
  font-weight: 650 !important;
  font-size: 0.95rem !important;
}}
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-baseweb="radio"] label[data-checked="true"],
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-baseweb="radio"] label:has(input:checked) {{
  background: #DBEAFE !important;
  border-color: {_PORTAL_BLUE} !important;
}}

/*
 * Portal menu open / close — professional floating controls
 * (replaces Streamlit’s default blue square + faint chevron)
 */
body:has(.erp-portal-root) [data-testid="stSidebarCollapsedControl"],
body:has(.erp-portal-root) [data-testid="collapsedControl"] {{
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  z-index: 1000001 !important;
  position: fixed !important;
  top: calc(0.7rem + env(safe-area-inset-top, 0px)) !important;
  left: 0.75rem !important;
}}

/* Shared: circular glass control */
body:has(.erp-portal-root) [data-testid="stSidebarCollapsedControl"] button,
body:has(.erp-portal-root) [data-testid="collapsedControl"] button,
body:has(.erp-portal-root) [data-testid="stExpandSidebarButton"],
body:has(.erp-portal-root) button[data-testid="stBaseButton-headerNoPadding"],
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"],
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"],
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"] {{
  background: {_PORTAL_CARD} !important;
  background-color: {_PORTAL_CARD} !important;
  border: 1px solid #E2E8F0 !important;
  color: {_PORTAL_BLUE_DARK} !important;
  border-radius: 999px !important;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.12) !important;
  min-width: 2.75rem !important;
  min-height: 2.75rem !important;
  width: 2.75rem !important;
  height: 2.75rem !important;
  padding: 0 !important;
  margin: 0 !important;
  position: relative !important;
  overflow: hidden !important;
  transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}}
body:has(.erp-portal-root) [data-testid="stSidebarCollapsedControl"] button:hover,
body:has(.erp-portal-root) [data-testid="collapsedControl"] button:hover,
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"]:hover,
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"]:hover {{
  transform: scale(1.04) !important;
  box-shadow: 0 6px 18px rgba(29, 78, 216, 0.18) !important;
  border-color: {_PORTAL_BLUE} !important;
}}

/* Hide Streamlit’s default icon glyphs (they render as ugly squares) */
body:has(.erp-portal-root) [data-testid="stSidebarCollapsedControl"] button > *,
body:has(.erp-portal-root) [data-testid="collapsedControl"] button > *,
body:has(.erp-portal-root) [data-testid="stExpandSidebarButton"] > *,
body:has(.erp-portal-root) button[data-testid="stBaseButton-headerNoPadding"] > *,
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"] > *,
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] > *,
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"] > *,
body:has(.erp-portal-root) [data-testid="stSidebarCollapsedControl"] svg,
body:has(.erp-portal-root) [data-testid="collapsedControl"] svg,
body:has(.erp-portal-root) [data-testid="stExpandSidebarButton"] svg,
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"] svg,
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] svg {{
  opacity: 0 !important;
  visibility: hidden !important;
  width: 0 !important;
  height: 0 !important;
  position: absolute !important;
}}

/* Open menu = hamburger (3 bars) */
body:has(.erp-portal-root) [data-testid="stSidebarCollapsedControl"] button::before,
body:has(.erp-portal-root) [data-testid="collapsedControl"] button::before,
body:has(.erp-portal-root) [data-testid="stExpandSidebarButton"]::before {{
  content: "" !important;
  position: absolute !important;
  left: 50% !important;
  top: 50% !important;
  width: 1.05rem !important;
  height: 2px !important;
  margin: -1px 0 0 -0.525rem !important;
  background: {_PORTAL_BLUE_DARK} !important;
  border-radius: 2px !important;
  box-shadow:
    0 -6px 0 {_PORTAL_BLUE_DARK},
    0 6px 0 {_PORTAL_BLUE_DARK} !important;
}}

/* Close menu (inside open sidebar) = X */
body:has(.erp-portal-root) section[data-testid="stSidebar"] {{
  position: relative !important;
}}
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"],
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"],
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"] {{
  position: absolute !important;
  top: 0.55rem !important;
  right: 0.55rem !important;
  z-index: 20 !important;
  background: #F8FAFC !important;
  border: 1px solid #CBD5E1 !important;
}}
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"]::before,
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"]::before,
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"]::before {{
  content: "" !important;
  position: absolute !important;
  left: 50% !important;
  top: 50% !important;
  width: 0.95rem !important;
  height: 2px !important;
  margin: -1px 0 0 -0.475rem !important;
  background: {_PORTAL_BLUE_DARK} !important;
  border-radius: 2px !important;
  transform: rotate(45deg) !important;
  box-shadow: none !important;
}}
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[kind="headerNoPadding"]::after,
body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"]::after,
body:has(.erp-portal-root) section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"]::after {{
  content: "" !important;
  position: absolute !important;
  left: 50% !important;
  top: 50% !important;
  width: 0.95rem !important;
  height: 2px !important;
  margin: -1px 0 0 -0.475rem !important;
  background: {_PORTAL_BLUE_DARK} !important;
  border-radius: 2px !important;
  transform: rotate(-45deg) !important;
}}

/* Give brand card room so X does not overlap title */
body:has(.erp-portal-root) .portal-side-brand {{
  padding-right: 3rem !important;
}}

.portal-close-menu {{
  display: block;
  width: 100%;
  margin: 0 0 0.65rem 0;
  padding: 0.55rem 0.85rem;
  border-radius: 10px;
  border: 1px solid #CBD5E1;
  background: #F8FAFC;
  color: {_PORTAL_BLUE_DARK};
  font-weight: 700;
  font-size: 0.88rem;
  text-align: center;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(15,23,42,0.06);
}}
.portal-close-menu:active {{
  background: #E2E8F0;
}}

@media (max-width: 768px), (pointer: coarse) {{
  /* Slim quiet top bar — controls sit cleanly on it */
  body:has(.erp-portal-root) header[data-testid="stHeader"] {{
    display: flex !important;
    visibility: visible !important;
    height: 3.5rem !important;
    min-height: 3.5rem !important;
    max-height: 3.5rem !important;
    overflow: visible !important;
    background: {_PORTAL_BG} !important;
    border-bottom: 1px solid #Dbeafe !important;
    box-shadow: none !important;
    z-index: 1000000 !important;
  }}
  body:has(.erp-portal-root) [data-testid="stToolbar"],
  body:has(.erp-portal-root) [data-testid="stDecoration"],
  body:has(.erp-portal-root) #MainMenu,
  body:has(.erp-portal-root) footer {{
    display: none !important;
    visibility: hidden !important;
  }}
  body:has(.erp-portal-root) [data-testid="stMainBlockContainer"],
  body:has(.erp-portal-root) div.block-container {{
    padding-top: 0.85rem !important;
    padding-left: 0.85rem !important;
    padding-right: 0.85rem !important;
  }}
  body:has(.erp-portal-root) section.main h2 {{
    font-size: 1.2rem !important;
  }}
  body:has(.erp-portal-root) section[data-testid="stSidebar"] [data-baseweb="radio"] label {{
    min-height: 2.85rem !important;
    display: flex !important;
    align-items: center !important;
  }}
  body:has(.erp-portal-root) [data-testid="stHorizontalBlock"] {{
    flex-wrap: wrap !important;
    gap: 0.55rem !important;
  }}
  body:has(.erp-portal-root) [data-testid="column"] {{
    min-width: min(100%, 10rem) !important;
  }}
  .portal-hero {{
    padding: 1rem 0.95rem;
    border-radius: 14px;
  }}
  .portal-hero h2 {{
    font-size: 1.15rem !important;
  }}
}}
</style>
"""


def _inject_portal_styles() -> None:
    st.markdown(PORTAL_CSS, unsafe_allow_html=True)


def _portal_sidebar_chrome() -> None:
    """Portal starts with sidebar open, but the collapse arrow must still work."""
    # Only auto-expand once per session — never lock the panel open.
    if st.session_state.get("_portal_sidebar_bootstrapped"):
        return
    st.session_state["_portal_sidebar_bootstrapped"] = True
    import streamlit.components.v1 as components

    components.html(
        """
<script>
(function () {
  try {
    const doc = window.parent.document;
    const sb = doc.querySelector('section[data-testid="stSidebar"]');
    const expanded = sb && sb.getAttribute('aria-expanded') !== 'false';
    if (!expanded) {
      const openBtn = doc.querySelector('[data-testid="stExpandSidebarButton"]')
        || doc.querySelector('[data-testid="stSidebarCollapsedControl"] button')
        || doc.querySelector('[data-testid="collapsedControl"] button');
      if (openBtn) openBtn.click();
    }
  } catch (e) {}
})();
</script>
        """,
        height=0,
        width=0,
    )


def render_portal_app(user: dict) -> None:
    if not is_portal_user(user):
        st.error("This account is not authorized for the distributor portal.")
        return

    st.session_state["portal_mode"] = True
    _inject_portal_styles()
    _portal_sidebar_chrome()
    _restore_saved_cart(user)
    st.markdown('<div class="erp-portal-root mobile-friendly"></div>', unsafe_allow_html=True)
    prof = ps.get_distributor_profile(user) or {}
    biz = prof.get("business_name") or prof.get("customer_name") or "Distributor"

    # Primary portal: order + own ledger + profile. Invoices/Payments under Advanced.
    menu_opts = [
        "Dashboard",
        "Product List",
        "Cart",
        "My Orders",
        "My Ledger",
        "Profile",
        "Notifications",
        "Advanced",
    ]
    kept = st.session_state.pop("_portal_keep_page", None)
    if kept in menu_opts:
        st.session_state["portal_menu"] = kept
    # Migrate session from older menu labels
    if st.session_state.get("portal_menu") in ("Invoices", "Payments"):
        st.session_state["portal_menu"] = "Advanced"
    if st.session_state.get("portal_menu") == "Catalogue":
        st.session_state["portal_menu"] = "Product List"

    with st.sidebar:
        from html import escape
        code = escape(str(prof.get("customer_code") or "—"))
        pl = escape(str(prof.get("price_list_name") or ""))
        biz_safe = escape(str(biz))
        st.markdown(
            f'<div class="portal-side-brand"><h3>{biz_safe}</h3>'
            f"<p>Code {code}"
            + (f" · {pl}" if pl else "")
            + "</p></div>",
            unsafe_allow_html=True,
        )
        st.caption("Tap a page below. Close with ✕ (top right) or Hide menu.")
        import streamlit.components.v1 as components
        components.html(
            """
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  .portal-close-menu {
    display: block; width: 100%; box-sizing: border-box;
    padding: 0.55rem 0.85rem; border-radius: 10px;
    border: 1px solid #CBD5E1; background: #F8FAFC; color: #1E3A8A;
    font-weight: 700; font-size: 0.88rem; text-align: center;
    cursor: pointer; font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  }
  .portal-close-menu:active { background: #E2E8F0; }
</style>
<button class="portal-close-menu" type="button" id="portalHideMenu">Hide menu</button>
<script>
(function () {
  function clickCollapse() {
    try {
      var doc = window.parent.document;
      var btn = doc.querySelector('section[data-testid="stSidebar"] button[kind="headerNoPadding"]')
        || doc.querySelector('section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"]')
        || doc.querySelector('section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"]')
        || doc.querySelector('button[data-testid="stBaseButton-headerNoPadding"]');
      if (btn) btn.click();
    } catch (e) {}
  }
  var el = document.getElementById('portalHideMenu');
  if (el) el.addEventListener('click', clickCollapse);
})();
</script>
            """,
            height=48,
        )
        unread = len(ntf.get_notifications_for_user(user["id"], unread_only=True, limit=99))
        _restore_saved_cart(user)
        cart_n = _cart_order_summary().get("products") or 0

        def _menu_label(opt: str) -> str:
            if opt == "Cart" and cart_n:
                return f"Cart ({cart_n})"
            if opt == "Notifications" and unread:
                return f"Notifications ({unread})"
            return opt

        page = st.radio(
            "Menu",
            menu_opts,
            key="portal_menu",
            label_visibility="collapsed",
            format_func=_menu_label,
        )
        if unread:
            st.info(f"{unread} new notification(s)")
            recent = ntf.get_notifications_for_user(user["id"], unread_only=True, limit=5)
            for n in recent:
                title = (n.get("title") or "Alert").strip()
                cat = (n.get("category") or "").strip()
                if cat == "order_deleted":
                    st.warning(title)
                else:
                    st.caption(f"• {title}")
        flash = st.session_state.get("_portal_notif_flash")
        if flash:
            st.success(flash)
        from erp_ui import form_flow as ff
        if st.button("Refresh", use_container_width=True, help="Reload form and data"):
            st.session_state["_portal_keep_page"] = page
            ff.refresh_current_page()
        if st.button("Sign out", use_container_width=True):
            from erp_ui.auth_session import clear_session
            clear_session()
            st.rerun()

    pages = {
        "Dashboard": _page_dashboard,
        "Product List": _page_catalogue,
        "Cart": _page_cart,
        "My Orders": _page_orders,
        "My Ledger": _page_ledger,
        "Profile": _page_profile,
        "Notifications": _page_notifications,
        "Advanced": _page_advanced,
    }
    pages[page](user)


def _page_dashboard(user: dict):
    from html import escape
    prof = ps.get_distributor_profile(user) or {}
    biz = escape(str(prof.get("business_name") or prof.get("customer_name") or "Distributor"))
    st.markdown(
        f'<div class="portal-hero"><h2>Welcome, {biz}</h2>'
        "<p>Check balance, place orders, and track deliveries from your phone.</p></div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Outstanding", f"Rs. {float(prof.get('current_balance') or 0):,.2f}")
    c2.metric("Credit limit", f"Rs. {float(prof.get('credit_limit') or 0):,.2f}")
    orders = ps.list_portal_orders(user)
    c3.metric("Orders", len(orders))
    recent = orders[:5]
    if recent:
        st.subheader("Recent orders")
        render_dataframe_html_table(
            pd.DataFrame(recent)[["order_no", "order_date", "status", "total"]].rename(
                columns={"order_no": "Order", "order_date": "Date", "status": "Status", "total": "Total"},
            ),
        )
    else:
        st.info("No orders yet. Open **Product List** to add products and place your first order.")


def _page_catalogue(user: dict):
    from html import escape

    st.markdown("## Product List")
    st.caption(
        "Add products for **this order**. After **Save to cart** you stay here — "
        "green items are already in the cart."
    )

    _restore_saved_cart(user)
    _ensure_cart()
    cart_map = _cart_qty_by_product()
    summary = _cart_order_summary()
    cart_lines = _cart_lines()

    flash = st.session_state.pop("_portal_cart_flash", None)
    if flash:
        st.success(flash)

    # Always-visible order strip (even when empty — clear state)
    if summary["products"] > 0:
        # Compact list of what’s already in this order
        chips = []
        for ln in cart_lines:
            code = escape(str(ln.get("code") or ""))
            q = float(ln.get("quantity") or 0)
            chips.append(
                f'<span style="display:inline-block;margin:0.15rem 0.25rem 0.15rem 0;'
                f'padding:0.2rem 0.5rem;background:#059669;color:#fff;border-radius:999px;'
                f'font-size:0.78rem;font-weight:700;">{code} × {q:g}</span>'
            )
        st.markdown(
            f"""
<div class="portal-cart-strip">
  <strong>This order — in cart now</strong>
  <div class="muted" style="margin-top:0.25rem;">
    {summary['products']} product(s) · total qty {summary['qty']:g} · est. Rs. {summary['total']:,.2f}
  </div>
  <div style="margin-top:0.45rem;">{''.join(chips)}</div>
</div>
            """,
            unsafe_allow_html=True,
        )
        b1, b2, b3 = st.columns([1, 1, 2])
        if b1.button("Open cart / submit", type="primary", use_container_width=True, key="portal_cat_goto_cart"):
            st.session_state["_portal_keep_page"] = "Cart"
            st.rerun()
        if b2.button("Clear cart", use_container_width=True, key="portal_cat_clear_cart"):
            st.session_state[_cart_key()] = []
            try:
                ps.clear_portal_cart(user)
            except Exception:
                pass
            st.rerun()
        b3.caption("Keep adding below. Green = already in this order.")
    else:
        st.info("Cart empty — enter qty and **Save to cart**. You will stay on this page.")

    q = st.text_input("Search products", placeholder="Type code or name…")
    all_items = ps.get_catalog(user, search=q or None) or []
    if not all_items and not q:
        st.info(
            "No products in your product list yet. "
            "Please contact IFS to set up your product list."
        )
        return

    view = st.radio(
        "Show",
        ["All products", "In cart only", "Not in cart"],
        horizontal=True,
        key="portal_cat_view",
    )
    if view == "In cart only":
        items = [it for it in all_items if cart_map.get(int(it["product_id"]), 0) > 0]
    elif view == "Not in cart":
        items = [it for it in all_items if cart_map.get(int(it["product_id"]), 0) <= 0]
    else:
        items = list(all_items)

    # Pin in-cart products to the top so they are obvious after Save
    items.sort(
        key=lambda it: (
            0 if cart_map.get(int(it["product_id"]), 0) > 0 else 1,
            str(it.get("code") or ""),
        )
    )

    in_cart_n = sum(1 for it in all_items if cart_map.get(int(it["product_id"]), 0) > 0)
    st.caption(
        f"{len(items)} product(s) shown · **{in_cart_n} in this order**"
        + (f" · search “{q}”" if q else "")
        + (" · in-cart items listed first" if in_cart_n and view == "All products" else "")
    )

    pending = st.session_state.get("_portal_add_pending")
    if pending:
        _confirm_add_to_cart(pending)

    if not items:
        st.warning("No products match this filter.")
        return

    for it in items:
        pid = int(it["product_id"])
        in_qty = float(cart_map.get(pid) or 0)
        in_cart = in_qty > 0
        changed = bool(it.get("admin_changed"))
        with st.container(border=True):
            if in_cart:
                st.markdown(
                    f'<div class="portal-in-cart-badge">✓ IN CART · qty {in_qty:g}</div>'
                    f'<div style="background:#ECFDF5;border:1px solid #6EE7B7;border-radius:8px;'
                    f'padding:0.35rem 0.55rem;margin:0 0 0.45rem 0;color:#065F46;font-size:0.88rem;">'
                    f'Already on this order — button is <b>Add more</b> to increase quantity.</div>',
                    unsafe_allow_html=True,
                )
            if changed:
                st.markdown(
                    '<div style="background:#FFF3CD;border-left:4px solid #D39E00;'
                    'padding:6px 10px;margin-bottom:6px;border-radius:4px;">'
                    '<strong style="color:#856404;">Changed by Admin</strong>'
                    + (
                        f' — {escape(str(it.get("admin_note") or ""))}'
                        if it.get("admin_note")
                        else ""
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
            c1, c2, c3 = st.columns([3, 1, 1])
            title = f"**{it['code']}** — {it['name']}"
            if in_cart:
                title = f"✅ {title}"
            elif changed:
                title = f"🟡 {title}"
            c1.markdown(title)
            disc = float(it.get("discount_pct") or 0)
            net = float(it.get("net_rate") if it.get("net_rate") is not None else it["rate"])
            extra = f" · Min qty {it['min_qty']}"
            if disc:
                extra += f" · Disc {disc:.2f}%"
            if "stock_qty" in it:
                extra += f" · Stock {it['stock_qty']:.0f}"
            if in_cart:
                extra += f" · **In this order: {in_qty:g}**"
            c1.caption(f"Rs. {it['rate']:,.2f} → net Rs. {net:,.2f}{extra}")
            qty = c2.number_input(
                "Qty to add",
                min_value=0.0,
                value=0.0,
                step=1.0,
                key=f"pq_{pid}",
                help=f"Already in cart: {in_qty:g}" if in_cart else "Enter quantity for this order",
            )
            btn_label = "Add more" if in_cart else "Save to cart"
            if c3.button(
                btn_label,
                key=f"add_{pid}",
                use_container_width=True,
                type="secondary" if in_cart else "primary",
            ):
                if qty <= 0:
                    st.warning("Enter quantity greater than zero.")
                else:
                    st.session_state["_portal_add_pending"] = {
                        "product_id": pid,
                        "code": it["code"],
                        "name": it["name"],
                        "quantity": qty,
                        "rate": it["rate"],
                        "discount_pct": disc,
                    }
                    st.rerun()


def _page_cart(user: dict):
    from datetime import date, timedelta

    edit_id = st.session_state.get("_portal_edit_order_id")
    editing = bool(edit_id)
    st.markdown("## Edit order" if editing else "## Shopping Cart")
    if editing:
        st.info(
            f"Editing order **#{edit_id}**. Change lines below, then **Save changes**. "
            "Or cancel edit to leave the order unchanged."
        )
        if st.button("Cancel edit", key="portal_cart_cancel_edit"):
            st.session_state.pop("_portal_edit_order_id", None)
            st.session_state.pop("_portal_edit_order_no", None)
            st.session_state[_cart_key()] = []
            st.session_state.pop("portal_cart_town", None)
            st.session_state.pop("portal_cart_notes", None)
            st.session_state.pop("portal_cart_notes_box", None)
            st.session_state["_portal_keep_page"] = "My Orders"
            st.rerun()

    _ensure_cart()
    if not editing:
        _restore_saved_cart(user)
    cart = st.session_state[_cart_key()]
    draft = {} if editing else ps.load_portal_cart(user)
    if draft.get("saved_at") and draft.get("cart") and not editing:
        st.caption(f"Saved cart last updated: {draft['saved_at']}")

    if not cart:
        st.info("Your cart is empty. Open **Product List**, set qty, then **Save to cart**.")
        if draft.get("cart") and not editing:
            if st.button("Restore saved cart", type="primary", key="portal_cart_restore"):
                st.session_state[_cart_key()] = list(draft["cart"])
                if draft.get("dispatch_town"):
                    st.session_state["portal_cart_town"] = draft["dispatch_town"]
                if draft.get("notes"):
                    st.session_state["portal_cart_notes"] = draft["notes"]
                    st.session_state["portal_cart_notes_box"] = draft["notes"]
                st.rerun()
        return
    df = pd.DataFrame(cart)
    if "discount_pct" in df.columns:
        df["line_total"] = df["quantity"] * df["rate"] * (1 - df["discount_pct"].fillna(0) / 100.0)
    else:
        df["line_total"] = df["quantity"] * df["rate"]
    show_cols = [c for c in ("code", "name", "quantity", "rate", "discount_pct", "line_total") if c in df.columns]
    render_dataframe_html_table(df[show_cols].rename(columns={
        "code": "Code", "name": "Product", "quantity": "Qty",
        "rate": "Rate", "discount_pct": "Disc %", "line_total": "Line Total",
    }))
    qty_total = float(pd.to_numeric(df["quantity"], errors="coerce").fillna(0).sum()) if "quantity" in df.columns else 0.0
    amt_total = float(df["line_total"].sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Products", f"{len(df):,}")
    m2.metric("Total quantity", f"{qty_total:,.0f}" if abs(qty_total - round(qty_total)) < 1e-9 else f"{qty_total:,.3f}")
    m3.metric("Estimated total", f"Rs. {amt_total:,.2f}")

    # Allow removing / changing qty while editing or before submit
    with st.expander("Adjust quantities / remove lines", expanded=editing):
        new_cart = []
        for i, line in enumerate(cart):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"**{line.get('code')}** — {line.get('name')}")
            qty = c2.number_input(
                "Qty",
                min_value=0.0,
                value=float(line.get("quantity") or 0),
                step=1.0,
                key=f"portal_cart_qty_{edit_id or 'new'}_{i}_{line.get('product_id')}",
            )
            remove = c3.checkbox("Remove", key=f"portal_cart_rm_{edit_id or 'new'}_{i}_{line.get('product_id')}")
            if not remove and qty > 0:
                nl = dict(line)
                nl["quantity"] = qty
                new_cart.append(nl)
        if st.button("Apply line changes", key="portal_cart_apply_lines"):
            st.session_state[_cart_key()] = new_cart
            st.rerun()

    d1, d2 = st.columns(2)
    order_date = d1.date_input("Date of order", value=date.today(), key="portal_cart_order_date")
    delivery_date = d2.date_input(
        "Delivery date",
        value=date.today() + timedelta(days=1),
        key="portal_cart_delivery_date",
    )
    if "portal_cart_town" not in st.session_state:
        st.session_state["portal_cart_town"] = draft.get("dispatch_town") or ""
    dispatch_town = st.text_input(
        "Dispatch town / destination *",
        key="portal_cart_town",
        placeholder="e.g. BADIN, LAHORE — shown on the sales order",
        help="Required. This town is saved on your order and appears on the sales order for dispatch.",
    )
    if "portal_cart_notes_box" not in st.session_state:
        st.session_state["portal_cart_notes_box"] = (
            st.session_state.get("portal_cart_notes") or draft.get("notes") or ""
        )
    notes = st.text_area("Order notes (optional)", key="portal_cart_notes_box")
    c1, c2, c3 = st.columns(3)
    if not editing and c1.button("Save cart", use_container_width=True, key="portal_cart_save_btn"):
        try:
            ps.save_portal_cart(
                user, cart, notes=notes, order_date=order_date, delivery_date=delivery_date,
                dispatch_town=dispatch_town,
            )
            st.success("Cart saved. You can leave and come back later.")
        except Exception as e:
            st.error(str(e))
    if c2.button("Clear cart", use_container_width=True, key="portal_cart_clear_btn"):
        st.session_state[_cart_key()] = []
        if not editing:
            ps.clear_portal_cart(user)
        st.rerun()

    submit_label = "Save changes" if editing else "Submit order"
    if c3.button(submit_label, type="primary", use_container_width=True, key="portal_cart_submit_btn"):
        try:
            if not (dispatch_town or "").strip():
                raise ValueError("Enter dispatch town / destination before submitting.")
            if editing:
                oid = ps.update_portal_order(
                    user,
                    int(edit_id),
                    cart,
                    notes=notes,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    dispatch_town=dispatch_town,
                )
                st.session_state.pop("_portal_edit_order_id", None)
                st.session_state.pop("_portal_edit_order_no", None)
                st.session_state[_cart_key()] = []
                st.session_state.pop("portal_cart_town", None)
                st.session_state["_portal_keep_page"] = "My Orders"
                st.success(f"Order updated successfully. Reference #{oid}")
                st.rerun()
            else:
                oid = ps.create_portal_order(
                    user,
                    cart,
                    notes=notes,
                    submit=True,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    dispatch_town=dispatch_town,
                )
                st.session_state[_cart_key()] = []
                st.session_state.pop("portal_cart_town", None)
                ps.clear_portal_cart(user)
                st.success(f"Order submitted successfully. Reference #{oid}")
                st.balloons()
        except Exception as e:
            st.error(str(e))


def _page_orders(user: dict):
    st.markdown("## My Orders")
    st.caption(
        "Track your orders — including orders you place here and orders created by IFS. "
        "You can **edit** or **delete** only **before dispatch** "
        "(not after In Dispatch / Invoiced / Delivered)."
    )
    status = st.selectbox("Status", ["All"] + list(PORTAL_ORDER_STATUSES))
    rows = ps.list_portal_orders(user, status=None if status == "All" else status)
    if not rows:
        st.info("No orders found.")
        return
    # Friendly source label for list
    for r in rows:
        src = (r.get("source_channel") or "").strip().lower()
        notes = (r.get("notes") or "")
        if src == "internal" or notes.startswith("Created by IFS"):
            r["source"] = "IFS"
        else:
            r["source"] = "Portal"
    df = pd.DataFrame(rows)
    cols = [
        c for c in (
            "order_no", "sales_order_no", "source", "order_date", "delivery_date", "dispatch_town",
            "status", "total", "modified_at", "notes",
        ) if c in df.columns
    ]
    render_dataframe_html_table(df[cols].rename(columns={
        "order_no": "Order", "sales_order_no": "Sales Order", "order_date": "Order Date",
        "delivery_date": "Delivery", "dispatch_town": "Dispatch Town",
        "status": "Status", "total": "Total", "modified_at": "Updated", "notes": "Notes",
    }))
    sel = st.selectbox("View details", ["—"] + [f"{r['order_no']} ({r['status']})" for r in rows])
    if sel != "—":
        idx = [f"{r['order_no']} ({r['status']})" for r in rows].index(sel)
        order = ps.get_portal_order(user, rows[idx]["id"])
        if order:
            st.subheader(order["order_no"])
            src = (order.get("source_channel") or "").strip().lower()
            notes = (order.get("notes") or "")
            if src == "internal" or notes.startswith("Created by IFS"):
                st.info("This order was created by IFS for your account.")
            st.write(f"**Status:** {order['status']}")
            st.write(f"**Order date:** {order.get('order_date') or '—'}")
            st.write(f"**Delivery date:** {order.get('delivery_date') or '—'}")
            st.write(f"**Dispatch town:** {order.get('dispatch_town') or '—'}")
            if order.get("sales_order_no"):
                st.write(f"**Sales order:** {order['sales_order_no']}")
            if order.get("modified_at"):
                st.caption(f"Last updated: {order['modified_at']}")
            if order.get("rejection_reason"):
                st.error(f"**Rejected:** {order['rejection_reason']}")
            elif (order.get("status") or "").strip() == "Rejected":
                st.error("This order was rejected by sales.")
            items = order.get("items") or []
            if items:
                idf = pd.DataFrame(items)
                show = [
                    c for c in (
                        "product_code", "product_name", "quantity",
                        "rate", "discount_pct", "amount",
                    ) if c in idf.columns
                ]
                render_dataframe_html_table(idf[show] if show else idf)
                m1, m2, m3 = st.columns(3)
                m1.metric("Subtotal", f"Rs. {float(order.get('subtotal') or 0):,.2f}")
                disc = float(order.get("discount") or 0)
                if disc:
                    m2.metric("Discount", f"Rs. {disc:,.2f}")
                m3.metric("Order total", f"Rs. {float(order.get('total') or 0):,.2f}")

            can_edit = ps.distributor_may_edit_order(order.get("status"))
            can_del = ps.distributor_may_delete_order(order.get("status"))
            e1, e2 = st.columns(2)
            if can_edit and e1.button("Edit order", type="primary", key=f"portal_ord_edit_{order['id']}"):
                cart_lines = []
                for it in items:
                    cart_lines.append({
                        "product_id": it["product_id"],
                        "code": it.get("product_code") or "",
                        "name": it.get("product_name") or "",
                        "quantity": float(it.get("quantity") or 0),
                        "rate": float(it.get("rate") or 0),
                        "discount_pct": float(it.get("discount_pct") or 0),
                    })
                st.session_state[_cart_key()] = cart_lines
                st.session_state["_portal_edit_order_id"] = int(order["id"])
                st.session_state["_portal_edit_order_no"] = order.get("order_no")
                st.session_state["portal_cart_town"] = order.get("dispatch_town") or ""
                st.session_state["portal_cart_notes"] = order.get("notes") or ""
                st.session_state["portal_cart_notes_box"] = order.get("notes") or ""
                # Prefill dates on next cart render via dedicated keys if present
                if order.get("order_date"):
                    try:
                        from datetime import date as _date
                        st.session_state["portal_cart_order_date"] = _date.fromisoformat(
                            str(order["order_date"])[:10]
                        )
                    except Exception:
                        pass
                if order.get("delivery_date"):
                    try:
                        from datetime import date as _date
                        st.session_state["portal_cart_delivery_date"] = _date.fromisoformat(
                            str(order["delivery_date"])[:10]
                        )
                    except Exception:
                        pass
                st.session_state["_portal_keep_page"] = "Cart"
                st.rerun()
            if can_del:
                with e2:
                    confirm = st.checkbox(
                        "Confirm delete",
                        key=f"portal_ord_del_confirm_{order['id']}",
                        help="Required before Delete order is enabled.",
                    )
                    if st.button(
                        "Delete order",
                        type="secondary",
                        disabled=not confirm,
                        key=f"portal_ord_del_{order['id']}",
                    ):
                        try:
                            ono = order.get("order_no") or ""
                            so_no = order.get("sales_order_no") or ""
                            ps.delete_portal_order(user, int(order["id"]))
                            flash = f"Order {ono} deleted."
                            if so_no:
                                flash += f" Sales order {so_no} removed."
                            st.session_state["_portal_notif_flash"] = flash
                            st.session_state["_portal_keep_page"] = "Notifications"
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))
            elif not can_edit:
                st.caption("This order is already dispatched (or later) — edit/delete is not allowed.")


def _attach_party_attrs(df: pd.DataFrame, party: dict) -> pd.DataFrame:
    try:
        df.attrs["ledger_party"] = {
            "code": (party or {}).get("code") or "",
            "name": (party or {}).get("name") or "",
            "phone": (party or {}).get("phone") or "",
            "address": (party or {}).get("address") or (party or {}).get("city") or "",
            "kind": "customer",
        }
        if (party or {}).get("ledger_summary"):
            df.attrs["ledger_summary"] = party["ledger_summary"]
    except Exception:
        pass
    return df


def _page_ledger(user: dict):
    """Own party statement only — never accepts another customer id from the UI."""
    from datetime import date
    from erp_ui.report_print import report_toolbar
    from erp_ui.helpers import fmt_signed_dr_cr, fmt_money

    st.markdown("## My Ledger")
    st.caption("Your account statement only. Running balance with print/export.")

    cid = ps.get_distributor_customer_id(user)
    if not cid:
        st.error("Your portal account is not linked to a customer.")
        return
    ps.assert_distributor_access(user, cid)

    c1, c2, c3 = st.columns(3)
    default_from = date.today().replace(month=1, day=1)
    fd = c1.date_input("From", value=default_from, key="portal_led_from")
    td = c2.date_input("To", value=date.today(), key="portal_led_to")
    detailed = c3.checkbox("Detailed (invoice lines)", value=False, key="portal_led_det")
    fd_s, td_s = str(fd) if fd else None, str(td) if td else None
    period = f"{fd_s or 'Start'} to {td_s or 'Today'}"

    try:
        customer, entries = ps.get_my_ledger(user, fd_s, td_s, detailed=detailed)
    except PermissionError as e:
        st.error(str(e))
        return
    if not customer:
        st.info("Customer record not found.")
        return

    summary = (customer or {}).get("ledger_summary") or {}
    opening = float(summary.get("opening") or 0)
    pdeb = float(summary.get("period_debit") or 0)
    pcred = float(summary.get("period_credit") or 0)
    if detailed and entries:
        try:
            import database as _db
            closing = float(_db.last_detailed_ledger_balance(entries))
        except Exception:
            closing = float(entries[-1].get("balance") or customer.get("balance") or 0)
    else:
        closing = float(summary.get("closing") if summary else (
            entries[-1]["balance"] if entries else customer.get("balance") or 0
        ))

    st.subheader(f"{customer.get('code') or ''} — {customer.get('name') or ''}".strip(" —"))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Opening", fmt_signed_dr_cr(opening))
    m2.metric("Debit (period)", fmt_money(pdeb))
    m3.metric("Credit (period)", fmt_money(pcred))
    m4.metric("Closing", fmt_signed_dr_cr(closing))

    if not entries:
        st.info("No ledger entries in this period.")
        return

    if detailed:
        from erp_ui.reports_pages import _detailed_ledger_dataframe
        df = _detailed_ledger_dataframe(entries)
        title = "Customer Ledger (Detailed)"
        fname = "my_ledger_detailed"
    else:
        cols = [c for c in ("date", "ref", "description", "debit", "credit", "balance") if c in entries[0]]
        df = pd.DataFrame(entries)[cols]
        title = "Customer Ledger"
        fname = "my_ledger"
    df = _attach_party_attrs(df, customer)
    show = df.copy()
    show.columns = [c.replace("_", " ").title() for c in show.columns]
    render_dataframe_html_table(show)
    filters = {"Customer": f"{customer.get('code')} - {customer.get('name')}"}
    report_toolbar(
        df, title, fname, period=period, filters=filters, key_prefix="portal_led",
    )


def _page_advanced(user: dict):
    st.markdown("## Advanced")
    st.caption("Invoices and payment proofs — open a tab below.")
    tab = sticky_page_tabs(["Invoices", "Payments"], "portal_adv_tab")
    if tab == "Invoices":
        _page_invoices(user)
    elif tab == "Payments":
        _page_payments(user)


def _page_invoices(user: dict):
    st.markdown("### My Invoices")
    st.caption("Approved sales invoices only — open one to see full lines and download PDF.")
    invs = ps.list_customer_invoices(user, approved_only=True)
    if not invs:
        st.info("No approved invoices yet.")
        return

    df = pd.DataFrame(invs)
    show_cols = [
        c for c in (
            "invoice_no", "sale_date", "total", "paid_amount", "status",
        ) if c in df.columns
    ]
    render_dataframe_html_table(df[show_cols])

    labels = [
        f"{r.get('invoice_no') or r['id']} · {r.get('sale_date') or '—'} · "
        f"Rs. {float(r.get('total') or 0):,.2f}"
        for r in invs
    ]
    pick = st.selectbox("Open invoice", ["—"] + labels, key="portal_inv_pick")
    if pick == "—":
        return

    row = invs[labels.index(pick)]
    try:
        inv = ps.get_my_invoice(user, row["id"])
    except Exception as e:
        st.error(str(e))
        return
    if not inv:
        st.warning("Invoice not found.")
        return

    st.subheader(inv.get("invoice_no") or f"Invoice #{inv['id']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Date", inv.get("sale_date") or "—")
    m2.metric("Total", f"Rs. {float(inv.get('total') or 0):,.2f}")
    m3.metric("Paid", f"Rs. {float(inv.get('paid_amount') or 0):,.2f}")
    bal = float(inv.get("total") or 0) - float(inv.get("paid_amount") or 0)
    m4.metric("Balance", f"Rs. {bal:,.2f}")

    items = inv.get("items") or []
    if items:
        idf = pd.DataFrame(items)
        line_cols = [
            c for c in (
                "item_name", "quantity", "unit", "rate", "discount_pct",
                "line_discount", "amount", "net_weight",
            ) if c in idf.columns
        ]
        render_dataframe_html_table(idf[line_cols])

    t1, t2, t3 = st.columns(3)
    t1.write(f"**Subtotal:** Rs. {float(inv.get('subtotal') or 0):,.2f}")
    t2.write(f"**Discount:** Rs. {float(inv.get('discount') or 0):,.2f}")
    t3.write(f"**Tax:** Rs. {float(inv.get('tax') or 0):,.2f}")
    if inv.get("notes"):
        st.caption(f"Notes: {inv['notes']}")

    st.markdown("#### Print / PDF")
    from erp_ui.document_print import document_print_toolbar
    document_print_toolbar(
        "Sales Invoice",
        int(inv["id"]),
        key_prefix=f"portal_inv_{inv['id']}",
    )


def _page_payments(user: dict):
    st.markdown("### Payments & Proof")
    st.caption(
        "Enter payment details and attach your bank slip. "
        "IFS accounts will review it under **Distributor Orders → Payment Proofs**."
    )
    prof = ps.get_distributor_profile(user) or {}
    st.metric("Outstanding balance", f"Rs. {float(prof.get('current_balance') or 0):,.2f}")

    # File uploader outside form (Streamlit forms + uploader is unreliable)
    slip = st.file_uploader(
        "Attach bank slip / payment proof",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        key="portal_pay_slip",
        help="PDF or image, max 8 MB",
    )
    with st.form("payment_proof"):
        amount = money_input("Amount paid", value=0.01, min_value=0.01, key="portal_pay_amt")
        proof_date = st.date_input("Payment date")
        ref = st.text_input("Reference / transaction no.")
        bank = st.text_input("Bank name")
        notes = st.text_area("Notes")
        if st.form_submit_button("Upload payment proof", type="primary"):
            try:
                file_bytes = slip.getvalue() if slip else None
                file_name = slip.name if slip else None
                if not file_bytes:
                    st.warning("Attach the bank slip image/PDF, then submit again.")
                else:
                    ps.submit_payment_proof(
                        user,
                        amount,
                        str(proof_date),
                        reference_no=ref,
                        bank_name=bank,
                        notes=notes,
                        file_bytes=file_bytes,
                        file_name=file_name,
                    )
                    st.success("Payment proof submitted for review. Accounts has been notified.")
                    st.rerun()
            except Exception as e:
                st.error(str(e))

    proofs = ps.list_payment_proofs(user)
    if proofs:
        st.subheader("Submitted proofs")
        render_dataframe_html_table(pd.DataFrame(proofs))


def _page_profile(user: dict):
    st.markdown("## Business Profile")
    prof = ps.get_distributor_profile(user) or {}

    def _val(v):
        if v is None:
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("null", "none") else s

    business = _val(prof.get("business_name") or prof.get("customer_name")) or "—"
    st.markdown(f"### {business}")
    st.caption(f"Customer code: {_val(prof.get('customer_code')) or '—'}")
    if prof.get("price_list_name"):
        st.caption(f"Price list: {prof['price_list_name']}")

    st.markdown("#### Update profile")
    st.caption("Changes are saved to your customer record (visible to IFS sales & accounts).")

    with st.form("portal_profile_form"):
        c1, c2 = st.columns(2)
        with c1:
            phone = st.text_input("Main phone", value=_val(prof.get("phone")))
            email = st.text_input("Email", value=_val(prof.get("email")))
            contact_name = st.text_input(
                "Contact person",
                value=_val(prof.get("contact_name") or prof.get("contact_person")),
            )
            city = st.text_input("City", value=_val(prof.get("city")))
            province = st.text_input("Province", value=_val(prof.get("province")))
        with c2:
            dispatch_phone = st.text_input(
                "Dispatch contact number",
                value=_val(prof.get("dispatch_phone")),
                help="Warehouse / dispatch coordination",
            )
            accounts_phone = st.text_input(
                "Accounts contact number",
                value=_val(prof.get("accounts_phone")),
                help="Accounts / payment follow-up",
            )
            owner_phone = st.text_input(
                "Owner contact number",
                value=_val(prof.get("owner_phone")),
            )
            ntn = st.text_input("NTN", value=_val(prof.get("ntn")))
            strn = st.text_input("STRN", value=_val(prof.get("strn")))
        address = st.text_area("Address", value=_val(prof.get("address")), height=80)
        saved = st.form_submit_button("Save profile", type="primary", use_container_width=True)

    if saved:
        try:
            ps.update_my_profile(
                user,
                {
                    "phone": phone,
                    "email": email,
                    "contact_name": contact_name,
                    "city": city,
                    "province": province,
                    "address": address,
                    "ntn": ntn,
                    "strn": strn,
                    "dispatch_phone": dispatch_phone,
                    "accounts_phone": accounts_phone,
                    "owner_phone": owner_phone,
                },
            )
            st.success("Profile updated on the server.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    st.markdown("### Change password")
    from erp_ui.change_password import render_change_password
    render_change_password(user)


def _page_notifications(user: dict):
    st.markdown("## Notifications")
    flash = st.session_state.pop("_portal_notif_flash", None)
    if flash:
        st.success(flash)
    c1, c2 = st.columns([1, 3])
    if c1.button("Mark all read", key="portal_nr_all"):
        ntf.mark_all_read(user["id"])
        st.rerun()
    rows = ntf.get_notifications_for_user(user["id"], limit=100)
    if not rows:
        st.info("No notifications.")
        return
    for n in rows:
        with st.container(border=True):
            unread = not n.get("is_read")
            prefix = "🔴 " if unread else ""
            cat = (n.get("category") or "").strip()
            title = n.get("title") or "Alert"
            if cat == "order_deleted":
                st.warning(f"{prefix}**{title}** — {n.get('created_at') or ''}")
            else:
                st.markdown(f"{prefix}**{title}** — {n.get('created_at') or ''}")
            st.caption(n.get("message") or "")
            if unread:
                if st.button("Mark read", key=f"nr_{n['id']}"):
                    ntf.mark_notification_read(n["id"], user["id"])
                    st.rerun()