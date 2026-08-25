"""IFS Chemicals ERP — brand colours (red, blue, white, black text)."""

RED = "#DC2626"
RED_DARK = "#B91C1C"
RED_LIGHT = "#FEE2E2"
BLUE = "#1D4ED8"
BLUE_DARK = "#1E3A8A"
BLUE_LIGHT = "#DBEAFE"
WHITE = "#FFFFFF"
BLACK = "#000000"
BORDER = "#93C5FD"
PAGE_BG = "#f4f7fc"

# Shared section-header block (CEO desktop + all module pages)
SECTION_HEADER_CSS = f"""
.erp-desk-section,
section.main [data-testid="stMarkdownContainer"] h4,
section.main h4 {{
  font-size: 0.78rem !important;
  font-weight: 800 !important;
  letter-spacing: 0.12em !important;
  color: {BLUE_DARK} !important;
  margin: 1.25rem 0 0.75rem 0 !important;
  text-transform: uppercase !important;
  padding: 0.45rem 0.65rem !important;
  background: {WHITE} !important;
  border: none !important;
  border-left: 5px solid {RED} !important;
  border-radius: 0 8px 8px 0 !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
  line-height: 1.35 !important;
}}
section.main [data-testid="stMarkdownContainer"] h5,
section.main h5 {{
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  color: {BLUE_DARK} !important;
  margin: 0.85rem 0 0.45rem 0 !important;
  text-transform: uppercase !important;
}}
section.main [data-testid="stMarkdownContainer"] h3,
section.main h3 {{
  font-size: 0.95rem !important;
  font-weight: 700 !important;
  color: {BLUE_DARK} !important;
  margin: 0.75rem 0 0.4rem 0 !important;
}}
"""

BRAND_CSS = f"""
<style>
/* === IFS Chemicals — red / blue / white, black text === */
section.main,
section.main label,
section.main span,
section.main h1, section.main h2, section.main h3,
section.main h4, section.main h5, section.main h6,
[data-testid="stCaptionContainer"] p {{
  color: {BLACK} !important;
}}
section.main p,
[data-testid="stMarkdownContainer"] p {{
  color: {BLACK};
}}
.erp-desk-hero,
.erp-desk-hero p,
.erp-desk-hero strong,
.erp-desk-hero-title,
.erp-desk-hero-sub,
.erp-desk-hero-meta {{
  color: {WHITE} !important;
}}

/* Workspace shell — CEO desktop + module pages */
body:has(.erp-desktop-root) [data-testid="stAppViewContainer"] > section.main,
body:has(.erp-module-root) [data-testid="stAppViewContainer"] > section.main,
.stApp:has(.erp-desktop-root) [data-testid="stAppViewContainer"] > section.main,
.stApp:has(.erp-module-root) [data-testid="stAppViewContainer"] > section.main {{
  background: {PAGE_BG} !important;
}}
/* Streamlit 1.39 reserves ~6rem header + one flex slot per CSS inject */
header[data-testid="stHeader"],
[data-testid="stHeader"],
.stAppHeader,
[data-testid="stDecoration"],
[data-testid="stToolbar"],
.stAppDeployButton,
[data-testid="stStatusWidget"] {{
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  border: none !important;
  overflow: hidden !important;
  visibility: hidden !important;
  pointer-events: none !important;
}}
.stMain,
section.main,
[data-testid="stAppViewContainer"] > section.main,
[data-testid="stAppViewContainer"] > section.main > div,
div.block-container,
.stMainBlockContainer,
[data-testid="stMainBlockContainer"] {{
  padding-top: 0.15rem !important;
}}
body:has(.erp-desktop-root) div.block-container,
body:has(.erp-module-root) div.block-container,
body:has(.erp-desktop-root) [data-testid="stMainBlockContainer"],
body:has(.erp-module-root) [data-testid="stMainBlockContainer"],
body:has(.erp-desktop-root) .stMainBlockContainer,
body:has(.erp-module-root) .stMainBlockContainer {{
  padding-top: 0 !important;
  padding-bottom: 0.85rem !important;
  padding-left: clamp(0.5rem, 1.2vw, 1.1rem) !important;
  padding-right: clamp(0.5rem, 1.2vw, 1.1rem) !important;
  max-width: min(100%, 1680px) !important;
  width: 100% !important;
  margin: 0 auto !important;
}}
/* Collapse only the CSS/marker markdown widgets — never their parent
   stVerticalBlockBorderWrapper (that wrapper also contains the login form). */
[data-testid="stElementContainer"]:has(.erp-module-root),
[data-testid="stElementContainer"]:has(.erp-desktop-root),
[data-testid="stElementContainer"]:has(.erp-mobile-root),
[data-testid="stElementContainer"]:has(.erp-notif-root),
[data-testid="stElementContainer"]:has(.erp-css-inject),
.element-container:has(.erp-module-root),
.element-container:has(.erp-desktop-root),
.element-container:has(.erp-mobile-root),
.element-container:has(.erp-notif-root),
.element-container:has(.erp-css-inject),
section.main [data-testid="element-container"]:has(.erp-module-root),
section.main [data-testid="element-container"]:has(.erp-desktop-root),
section.main [data-testid="element-container"]:has(.erp-mobile-root),
section.main [data-testid="element-container"]:has(.erp-notif-root),
section.main [data-testid="element-container"]:has(.erp-css-inject) {{
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  border: none !important;
  overflow: hidden !important;
}}
.erp-module-root,
.erp-desktop-root,
.erp-mobile-root,
.erp-css-inject,
.erp-notif-root {{
  display: none !important;
}}
body:has(.erp-desktop-root) section[data-testid="stSidebar"],
body:has(.erp-module-root) section[data-testid="stSidebar"] {{
  display: none !important;
}}
body:has(.erp-desktop-root) [data-testid="stSidebarCollapsedControl"],
body:has(.erp-module-root) [data-testid="stSidebarCollapsedControl"] {{
  display: none !important;
}}

[data-testid="stAppViewContainer"] > section.main {{
  background: {WHITE} !important;
}}
header[data-testid="stHeader"] {{
  background: {WHITE} !important;
  border-bottom: 2px solid {BLUE} !important;
}}
section[data-testid="stSidebar"] {{
  background: {WHITE} !important;
  border-right: 2px solid {BLUE} !important;
}}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {{
  color: {BLACK} !important;
}}
/* Do not force-paint sidebar chrome icons (collapse arrow) white/black via * */
section[data-testid="stSidebar"] button[kind="headerNoPadding"],
section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"],
section[data-testid="stSidebar"] button[data-testid="baseButton-headerNoPadding"],
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button,
[data-testid="stExpandSidebarButton"] {{
  color: {BLUE_DARK} !important;
}}
[data-testid="stSidebarCollapsedControl"] button svg,
[data-testid="collapsedControl"] button svg,
[data-testid="stExpandSidebarButton"] svg,
section[data-testid="stSidebar"] button[kind="headerNoPadding"] svg,
section[data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] svg {{
  fill: {BLUE_DARK} !important;
  color: {BLUE_DARK} !important;
}}

/* Page titles */
.page-header-wrap {{
  display: block;
  margin: 0 0 0.4rem 0;
  padding: 0;
  overflow: visible;
}}
.main-header {{
  display: block !important;
  font-size: clamp(1.0rem, 2vw, 1.12rem) !important;
  font-weight: 800 !important;
  color: {BLUE_DARK} !important;
  margin: 0 !important;
  padding: 0.3rem 0.55rem !important;
  line-height: 1.25 !important;
  background: {WHITE} !important;
  border: 1px solid rgba(29, 78, 216, 0.45) !important;
  border-left: 4px solid {RED} !important;
  border-radius: 0 8px 8px 0 !important;
  box-shadow: none !important;
}}
.page-header-sub-inline {{
  font-size: 0.78rem;
  font-weight: 500;
  color: {BLACK} !important;
  opacity: 0.85;
}}
.sub-header {{
  font-size: 0.82rem;
  color: {BLACK} !important;
  margin: 0.35rem 0 0 0 !important;
  padding: 0 0.65rem !important;
  line-height: 1.4 !important;
  opacity: 0.85;
}}

/* Invoice status badges & banner */
.inv-badge {{
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.2rem 0.55rem;
  border-radius: 4px;
  border: 1px solid {BORDER};
  line-height: 1.3;
  vertical-align: middle;
}}
.inv-badge-draft {{
  background: {BLUE_LIGHT};
  color: {BLUE_DARK} !important;
  border-color: {BLUE};
}}
.inv-badge-pending {{
  background: #FEF3C7;
  color: #92400E !important;
  border-color: #F59E0B;
}}
.inv-badge-approved {{
  background: #D1FAE5;
  color: #065F46 !important;
  border-color: #10B981;
}}
.inv-badge-rejected {{
  background: {RED_LIGHT};
  color: {RED_DARK} !important;
  border-color: {RED};
}}
.inv-badge-cancelled {{
  background: #F3F4F6;
  color: #374151 !important;
  border-color: #9CA3AF;
}}
.inv-status-banner {{
  background: {WHITE};
  border: 2px solid {BLUE};
  border-left: 5px solid {RED};
  border-radius: 0 10px 10px 0;
  padding: 0.75rem 1rem;
  margin: 0.35rem 0 0.85rem 0;
  box-shadow: 0 2px 8px rgba(29, 78, 216, 0.08);
}}
.inv-status-banner-main {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem 0.65rem;
  color: {BLACK} !important;
  font-size: 0.95rem;
}}
.inv-status-doc {{
  font-weight: 800;
  color: {BLUE_DARK} !important;
}}
.inv-status-party {{
  font-weight: 600;
}}
.inv-status-date {{
  opacity: 0.85;
}}
.inv-status-total {{
  margin-left: auto;
  font-weight: 800;
  color: {BLUE_DARK} !important;
}}
.inv-status-sep {{
  opacity: 0.45;
}}
.inv-status-hint {{
  margin-top: 0.35rem;
  font-size: 0.8rem;
  color: {BLACK} !important;
  opacity: 0.8;
}}
.inv-step-header {{
  font-size: 0.78rem !important;
  font-weight: 800 !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: {BLUE_DARK} !important;
  margin: 1rem 0 0.55rem 0 !important;
  padding: 0.4rem 0.65rem !important;
  background: {WHITE} !important;
  border-left: 5px solid {RED} !important;
  border-radius: 0 8px 8px 0 !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}}

{SECTION_HEADER_CSS}

/* KPI cards (Business Overview + dashboards) */
.dash-kpi {{
  background: {WHITE};
  border: 2px solid {BLUE};
  border-left: 4px solid {RED};
  border-radius: 10px;
  padding: 0.85rem 1rem;
  margin-bottom: 0.5rem;
  box-shadow: 0 2px 8px rgba(29, 78, 216, 0.08);
  min-height: clamp(72px, 12vw, 96px);
}}
.dash-kpi-title {{
  font-size: 0.78rem;
  color: {BLACK} !important;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}
.dash-kpi-value {{
  font-size: 1.3rem;
  font-weight: 800;
  color: {BLACK} !important;
  margin: 0.25rem 0;
}}
.dash-kpi-sub {{
  font-size: 0.78rem;
  color: {BLACK} !important;
  opacity: 0.8;
  line-height: 1.35;
}}
.dash-kpi-compact {{
  min-height: 4.5rem !important;
  padding: 0.55rem 0.65rem !important;
  margin-bottom: 0.35rem !important;
}}
.dash-kpi-compact .dash-kpi-title {{
  font-size: 0.68rem !important;
}}
.dash-kpi-compact .dash-kpi-value {{
  font-size: 1.05rem !important;
}}
.erp-shell-sub-only {{
  font-size: 0.88rem !important;
  color: {BLACK} !important;
  margin: 0.15rem 0 0.35rem 0 !important;
  font-weight: 500 !important;
}}
.dash-alert {{
  background: {RED_LIGHT};
  border-left: 4px solid {RED};
  padding: 0.6rem 0.85rem;
  border-radius: 8px;
  margin-bottom: 0.5rem;
  font-size: 0.88rem;
  color: {BLACK} !important;
}}
.metric-card {{
  background: {WHITE};
  padding: 1rem 1.2rem;
  border-radius: 8px;
  border-left: 4px solid {BLUE};
}}

/* Buttons */
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {{
  background: {RED} !important;
  color: {BLACK} !important;
  border: 2px solid {RED_DARK} !important;
  font-weight: 700 !important;
  border-radius: 8px !important;
}}
.stButton > button[kind="secondary"],
.stButton > button:not([kind="primary"]) {{
  background: {WHITE} !important;
  color: {BLACK} !important;
  border: 2px solid {BLUE} !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
}}
.stButton > button:hover {{
  border-color: {RED} !important;
}}

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
  border-bottom: 2px solid {BLUE} !important;
  gap: 0.25rem !important;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
  background-color: {BLUE_LIGHT} !important;
  color: {BLACK} !important;
  border: 2px solid {BLUE} !important;
  border-radius: 8px 8px 0 0 !important;
  font-weight: 600 !important;
}}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
  background-color: {RED} !important;
  color: {BLACK} !important;
  border-color: {RED_DARK} !important;
  border-bottom: 2px solid {RED} !important;
  font-weight: 700 !important;
}}

/* Metrics & forms */
[data-testid="stMetric"] {{
  background: {WHITE} !important;
  border: 2px solid {BLUE} !important;
  border-radius: 8px !important;
}}
[data-testid="stMetricLabel"],
[data-testid="stMetricValue"] {{
  color: {BLACK} !important;
}}
[data-testid="stForm"] {{
  border: 2px solid {BLUE} !important;
  background: {WHITE} !important;
  border-radius: 10px !important;
}}
.stTextInput input, .stTextArea textarea,
[data-testid="stSelectbox"] > div > div,
.stNumberInput input {{
  border-color: {BLUE} !important;
  color: {BLACK} !important;
  background: {WHITE} !important;
  -webkit-text-fill-color: {BLACK} !important;
  caret-color: {BLACK} !important;
}}
/* Select / popover type-to-filter — keep typed characters visible */
[data-baseweb="select"] input,
[data-baseweb="popover"] input,
[data-baseweb="popover"] [data-baseweb="input"] input,
ul[role="listbox"] input {{
  color: {BLACK} !important;
  -webkit-text-fill-color: {BLACK} !important;
  caret-color: {BLUE} !important;
  opacity: 1 !important;
  background: {WHITE} !important;
}}
[data-baseweb="select"] input::placeholder,
[data-baseweb="popover"] input::placeholder {{
  color: #64748b !important;
  -webkit-text-fill-color: #64748b !important;
  opacity: 1 !important;
}}
.stTextInput input::placeholder {{
  color: #64748b !important;
  -webkit-text-fill-color: #64748b !important;
  opacity: 1 !important;
}}

/* Module top bar — full-width toolbar row */
div[class*="st-key-mod_topbar"],
div[class*="st-key-desk_topbar"] {{
  width: 100% !important;
  max-width: 100% !important;
  align-self: stretch !important;
}}
section.main [data-testid="element-container"]:has(div[class*="st-key-mod_topbar"]),
section.main [data-testid="element-container"]:has(div[class*="st-key-desk_topbar"]),
section.main [data-testid="stVerticalBlock"]:has(div[class*="st-key-mod_topbar"]),
section.main [data-testid="stVerticalBlock"]:has(div[class*="st-key-desk_topbar"]) {{
  width: 100% !important;
  max-width: 100% !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="stVerticalBlock"],
div[class*="st-key-desk_topbar"] [data-testid="stVerticalBlock"] {{
  width: 100% !important;
  max-width: 100% !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"],
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] {{
  width: 100% !important;
  max-width: 100% !important;
  flex-wrap: nowrap !important;
  align-items: center !important;
  gap: 0.5rem !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="column"],
div[class*="st-key-desk_topbar"] [data-testid="column"] {{
  min-width: 0 !important;
  max-width: none !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(1) {{
  flex: 1.4 1 0% !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2) {{
  flex: 1.4 1 0% !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(3) {{
  flex: 5.2 1 0% !important;
}}
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(4) {{
  flex: 1.2 1 0% !important;
}}
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(1) {{
  flex: 2.2 1 0% !important;
}}
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2) {{
  flex: 3.4 1 0% !important;
}}
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(3) {{
  flex: 2.2 1 0% !important;
}}
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(4) {{
  flex: 2.2 1 0% !important;
}}
div[class*="st-key-mod_topbar"] {{
  background: {WHITE} !important;
  border: 1px solid rgba(29, 78, 216, 0.4) !important;
  border-radius: 8px !important;
  padding: 0.3rem 0.55rem !important;
  margin-top: 0 !important;
  margin-bottom: 0.35rem !important;
  box-shadow: none !important;
  box-sizing: border-box !important;
  overflow: visible !important;
}}
div[class*="st-key-mod_topbar"] .stButton > button {{
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  min-height: 2.2rem !important;
  padding-top: 0.3rem !important;
  padding-bottom: 0.3rem !important;
}}
.erp-mod-crumb {{
  color: {BLACK} !important;
  font-size: 0.75rem;
  margin: 0;
  opacity: 0.8;
  line-height: 1.2;
}}
.erp-mod-screen {{
  color: {BLUE_DARK} !important;
  font-size: 0.98rem;
  font-weight: 800;
  margin: 0.05rem 0 0 0;
  letter-spacing: 0.02em;
  line-height: 1.2;
}}
div[class*="st-key-nav_desktop"] button {{
  background: {RED} !important;
  color: {BLACK} !important;
  border: 2px solid {RED_DARK} !important;
  font-weight: 700 !important;
  border-radius: 8px !important;
}}
div[class*="st-key-nav_module"] button {{
  background: {BLUE_LIGHT} !important;
  color: {BLACK} !important;
  border: 2px solid {BLUE} !important;
  font-weight: 700 !important;
  border-radius: 8px !important;
}}

/* Screen chips within a module */
div[class*="st-key-mod_chips_row"] {{
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  background: {WHITE};
  border: 1px solid rgba(29, 78, 216, 0.4);
  border-radius: 8px;
  padding: 0.35rem 0.5rem 0.1rem;
  margin-bottom: 0.4rem;
  margin-top: 0;
  box-shadow: none;
}}
div[class*="st-key-mod_chips_row"] [data-testid="stHorizontalBlock"] {{
  width: 100% !important;
  flex-wrap: nowrap !important;
}}
div[class*="st-key-mod_chips_row"] [data-testid="column"] {{
  min-width: 0 !important;
  flex: 1 1 0% !important;
}}
div[class*="st-key-mod_chips_row"] .stButton > button {{
  font-size: 0.78rem !important;
  min-height: 2.1rem !important;
  padding: 0.28rem 0.4rem !important;
}}
div[class*="st-key-mod_chips_row"] .stButton > button[kind="primary"] {{
  background: {RED} !important;
  border-color: {RED_DARK} !important;
}}
div[class*="st-key-mod_chips_row"] .stButton > button:not([kind="primary"]) {{
  background: {WHITE} !important;
  border-color: {BLUE} !important;
}}

/* Reports hub cards */
.rpt-hub-card {{
  background: {WHITE} !important;
  border: 2px solid {BLUE} !important;
  border-radius: 10px !important;
  padding: 8px 12px !important;
  margin-bottom: 6px !important;
}}
.rpt-hub-card h4 {{
  margin: 0 0 4px 0 !important;
  color: {BLUE_DARK} !important;
  font-weight: 700 !important;
  text-transform: none !important;
  letter-spacing: normal !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}}
.rpt-hub-card p {{
  margin: 0 !important;
  color: {BLACK} !important;
  opacity: 0.8;
}}
.rpt-filter-box {{
  background: {WHITE} !important;
  border: 2px solid {BLUE} !important;
  border-radius: 10px !important;
  padding: 10px 12px !important;
  margin: 6px 0 10px 0 !important;
}}

.erp-day-legend {{
  font-size: 0.78rem;
  color: {BLACK} !important;
  opacity: 0.8;
  margin: 0.1rem 0 0.35rem 0;
  line-height: 1.35;
}}

/* Transaction list filters & KPIs */
.txn-filter-box {{
  background: {WHITE} !important;
  border: 2px solid {BLUE} !important;
  border-radius: 10px !important;
  padding: 0.75rem 1rem 0.25rem !important;
  margin-bottom: 0.75rem !important;
}}
.txn-kpi {{
  font-size: 0.72rem;
  color: {BLACK} !important;
  opacity: 0.85;
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 700;
}}
.txn-kpi-val {{
  font-size: 1.2rem;
  font-weight: 800;
  color: {BLUE_DARK} !important;
  margin: 0.15rem 0 0 0;
}}
.txn-kpi-card {{
  background: {WHITE};
  border: 1px solid rgba(29, 78, 216, 0.28);
  border-left: 4px solid {RED};
  border-radius: 8px;
  padding: 0.55rem 0.75rem;
  margin-bottom: 0.35rem;
}}
.txn-status-strip {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.65rem;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 0.45rem 0.75rem;
  margin: 0.35rem 0 0.55rem 0;
}}
.txn-queue-label {{
  font-size: 0.82rem;
  font-weight: 600;
  color: #334155;
}}
.txn-reg-wrap {{
  overflow-x: auto;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  max-height: min(70vh, 560px);
  border: 1px solid rgba(29, 78, 216, 0.35);
  border-radius: 8px;
  margin: 0.35rem 0 0.5rem 0;
  background: {WHITE};
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}}
.txn-reg-table {{
  width: 100%;
  min-width: 520px;
  border-collapse: collapse;
  font-size: 0.86rem;
}}
.txn-reg-table thead th {{
  background: {BLUE_DARK};
  color: {WHITE} !important;
  text-align: left;
  padding: 0.55rem 0.65rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
  position: sticky;
  top: 0;
  z-index: 2;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.12);
}}
.txn-reg-table tbody td {{
  padding: 0.45rem 0.65rem;
  border-bottom: 1px solid #E2E8F0;
  vertical-align: middle;
  color: {BLACK} !important;
  word-break: break-word;
}}
.txn-reg-table tbody tr:nth-child(even) {{
  background: #F8FAFC;
}}
.txn-reg-table tbody tr:hover {{
  background: {BLUE_LIGHT};
}}
.txn-reg-table .txn-num {{
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
  min-width: 4.5rem;
}}
.txn-reg-table .txn-status-cell {{
  white-space: nowrap;
}}
.erp-section-tabs {{
  margin: 0.25rem 0 0.65rem 0;
}}
.erp-section-tabs [data-testid="stHorizontalBlock"] {{
  gap: 0.35rem !important;
}}
.erp-section-tabs .stButton button {{
  font-weight: 700 !important;
  letter-spacing: 0.02em;
  min-height: 2.35rem;
}}
@media (max-width: 900px) {{
  .txn-reg-table {{
    font-size: 0.78rem;
    min-width: 480px;
  }}
  .txn-reg-table thead th,
  .txn-reg-table tbody td {{
    padding: 0.35rem 0.45rem;
  }}
  .txn-kpi-card {{
    padding: 0.4rem 0.55rem;
  }}
  .txn-kpi-val {{
    font-size: 1.02rem;
  }}
  .erp-section-tabs .stButton button {{
    font-size: 0.72rem !important;
    padding: 0.3rem 0.35rem !important;
    min-height: 2.1rem;
  }}
  .page-header-wrap.erp-page-shell .main-header {{
    font-size: 1.05rem !important;
    padding: 0.45rem 0.65rem !important;
  }}
}}
.mobile-approval-root ~ [data-testid="stVerticalBlock"] .stButton button {{
  min-height: 2.5rem;
}}
.page-header-wrap.erp-page-shell .main-header {{
  background: linear-gradient(90deg, #EFF6FF 0%, {WHITE} 55%) !important;
  border: 1px solid rgba(29, 78, 216, 0.55) !important;
  border-left: 5px solid {RED} !important;
  padding: 0.55rem 0.85rem !important;
  font-size: clamp(1.15rem, 2.2vw, 1.35rem) !important;
}}
.page-header-wrap.erp-page-shell .inv-badge,
.page-header-wrap.erp-page-shell .erp-shell-badge {{
  margin-left: 0.65rem;
  font-size: 0.75rem !important;
}}

.erp-shell-crumb-active {{
  font-size: 0.78rem;
  font-weight: 700;
  color: {BLUE_DARK} !important;
  margin: 0.15rem 0;
  padding: 0.35rem 0.5rem;
  background: {BLUE_LIGHT};
  border-radius: 6px;
  text-align: center;
}}
.erp-empty-state {{
  background: {WHITE};
  border: 2px dashed {BLUE};
  border-radius: 10px;
  padding: 1.25rem 1rem;
  margin: 0.5rem 0 0.75rem 0;
  text-align: center;
}}
.erp-empty-state p {{
  color: {BLACK} !important;
  margin: 0;
  font-size: 0.92rem;
}}
.erp-field-error {{
  color: {RED_DARK} !important;
  background: {RED_LIGHT};
  border-left: 4px solid {RED};
  padding: 0.45rem 0.65rem;
  border-radius: 6px;
  margin: 0.35rem 0;
  font-size: 0.88rem;
  font-weight: 600;
}}
.erp-stock-policy-banner {{
  background: #FEF3C7;
  border: 1px solid #F59E0B;
  border-left: 4px solid #D97706;
  color: {BLACK} !important;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  margin: 0.35rem 0 0.55rem 0;
  font-size: 0.86rem;
}}
.erp-shell-action-bar-marker + div[data-testid="stVerticalBlock"] {{
  position: sticky;
  bottom: 0;
  z-index: 40;
  background: {WHITE};
  border-top: 2px solid {BLUE};
  padding: 0.5rem 0.25rem 0.25rem;
  margin-top: 0.5rem;
  box-shadow: 0 -4px 12px rgba(15, 23, 42, 0.08);
}}

div[class*="st-key-rpt_nav_sidebar"] h5 {{
  text-transform: none !important;
  letter-spacing: normal !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0.5rem 0 0.2rem 0 !important;
  font-size: 0.82rem !important;
}}
</style>
"""

# Tile accents — light fills, black text on buttons
TILE_BLUE = (BLUE_LIGHT, BLUE)
TILE_RED = (RED_LIGHT, RED)
TILE_WHITE = (WHITE, BLUE)

GROUP_TILE_STYLE = {
    "Overview": TILE_BLUE,
    "Masters": TILE_WHITE,
    "Sales": TILE_RED,
    "Purchases": TILE_BLUE,
    "Inventory": TILE_WHITE,
    "Production": TILE_RED,
    "Finance": TILE_BLUE,
    "HR": TILE_WHITE,
    "Weight Scale": TILE_RED,
    "Gate Pass": TILE_BLUE,
    "Reports": TILE_WHITE,
    "Administration": TILE_RED,
}
