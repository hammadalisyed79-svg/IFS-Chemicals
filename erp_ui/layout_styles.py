"""Global Streamlit layout CSS — compact headers, forms, and responsive toolbars."""

GLOBAL_LAYOUT_CSS = """
<style>
/* Fluid type scales with viewport (readable on laptops and large monitors) */
html { font-size: clamp(14px, 0.35vw + 12px, 16px); }

/* Main content — Streamlit still injects ~6rem header padding unless we override */
[data-testid="stAppViewContainer"] > section.main > div,
.stMain,
section.main {
  padding-top: 0.1rem !important;
}
div.block-container,
.stMainBlockContainer,
[data-testid="stMainBlockContainer"] {
  padding-top: 0.25rem !important;
  padding-bottom: 1.25rem !important;
  padding-left: clamp(0.65rem, 1.5vw, 1.25rem) !important;
  padding-right: clamp(0.65rem, 1.5vw, 1.25rem) !important;
  max-width: 100% !important;
  width: 100% !important;
}
/* Desktop / module shells — override the default top padding (must win) */
body:has(.erp-desktop-root) div.block-container,
body:has(.erp-module-root) div.block-container,
body:has(.erp-desktop-root) [data-testid="stMainBlockContainer"],
body:has(.erp-module-root) [data-testid="stMainBlockContainer"] {
  padding-top: 0 !important;
  padding-bottom: 0.85rem !important;
}
@media (min-width: 1200px) {
  body:not(:has(.erp-module-root)):not(:has(.erp-desktop-root)) [data-testid="stMainBlockContainer"] {
    max-width: min(100%, 1680px) !important;
  }
}
@media (max-width: 720px) {
  body:not(:has(.erp-module-root)):not(:has(.erp-desktop-root)) div.block-container,
  body:not(:has(.erp-module-root)):not(:has(.erp-desktop-root)) [data-testid="stMainBlockContainer"] {
    padding-top: 0.85rem !important;
    padding-bottom: 0.85rem !important;
  }
  body:has(.erp-desktop-root) div.block-container,
  body:has(.erp-module-root) div.block-container,
  body:has(.erp-desktop-root) [data-testid="stMainBlockContainer"],
  body:has(.erp-module-root) [data-testid="stMainBlockContainer"] {
    padding-top: 0 !important;
    padding-bottom: 0.85rem !important;
  }
}
header[data-testid="stHeader"] {
  background: rgba(255, 255, 255, 0.98);
}

/* Page title block — colours in theme.py */
.page-header-wrap {
  display: block;
  margin: 0 0 0.4rem 0;
  padding: 0;
  overflow: visible;
}
.page-header-compact {
  margin-bottom: 0.3rem !important;
}

/* Tabs — layout only (colours in theme.py) */
[data-testid="stTabs"] {
  margin-top: 0.15rem;
  margin-bottom: 0.25rem;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: flex-end !important;
  min-height: 2.5rem !important;
  width: 100% !important;
  background: transparent !important;
  overflow-x: auto !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  display: inline-flex !important;
  flex: 0 0 auto !important;
  align-items: center !important;
  justify-content: center !important;
  height: auto !important;
  min-height: 2.15rem !important;
  padding: 0.4rem 0.95rem !important;
  margin: 0 !important;
  font-size: 0.875rem !important;
  line-height: 1.2 !important;
  white-space: nowrap !important;
  box-shadow: none !important;
}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {
  padding-top: 0.65rem !important;
  border-top: none !important;
}
hr {
  margin: 0.35rem 0 !important;
}

/* Toolbar rows — always span full content width */
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"],
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"],
div[class*="st-key-mod_chips_row"] [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important;
  width: 100% !important;
  max-width: 100% !important;
}
div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"],
div[class*="st-key-desk_topbar"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  min-width: 0 !important;
  max-width: none !important;
}
div[class*="st-key-mod_chips_row"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  flex: 1 1 0% !important;
  min-width: 0 !important;
  max-width: none !important;
}

/* Vertical rhythm between widgets */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
  padding-top: 0.1rem;
  padding-bottom: 0.1rem;
}
/* Columns — flex and wrap so forms adapt to screen width */
section.main [data-testid="stHorizontalBlock"] {
  gap: 0.35rem !important;
  align-items: flex-end;
  flex-wrap: wrap !important;
}
section.main [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  min-width: 0 !important;
  flex: 1 1 11.5rem !important;
  max-width: 100% !important;
}
@media (min-width: 1400px) {
  section.main [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 10rem !important;
  }
}
@media (max-width: 1100px) {
  section.main [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 calc(50% - 0.4rem) !important;
    min-width: min(100%, 220px) !important;
  }
}
@media (max-width: 720px) {
  section.main [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 100% !important;
    min-width: 100% !important;
  }
}
/* Tab panels keep equal tab buttons on one row */
section.main [data-testid="stTabs"] [data-testid="stHorizontalBlock"] {
  align-items: stretch !important;
  gap: 0 !important;
  flex-wrap: nowrap !important;
}
section.main [data-testid="stTabs"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  flex: 1 1 auto !important;
  min-width: 0 !important;
  max-width: none !important;
}
/* Wide toolbars (ledger day nav, 5+ buttons) — scroll on narrow screens */
div[class*="st-key-"][class*="_wide_row"] [data-testid="stHorizontalBlock"],
div[class*="st-key-erp_wide_row"] [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important;
  min-width: min-content;
}
div[class*="st-key-"][class*="_wide_row"],
div[class*="st-key-erp_wide_row"] {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  width: 100%;
  padding-bottom: 0.15rem;
}
div[class*="st-key-"][class*="_wide_row"] [data-testid="column"],
div[class*="st-key-erp_wide_row"] [data-testid="column"] {
  flex: 0 0 auto !important;
  min-width: 5.5rem !important;
}

/* Metrics — sizing only (colours in theme.py) */
[data-testid="stMetric"] {
  padding: 0.35rem 0.5rem !important;
}
[data-testid="stMetricLabel"] {
  font-size: 0.7rem !important;
}
[data-testid="stMetricValue"] {
  font-size: 1.05rem !important;
}
div[class*="st-key-"][class*="_metrics"] [data-testid="stMetric"] {
  min-height: 3.1rem;
}
div[class*="st-key-"][class*="_metrics"] [data-testid="stHorizontalBlock"] {
  flex-wrap: wrap !important;
}
@media (max-width: 900px) {
  div[class*="st-key-"][class*="_metrics"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 calc(50% - 0.35rem) !important;
    min-width: 140px !important;
  }
}
@media (max-width: 520px) {
  div[class*="st-key-"][class*="_metrics"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 100% !important;
  }
}

/* Forms — padding only (colours in theme.py) */
[data-testid="stForm"] {
  padding: 0.5rem 0.65rem 0.65rem 0.65rem !important;
}
[data-testid="stForm"] label {
  font-size: 0.8rem !important;
  margin-bottom: 0.1rem !important;
}
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
  align-items: flex-end;
}

/* Inputs — slightly tighter */
.stNumberInput input, .stTextInput input, .stTextArea textarea,
[data-testid="stSelectbox"] > div > div {
  min-height: 2rem !important;
}
.stButton > button {
  min-height: 2rem !important;
  padding: 0.2rem 0.55rem !important;
  font-size: 0.84rem !important;
}

/* Alerts — professional action feedback */
[data-testid="stAlert"] {
  padding: 0.55rem 0.85rem !important;
  margin: 0.35rem 0 0.65rem 0 !important;
  border-radius: 8px !important;
  border-left-width: 4px !important;
}
[data-testid="stAlert"] p {
  font-size: 0.92rem !important;
  margin: 0 !important;
  line-height: 1.35 !important;
}

/* Dataframes — denser rows, use horizontal space */
[data-testid="stDataFrame"] {
  margin-top: 0.1rem !important;
  margin-bottom: 0.2rem !important;
  width: 100% !important;
}
[data-testid="stDataFrame"] [data-testid="stElementToolbar"] {
  padding: 0.15rem 0 !important;
}
[data-testid="stDataFrame"] canvas,
[data-testid="stDataFrame"] [role="grid"] {
  font-size: 0.9rem !important;
}

/* Alternating row shade — payroll Edit Lines and other grids */
div[class*="st-key-pr_tab_editor_"] [data-testid="stDataFrame"] [role="rowgroup"] [role="row"]:nth-child(even) [role="gridcell"],
div[class*="st-key-pr_tab_editor_"] [data-testid="stDataFrame"] [role="row"]:nth-child(even) {
  background-color: #eef2f7 !important;
}
div[class*="st-key-pr_tab_editor_"] [data-testid="stDataFrame"] [role="rowgroup"] [role="row"]:nth-child(odd) [role="gridcell"],
div[class*="st-key-pr_tab_editor_"] [data-testid="stDataFrame"] [role="row"]:nth-child(odd) {
  background-color: #ffffff !important;
}
/* Fallback for glide/canvas wrappers */
div[class*="st-key-pr_tab_editor_"] [data-testid="stDataFrame"] {
  --dv-odd-row-background-color: #ffffff;
  --dv-even-row-background-color: #e8eef5;
}

/* Expanders */
[data-testid="stExpander"] details summary {
  padding: 0.35rem 0.5rem !important;
  font-size: 0.86rem !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
  padding-top: 0.35rem !important;
}

/* Cash / Bank Daily Book — full-width panels so all columns stay visible */
body:has(div[class*="st-key-"][class*="_day_wide"]) [data-testid="stMainBlockContainer"] {
  max-width: min(100%, 1920px) !important;
  padding-left: clamp(0.5rem, 1.2vw, 1rem) !important;
  padding-right: clamp(0.5rem, 1.2vw, 1rem) !important;
}
div[class*="st-key-"][class*="_book_body"] {
  width: 100% !important;
  margin: 0.15rem 0 0.35rem 0 !important;
}
div[class*="st-key-"][class*="_book_body"] .erp-section-tabs,
div[class*="st-key-"][class*="_book_body"] .erp-desk-section {
  margin-top: 0 !important;
}
div[class*="st-key-"][class*="_cash_footer"] {
  margin-top: 0.85rem !important;
  padding-top: 0.65rem !important;
  border-top: 2px solid rgba(29, 78, 216, 0.22) !important;
}
div[class*="st-key-"][class*="_day_wide"] {
  width: 100% !important;
  max-width: 100% !important;
}
div[class*="st-key-"][class*="_day_wide"] [data-testid="stHorizontalBlock"] {
  gap: 0.75rem !important;
  align-items: flex-start !important;
}
div[class*="st-key-"][class*="_day_wide"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  flex: 1 1 0% !important;
  min-width: min(48%, 22rem) !important;
  max-width: 100% !important;
}
div[class*="st-key-"][class*="_day_wide"] [data-testid="stDataFrame"],
div[class*="st-key-"][class*="_day_wide"] .txn-reg-wrap {
  width: 100% !important;
}
div[class*="st-key-"][class*="_day_wide"] [data-testid="stDataFrame"] > div {
  width: 100% !important;
}
/* Prefer fitting columns in panel over a clipped horizontal scrollbar */
div[class*="st-key-"][class*="_day_wide"] [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {
  width: 100% !important;
}
div[class*="st-key-"][class*="_day_wide"] .txn-reg-wrap {
  max-height: min(56vh, 480px);
}

/* Compact voucher / finance entry forms — restore column ratios & cap width */
div[class*="st-key-"][class*="_form_blk"] {
  max-width: min(58rem, 100%);
  margin-right: auto;
  margin-bottom: 0.35rem;
}
div[class*="st-key-"][class*="_form_blk"] [data-testid="stHorizontalBlock"] {
  gap: 0.45rem !important;
  align-items: flex-end !important;
  flex-wrap: wrap !important;
}
div[class*="st-key-"][class*="_form_blk"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  flex: 1 1 0% !important;
  min-width: 0 !important;
  max-width: 100% !important;
}
div[class*="st-key-"][class*="_form_blk"] label {
  font-size: 0.8rem !important;
  margin-bottom: 0.15rem !important;
}
div[class*="st-key-"][class*="_form_blk"] [data-testid="stCaption"] {
  font-size: 0.72rem !important;
  margin-top: -0.15rem !important;
  margin-bottom: 0.15rem !important;
}
div[class*="st-key-"][class*="_form_line"] {
  padding: 0.35rem 0.55rem 0.45rem;
  margin: 0 0 0.45rem;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 0.45rem;
  background: rgba(248, 250, 252, 0.65);
}
div[class*="st-key-"][class*="_form_line"] [data-testid="stHorizontalBlock"] {
  gap: 0.35rem !important;
  align-items: flex-end !important;
  flex-wrap: wrap !important;
  margin-bottom: 0.15rem !important;
}
div[class*="st-key-"][class*="_form_line"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
  flex: 1 1 0% !important;
  min-width: 0 !important;
}
@media (max-width: 768px) {
  div[class*="st-key-"][class*="_form_blk"],
  div[class*="st-key-"][class*="_form_line"] {
    max-width: 100%;
  }
  div[class*="st-key-"][class*="_form_line"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 100% !important;
  }
}

/* Invoice / voucher line grids — horizontal scroll when many columns */
div[class*="st-key-"][class*="_lines_blk"] {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  width: 100%;
  margin-bottom: 0.2rem;
  border: 1px solid rgba(29, 78, 216, 0.28);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
  padding: 0.35rem 0.45rem 0.5rem;
}
.txn-line-hdr-cell {
  background: #1D4ED8;
  color: #fff !important;
  text-align: left;
  padding: 0.42rem 0.35rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
  line-height: 1.2;
  margin-bottom: 0.12rem;
  border-radius: 4px;
}
.txn-line-hdr-cell.txn-line-hdr-num {
  text-align: right;
}
.txn-line-hdr-cell.txn-line-act {
  text-align: center;
  padding-left: 0.15rem;
  padding-right: 0.15rem;
}
.txn-line-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 0.82rem;
  padding: 0.35rem 0.2rem 0.1rem 0;
  line-height: 1.25;
}
.txn-line-prev {
  font-size: 0.78rem;
}
/* Legacy table header (unused) — kept for old cached pages */
.txn-line-head-wrap {
  margin: 0 0 0.2rem 0;
  overflow-x: auto;
}
.txn-line-head {
  width: 100%;
  min-width: min(100%, 42rem);
  border-collapse: collapse;
  table-layout: fixed;
}
.txn-line-head th {
  background: #1D4ED8;
  color: #fff !important;
  text-align: left;
  padding: 0.42rem 0.45rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.txn-line-head th.txn-line-act {
  width: 2rem;
  text-align: center;
}
div[class*="st-key-"][class*="_lines_blk"] [data-testid="stHorizontalBlock"] {
  gap: 0.35rem !important;
  align-items: flex-end !important;
  margin-bottom: 0.08rem !important;
  flex-wrap: nowrap !important;
}
div[class*="st-key-"][class*="_lines_blk"] [data-testid="column"] {
  min-width: 0 !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
}
div[class*="st-key-"][class*="_lines_blk"] label {
  font-size: 0.72rem !important;
}
div[class*="st-key-"][class*="_lines_blk"] .stNumberInput input,
div[class*="st-key-"][class*="_lines_blk"] [data-testid="stSelectbox"] > div > div {
  min-height: 1.85rem !important;
  font-size: 0.8rem !important;
}

/* Reports Center — browse rail stacks above report on tablet/phone */
div[class*="st-key-rpt_hub_row"] [data-testid="stHorizontalBlock"] {
  align-items: flex-start !important;
  flex-wrap: wrap !important;
}
@media (min-width: 993px) {
  div[class*="st-key-rpt_hub_row"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:first-child {
    flex: 0 1 22rem !important;
    max-width: 26rem !important;
    min-width: 18rem !important;
  }
  div[class*="st-key-rpt_hub_row"] [data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child {
    flex: 1 1 20rem !important;
    min-width: min(100%, 320px) !important;
  }
}
@media (max-width: 992px) {
  div[class*="st-key-rpt_hub_row"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 100% !important;
    max-width: 100% !important;
    min-width: 100% !important;
  }
}
div[class*="st-key-rpt_nav_sidebar"] {
  max-width: 100%;
}
@media (min-width: 993px) {
  div[class*="st-key-rpt_nav_sidebar"] {
    max-width: 26rem;
  }
}
div[class*="st-key-rpt_nav_sidebar"] .stTextInput input,
div[class*="st-key-rpt_nav_sidebar"] [data-testid="stSelectbox"] > div > div {
  font-size: 0.82rem !important;
  min-height: 1.85rem !important;
}
/* Full report titles — no ellipsis truncation */
div[class*="st-key-rpt_nav_sidebar"] [data-baseweb="radio"] label,
div[class*="st-key-rpt_nav_sidebar"] [data-baseweb="radio"] label p,
div[class*="st-key-rpt_nav_sidebar"] [data-baseweb="radio"] label span {
  font-size: 0.84rem !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: unset !important;
  line-height: 1.35 !important;
  word-break: break-word !important;
}
div[class*="st-key-rpt_nav_sidebar"] [data-baseweb="radio"] label {
  padding: 0.28rem 0 !important;
  align-items: flex-start !important;
}
div[class*="st-key-rpt_nav_sidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
div[class*="st-key-rpt_nav_sidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] span {
  white-space: normal !important;
  text-overflow: unset !important;
  overflow: visible !important;
  height: auto !important;
  min-height: 1.85rem !important;
}
div[class*="st-key-rpt_nav_sidebar"] .stButton > button {
  white-space: normal !important;
  height: auto !important;
  min-height: 2rem !important;
  line-height: 1.3 !important;
  text-align: left !important;
}
div[class*="st-key-rpt_nav_sidebar"] h5 {
  font-size: 0.88rem !important;
  margin: 0.5rem 0 0.2rem 0 !important;
}
/* Select dropdown options — show full labels (Popular picker, etc.) */
div[data-baseweb="popover"] ul[role="listbox"],
div[data-baseweb="popover"] [data-baseweb="menu"] {
  min-width: max(100%, 18rem) !important;
  max-width: min(36rem, 92vw) !important;
}
div[data-baseweb="popover"] li[role="option"],
div[data-baseweb="popover"] [role="option"] {
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: unset !important;
  line-height: 1.35 !important;
  height: auto !important;
  min-height: 2rem !important;
  padding-top: 0.4rem !important;
  padding-bottom: 0.4rem !important;
}
div[class*="st-key-rpt_period_bar"] .stButton > button {
  min-height: 1.75rem !important;
  padding: 0.1rem 0.35rem !important;
  font-size: 0.72rem !important;
  white-space: nowrap !important;
}
div[class*="st-key-rpt_period_bar"] [data-testid="stHorizontalBlock"] {
  gap: 0.2rem !important;
}
div[class*="st-key-rpt_filter_party"] [data-testid="stHorizontalBlock"] {
  align-items: flex-start !important;
  gap: 0.5rem !important;
}
div[class*="st-key-rpt_filter_party"] label {
  font-size: 0.76rem !important;
}
div[class*="st-key-rpt_filter_party"] .stCaption,
div[class*="st-key-rpt_filter_party"] [data-testid="stCaptionContainer"] {
  font-size: 0.7rem !important;
}
.rpt-hub-card h4 { font-size: 0.95rem !important; margin: 0 0 2px 0 !important; }
.rpt-hub-card p { font-size: 0.8rem !important; line-height: 1.35 !important; }
div[class*="st-key-rpt_run_row"] .stButton > button[kind="primary"] {
  min-height: 2rem !important;
  max-width: 10rem;
}

/* Date / filter toolbars (Cash Book, Bank Book, etc.) */
div[class*="st-key-"][class*="_datenav"] {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  width: 100%;
}
div[class*="st-key-"][class*="_datenav"] [data-testid="stHorizontalBlock"] {
  gap: 0.2rem !important;
  align-items: flex-end !important;
  margin-bottom: 0.15rem !important;
  flex-wrap: nowrap !important;
  min-width: min-content;
}
div[class*="st-key-"][class*="_datenav"] [data-testid="column"] {
  flex: 0 0 auto !important;
  min-width: 4.5rem !important;
}
div[class*="st-key-rpt_period_bar"] {
  overflow-x: auto;
  width: 100%;
}
div[class*="st-key-rpt_period_bar"] [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important;
  min-width: min-content;
}
div[class*="st-key-rpt_period_bar"] [data-testid="column"] {
  flex: 0 0 auto !important;
  min-width: 5rem !important;
}
div[class*="st-key-"][class*="_datenav"] label {
  font-size: 0.72rem !important;
  padding-bottom: 0.1rem !important;
}
div[class*="st-key-"][class*="_datenav"] .stButton > button {
  min-height: 1.85rem !important;
  padding: 0.12rem 0.4rem !important;
  font-size: 0.78rem !important;
}
div[class*="st-key-"][class*="_datenav"] p {
  margin: 0 !important;
  font-size: 0.9rem !important;
  line-height: 1.85rem !important;
}

/* Dashboard KPI — responsive tweaks only */
@media (max-width: 900px) {
  .dash-kpi-value { font-size: 1.15rem !important; }
}
@media (max-width: 520px) {
  .dash-kpi { padding: 0.65rem 0.75rem !important; }
}

/* Forms — one field per row on phones */
@media (max-width: 720px) {
  [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 100% !important;
  }
}

/* Odoo-style home — large desktop app icons (main content) */
.erp-odoo-home-header {
  text-align: center;
  margin: 0.5rem 0 1.75rem 0;
}
.erp-odoo-home-title {
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 800;
  color: #1E3A8A;
  margin: 0 0 0.35rem 0;
}
.erp-odoo-home-sub {
  color: #000000;
  opacity: 0.8;
  font-size: 1rem;
  margin: 0;
}
.erp-odoo-module-title {
  font-size: 1.35rem;
  font-weight: 800;
  color: #1E3A8A;
  margin: 0.35rem 0 0.75rem 0;
}
.erp-odoo-tile {
  border-radius: 14px;
  padding: clamp(1.25rem, 3vw, 2rem) 0.5rem;
  text-align: center;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.18);
  margin-bottom: 0.35rem;
  min-height: clamp(88px, 14vw, 120px);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.erp-odoo-tile-icon {
  font-size: clamp(2.25rem, 5vw, 3.25rem);
  line-height: 1;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.15));
}
.erp-odoo-tile-label {
  text-align: center;
  font-size: 0.88rem;
  font-weight: 600;
  color: #000000;
  margin: 0.15rem 0 0.35rem 0;
  line-height: 1.25;
  min-height: 2.4em;
}
.erp-nav-crumb {
  margin: 0.55rem 0 0 0;
  font-size: 0.95rem;
  color: #000000;
  opacity: 0.8;
}
div[class*="st-key-odoo_mod_odoo_grid"] [data-testid="column"] .stButton > button,
div[class*="st-key-odoo_scr_"] [data-testid="column"] .stButton > button {
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  padding: 0.3rem 0.5rem !important;
  min-height: 2rem !important;
  border-radius: 8px !important;
  margin-top: -0.15rem;
}
div[class*="st-key-odoo_mod_odoo_grid"] [data-testid="column"],
div[class*="st-key-odoo_scr_"] [data-testid="column"] {
  padding: 0.35rem 0.5rem !important;
}
@media (max-width: 720px) {
  .erp-odoo-tile { min-height: 76px; padding: 1rem 0.25rem; }
  .erp-odoo-tile-icon { font-size: 2rem; }
}

/* Sidebar — desktop-style module / screen icon grid */
section[data-testid="stSidebar"] {
  min-width: 17.5rem !important;
}
section[data-testid="stSidebar"] .erp-nav-ico {
  text-align: center;
  font-size: 1.65rem;
  line-height: 1;
  margin: 0.15rem 0 0.05rem 0;
  user-select: none;
}
div[class*="st-key-nav_grp_grid"] [data-testid="column"] .stButton > button,
div[class*="st-key-nav_scr_grid"] [data-testid="column"] .stButton > button {
  font-size: 0.62rem !important;
  font-weight: 600 !important;
  padding: 0.28rem 0.2rem !important;
  min-height: 2.35rem !important;
  line-height: 1.15 !important;
  white-space: normal !important;
  word-break: break-word !important;
  border-radius: 8px !important;
}
div[class*="st-key-nav_grp_grid"] [data-testid="column"],
div[class*="st-key-nav_scr_grid"] [data-testid="column"] {
  padding: 0.12rem !important;
}
div[class*="st-key-nav_grp_grid"] [data-testid="column"] .stButton,
div[class*="st-key-nav_scr_grid"] [data-testid="column"] .stButton {
  margin-bottom: 0.15rem;
}
@media (max-width: 1100px) {
  section[data-testid="stSidebar"] {
    min-width: 15rem !important;
  }
  section[data-testid="stSidebar"] .erp-nav-ico {
    font-size: 1.45rem;
  }
}

@media (max-width: 720px) {
  .erp-portal-root ~ div [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
  }
  .mobile-approval-root .stButton button {
    min-height: 3rem !important;
    font-size: 1rem !important;
  }
  [data-testid="stDataFrame"] > div {
    overflow-x: auto !important;
  }
  div[class*="st-key-mod_topbar"] [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
  }
  .mobile-friendly .stButton button {
    min-height: 2.75rem !important;
    padding: 0.5rem 1rem !important;
  }
}

/* Page shell — Option D */
.erp-shell-crumb {
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 0.2rem 0;
  font-weight: 600;
}
.erp-page-shell .main-header .erp-shell-badge,
.erp-page-shell .main-header .inv-badge-draft,
.erp-page-shell .main-header .inv-badge-pending,
.erp-page-shell .main-header .inv-badge-approved,
.erp-page-shell .main-header .inv-badge-rejected,
.erp-page-shell .main-header .inv-badge-cancelled {
  margin-left: 0.55rem;
  vertical-align: middle;
}
.erp-shell-badge {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  border: 1px solid transparent;
}
.erp-shell-badge-draft { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
.erp-shell-badge-pending { background: #ffedd5; color: #9a3412; border-color: #fdba74; }
.erp-shell-badge-posted { background: #dcfce7; color: #166534; border-color: #86efac; }
.erp-shell-badge-shadow { background: #dbeafe; color: #1e40af; border-color: #93c5fd; }
.erp-shell-badge-muted { background: #f1f5f9; color: #475569; border-color: #cbd5e1; }
.erp-shell-badge-rejected { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.erp-shell-footer {
  font-size: 0.75rem;
  color: #64748b;
  margin: 0.75rem 0 0 0;
  padding-top: 0.5rem;
  border-top: 1px solid #e2e8f0;
}
body:has(.erp-shell-action-bar-marker) div[class*="st-key-sal_new_act_bar"] {
  position: sticky;
  bottom: 0;
  z-index: 40;
  background: rgba(255,255,255,0.97);
  border-top: 1px solid rgba(29,78,216,0.25);
  padding: 0.45rem 0;
  margin-top: 0.5rem;
}
.erp-mywork-panel {
  border: 1px solid rgba(29,78,216,0.28);
  border-radius: 8px;
  background: #fff;
  padding: 0.65rem 0.85rem;
  margin-bottom: 0.75rem;
}
.erp-mywork-title {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #1e3a8a;
  margin: 0 0 0.45rem 0;
}
.erp-mywork-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.35rem 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 0.85rem;
}
.erp-mywork-row:last-child { border-bottom: none; }
.erp-mywork-detail { font-size: 0.75rem; color: #64748b; }

</style>
"""


def inject_layout_styles():
    import streamlit as st
    from erp_ui.theme import BRAND_CSS
    from erp_ui.mobile_layout import inject_mobile_layout
    # Marker lets theme CSS collapse this wrapper so it does not eat flex gap.
    st.markdown(
        BRAND_CSS
        + GLOBAL_LAYOUT_CSS
        + '<div class="erp-css-inject" aria-hidden="true">&#8203;</div>',
        unsafe_allow_html=True,
    )
    inject_mobile_layout()
