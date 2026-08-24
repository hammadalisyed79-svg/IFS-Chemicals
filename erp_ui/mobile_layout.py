"""Mobile browser layout — professional app shell for phones & tablets."""

from __future__ import annotations

import re

_MOBILE_UA = re.compile(
    r"(android|iphone|ipad|ipod|mobile|webos|blackberry|iemobile|opera mini|silk)",
    re.I,
)

# IFS brand — matches erp_ui/theme.py
_BLUE = "#1D4ED8"
_BLUE_DARK = "#1E3A8A"
_RED = "#DC2626"
_WHITE = "#FFFFFF"
_PAGE_BG = "#F0F4FA"

MOBILE_CSS = f"""
<style>
body.erp-mobile-mode,
body:has(.erp-mobile-root) {{
  -webkit-text-size-adjust: 100%;
  touch-action: manipulation;
  background: {_PAGE_BG} !important;
}}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > section.main,
[data-testid="stMainBlockContainer"] {{
  background: {_PAGE_BG} !important;
}}

@media (max-width: 768px), (pointer: coarse) {{
  /* Hide Streamlit chrome — native app feel (portal keeps a slim header — see portal CSS) */
  header[data-testid="stHeader"],
  [data-testid="stToolbar"],
  [data-testid="stDecoration"],
  #MainMenu,
  footer {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    overflow: hidden !important;
  }}
  /* Portal needs header so the menu arrow stays reachable */
  body:has(.erp-portal-root) header[data-testid="stHeader"] {{
    display: flex !important;
    visibility: visible !important;
    height: 3.4rem !important;
    min-height: 3.4rem !important;
    max-height: 3.4rem !important;
    overflow: visible !important;
  }}

  html {{ font-size: 16px !important; }}

  [data-testid="stMainBlockContainer"],
  div.block-container {{
    padding: 0.65rem 0.75rem calc(1rem + env(safe-area-inset-bottom, 0)) !important;
    max-width: 100% !important;
  }}

  /* ---- Login card ---- */
  .erp-mobile-login-wrap {{
    min-height: calc(100vh - 2rem);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 1rem 0.5rem;
    background: linear-gradient(160deg, {_BLUE_DARK} 0%, {_BLUE} 45%, #2563EB 100%);
    margin: -0.65rem -0.75rem 0;
    border-radius: 0;
  }}
  .erp-mobile-login-card {{
    width: 100%;
    max-width: 400px;
    background: {_WHITE};
    border-radius: 18px;
    padding: 1.75rem 1.35rem 1.5rem;
    box-shadow: 0 12px 40px rgba(15, 23, 42, 0.22);
    border: 1px solid rgba(255,255,255,0.25);
  }}
  .erp-mobile-login-logo {{
    text-align: center;
    margin-bottom: 1.25rem;
  }}
  .erp-mobile-login-logo .icon {{
    font-size: 2.5rem;
    line-height: 1;
    margin-bottom: 0.35rem;
  }}
  .erp-mobile-login-logo h1 {{
    font-size: 1.35rem;
    font-weight: 800;
    color: {_BLUE_DARK};
    margin: 0 0 0.2rem 0;
    letter-spacing: 0.02em;
  }}
  .erp-mobile-login-logo p.sub {{
    font-size: 0.9rem;
    color: #475569;
    margin: 0;
    font-weight: 600;
  }}
  .erp-mobile-login-logo p {{
    font-size: 0.82rem;
    color: #334155;
    margin: 0;
    opacity: 0.9;
  }}
  .erp-mobile-login .stTextInput input {{
    min-height: 3.1rem !important;
    font-size: 1rem !important;
    border-radius: 10px !important;
    border: 2px solid #CBD5E1 !important;
  }}
  .erp-mobile-login [data-testid="stForm"] {{
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
  }}
  .erp-mobile-login .stFormSubmitButton > button {{
    min-height: 3.15rem !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
    margin-top: 0.35rem !important;
    background: {_RED} !important;
    border: 2px solid #B91C1C !important;
  }}
  .erp-mobile-login-caption {{
    text-align: center;
    font-size: 0.75rem;
    color: rgba(255,255,255,0.85);
    margin-top: 1rem;
    padding: 0 0.5rem;
  }}

  /* ---- App top bars ---- */
  div[class*="st-key-desk_topbar"],
  div[class*="st-key-mod_topbar"] {{
    border-radius: 14px !important;
    padding: 0.65rem 0.75rem !important;
    margin-bottom: 0.65rem !important;
    box-shadow: 0 2px 12px rgba(29, 78, 216, 0.12) !important;
  }}
  div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"],
  div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] {{
    flex-wrap: wrap !important;
    gap: 0.4rem !important;
  }}
  div[class*="st-key-mod_topbar"] [data-testid="column"],
  div[class*="st-key-desk_topbar"] [data-testid="column"] {{
    flex: 1 1 calc(33.33% - 0.35rem) !important;
    min-width: calc(33.33% - 0.35rem) !important;
  }}
  div[class*="st-key-mod_topbar"] [data-testid="column"]:nth-child(3),
  div[class*="st-key-desk_topbar"] [data-testid="column"]:nth-child(2) {{
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }}
  div[class*="st-key-mod_topbar"] .stButton > button,
  div[class*="st-key-desk_topbar"] .stButton > button {{
    min-height: 2.75rem !important;
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    border-radius: 10px !important;
  }}
  .erp-mod-screen {{
    font-size: 1.15rem !important;
  }}
  .erp-mod-crumb {{
    font-size: 0.72rem !important;
  }}
  .erp-desk-brand {{
    font-size: 1.05rem !important;
  }}

  /* ---- Dashboard hero ---- */
  .erp-desk-hero {{
    border-radius: 14px !important;
    padding: 1rem !important;
    margin-bottom: 0.75rem !important;
  }}
  .erp-desk-hero table, .erp-desk-hero tr, .erp-desk-hero td {{
    display: block !important;
    width: 100% !important;
    text-align: left !important;
  }}
  .erp-desk-hero-title {{ font-size: 1.35rem !important; }}
  .erp-desk-hero-meta {{
    text-align: left !important;
    margin-top: 0.45rem !important;
    font-size: 0.8rem !important;
  }}
  .erp-desk-section {{
    font-size: 0.78rem !important;
    font-weight: 800 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {_BLUE_DARK} !important;
    margin: 0.85rem 0 0.45rem 0 !important;
    padding-left: 0.15rem;
  }}

  /* ---- Module tiles (single column on phone) ---- */
  div[class*="st-key-dsk_tile_"] button,
  div[class*="st-key-dsk_scr_"] button {{
    min-height: 108px !important;
    padding: 0.9rem 0.85rem !important;
    border-radius: 14px !important;
    box-shadow: 0 3px 10px rgba(29, 78, 216, 0.1) !important;
    font-size: 0.88rem !important;
  }}
  div[class*="st-key-dsk_tile_"] button p::first-line,
  div[class*="st-key-dsk_scr_"] button p::first-line {{
    font-size: 1.75rem !important;
  }}
  div[class*="st-key-dsk_qa_"] button {{
    min-height: 2.85rem !important;
    border-radius: 10px !important;
    font-size: 0.8rem !important;
  }}

  /* ---- Screen chips (scrollable pills) ---- */
  div[class*="st-key-mod_chips_row"] {{
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin-bottom: 0.5rem;
    padding-bottom: 0.15rem;
  }}
  div[class*="st-key-mod_chips_row"] [data-testid="stHorizontalBlock"] {{
    flex-wrap: nowrap !important;
    gap: 0.35rem !important;
  }}
  div[class*="st-key-mod_chips_row"] [data-testid="column"] {{
    flex: 0 0 auto !important;
    min-width: 6.5rem !important;
  }}
  div[class*="st-key-mod_chips_row"] .stButton > button {{
    min-height: 2.5rem !important;
    font-size: 0.75rem !important;
    border-radius: 999px !important;
    white-space: nowrap !important;
  }}

  /* ---- Forms, inputs, buttons ---- */
  .stButton > button {{
    min-height: 2.85rem !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
  }}
  .stTextInput input, .stNumberInput input, .stTextArea textarea,
  [data-testid="stSelectbox"] > div > div {{
    min-height: 2.85rem !important;
    font-size: 1rem !important;
    border-radius: 10px !important;
  }}
  [data-testid="stForm"] {{
    border-radius: 14px !important;
    padding: 0.85rem !important;
  }}

  /* ---- Tabs ---- */
  [data-testid="stTabs"] [data-baseweb="tab-list"] {{
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
    flex-wrap: nowrap !important;
  }}
  [data-testid="stTabs"] [data-baseweb="tab"] {{
    min-height: 2.65rem !important;
    padding: 0.45rem 0.85rem !important;
    font-size: 0.82rem !important;
    flex: 0 0 auto !important;
  }}

  /* ---- Metrics & KPIs ---- */
  [data-testid="stMetric"] {{
    background: {_WHITE} !important;
    border-radius: 12px !important;
    padding: 0.65rem 0.75rem !important;
    border: 1px solid #E2E8F0 !important;
    box-shadow: 0 1px 4px rgba(15,23,42,0.06) !important;
  }}
  .dash-kpi {{
    border-radius: 12px !important;
    padding: 0.75rem !important;
  }}
  div[class*="st-key-"][class*="_metrics"] [data-testid="column"] {{
    flex: 1 1 calc(50% - 0.35rem) !important;
    min-width: calc(50% - 0.35rem) !important;
  }}

  /* ---- Data tables ---- */
  [data-testid="stDataFrame"] > div {{
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
    border-radius: 10px;
  }}
  .main-header {{
    font-size: 1rem !important;
    border-radius: 10px !important;
    padding: 0.5rem 0.75rem !important;
  }}

  /* ---- Alerts ---- */
  [data-testid="stAlert"] {{
    border-radius: 10px !important;
    font-size: 0.88rem !important;
  }}

  /* Single-column forms */
  section.main [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }}

  .mobile-approval-root .stButton > button {{
    min-height: 3rem !important;
    font-size: 1rem !important;
  }}
}}

@media (max-width: 480px) {{
  div[class*="st-key-dsk_tile_"],
  div[class*="st-key-dsk_scr_"] {{
    width: 100% !important;
  }}
}}
</style>
"""

_MOBILE_HEAD = f"""
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<meta name="theme-color" content="{_BLUE_DARK}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="mobile-web-app-capable" content="yes">
"""

_MOBILE_BODY_SCRIPT = """
<script>
(function () {
  function applyMobileClass() {
    var mobile = window.matchMedia("(max-width: 768px)").matches
      || window.matchMedia("(pointer: coarse)").matches;
    document.body.classList.toggle("erp-mobile-mode", mobile);
  }
  applyMobileClass();
  window.addEventListener("resize", applyMobileClass);
})();
</script>
"""


def is_mobile_client() -> bool:
    """Detect phone/tablet from Streamlit request context or ?mobile=1."""
    try:
        import streamlit as st

        if st.query_params.get("mobile") == "1":
            return True
        ctx = getattr(st, "context", None)
        if ctx is None:
            return False
        ua = getattr(ctx, "user_agent", None)
        if ua is None:
            return False
        text = ua.to_str() if hasattr(ua, "to_str") else str(ua)
        return bool(_MOBILE_UA.search(text))
    except Exception:
        return False


def grid_columns(default: int = 4, mobile: int = 2) -> int:
    return 1 if is_mobile_client() else default


def qa_columns(default: int = 5, mobile: int = 2) -> int:
    return 2 if is_mobile_client() else default


def mobile_login_shell(title: str, subtitle: str) -> str:
    return f"""
<div class="erp-mobile-login-wrap">
  <div class="erp-mobile-login-card erp-mobile-login">
    <div class="erp-mobile-login-logo">
      <div class="icon">🧪</div>
      <h1>{title}</h1>
      <p class="sub">{subtitle}</p>
    </div>
"""


def inject_mobile_layout() -> None:
    import streamlit as st

    # One markdown only — multiple injects stacked flex-gap above the ERP topbar.
    st.markdown(
        _MOBILE_HEAD
        + MOBILE_CSS
        + _MOBILE_BODY_SCRIPT
        + '<div class="erp-mobile-root mobile-friendly erp-css-inject" aria-hidden="true">&#8203;</div>',
        unsafe_allow_html=True,
    )
