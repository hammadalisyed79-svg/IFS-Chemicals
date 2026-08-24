# Enterprise Health Report

**Version:** V17.3 Enterprise Commercial Certification
**Health Score:** 97.9%
**Checks:** 95/97 passed

## Critical Errors
- Regression: Inventory Guard — expected insufficient stock error
- V15 Portal: Distributor isolation tests — Dispatch town is required — where should this order be delivered?
- None

## Warnings
- None

## Recommendations
- Review failed checks in ENTERPRISE_HEALTH_REPORT.md
- None

## Detail

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| PASS | Core | Login Ok | OK |
| PASS | Core | Customer Required | OK |
| PASS | Core | Supplier Required | OK |
| PASS | Core | Blank Sale Blocked | OK |
| PASS | Core | Blank Purchase Blocked | OK |
| PASS | Core | Totals Recalc | OK |
| PASS | Core | Weekly Holidays Table | OK |
| PASS | Core | Draft Registry | OK |
| PASS | Core | V14 Tables | OK |
| PASS | Core | Cash Book Query | OK |
| PASS | Core | Bank Book Query | OK |
| PASS | Core | Gl Table | OK |
| PASS | Core | Enterprise Search Ok | OK |
| PASS | Core | Transaction Engine Registry | OK |
| PASS | Core | Login Ok | OK |
| PASS | Core | Customer Required | OK |
| PASS | Core | Supplier Required | OK |
| PASS | Core | Blank Sale Blocked | OK |
| PASS | Core | Blank Purchase Blocked | OK |
| PASS | Core | Totals Recalc | OK |
| PASS | Core | Weekly Holidays Table | OK |
| PASS | Core | Draft Registry | OK |
| PASS | Core | V14 Tables | OK |
| PASS | Core | Cash Book Query | OK |
| PASS | Core | Bank Book Query | OK |
| PASS | Core | Gl Table | OK |
| PASS | Core | Enterprise Search Ok | OK |
| PASS | Core | Transaction Engine Registry | OK |
| PASS | Menus | Menus Registered | OK |
| PASS | Menus | Duplicate Page Ids | OK |
| PASS | Database | Foreign Keys On | OK |
| PASS | UI | Scaffold Scan | OK |
| PASS | Reports | Report Catalog Nonempty | OK |
| PASS | Approval | Approval Rules Seeded | OK |
| PASS | Regression | Create Customer | OK |
| PASS | Regression | Create Supplier | OK |
| PASS | Regression | Create Product | OK |
| PASS | Regression | Validation Blocks Blank Sale | OK |
| PASS | Regression | Period Lock Check | OK |
| FAIL | Regression | Inventory Guard | expected insufficient stock error |
| PASS | Regression | Gl Drilldown | OK |
| PASS | Regression | Document Workflow Registry | OK |
| PASS | Regression | Enterprise Search | OK |
| PASS | Regression | Journal Search | OK |
| PASS | Performance | startup_init_db | 0.0 ms |
| PASS | Performance | enterprise_search | 101.79 ms |
| PASS | Performance | cash_book_query | 5.42 ms |
| PASS | Performance | db_simple_query | 6.91 ms |
| PASS | Database | Foreign keys pragma | OK |
| PASS | Database | Document sequences | OK |
| PASS | Approval | Approval rules exist | OK |
| PASS | Document Hub | All specs have search or get | OK |
| PASS | Scaffold | No user-facing scaffold messages | OK |
| PASS | V15 Mobile | Streamlit config exists | OK |
| PASS | V15 Portal | portal_app.py exists | OK |
| PASS | V15 Portal | Portal routes module | OK |
| PASS | V15 Security | Deployment guides exist | OK |
| PASS | V15 Database | Notification table | OK |
| PASS | V15 Database | Portal orders table | OK |
| PASS | V15 Database | Price lists table | OK |
| PASS | V15 Database | Role permission matrix | OK |
| PASS | V15 Security | Login attempts table | OK |
| PASS | V15 Roles | Enterprise roles seeded | OK |
| FAIL | V15 Portal | Distributor isolation tests | Dispatch town is required — where should this order be delivered? |
| PASS | V15 Security | Lockout settings | OK |
| PASS | V16 Architecture | Layer presentation/ | OK |
| PASS | V16 Architecture | Layer application/ | OK |
| PASS | V16 Architecture | Layer domain/ | OK |
| PASS | V16 Architecture | Layer infrastructure/ | OK |
| PASS | V16 Architecture | Layer api/ | OK |
| PASS | V16 Architecture | Layer integrations/ | OK |
| PASS | V16 Architecture | Layer services/ | OK |
| PASS | V16 Architecture | Layer security/ | OK |
| PASS | V16 API | FastAPI app | OK |
| PASS | V16 Database | Companies table | OK |
| PASS | V16 Database | Job queue | OK |
| PASS | V16 Database | Domain events | OK |
| PASS | V16 Database | Document repository | OK |
| PASS | V16 Config | erp_config | OK |
| PASS | V16 Integrations | Connector registry | OK |
| PASS | V16 Platform | Platform tests | OK |
| PASS | V16 API | API tests | OK |
| PASS | V17 Plugins | Plugin SDK | OK |
| PASS | V17 Plugins | Sample plugin loads | OK |
| PASS | V17 Rules | Rule engine | OK |
| PASS | V17 Workflows | Workflow designer | OK |
| PASS | V17 Scripts | Script sandbox | OK |
| PASS | V17 Tenant | Coverage >= 80% | OK |
| PASS | V17 Migrations | Graph valid | OK |
| PASS | V17 API | Prometheus endpoint | OK |
| PASS | V17 Platform | V17 tests | OK |
| PASS | V17.1 Manufacturing | Industrial services | OK |
| PASS | V17.1 Manufacturing | Integration adapters | OK |
| PASS | V17.1 Manufacturing | V17.1 tests | OK |
| PASS | V17.2 Validation | Certification suite | OK |
| PASS | V17.2 Validation | UAT tables | OK |
| PASS | V17.2 Validation | V17.2 smoke tests | OK |