# CHANGELOG — V13.14 Enterprise Workflow & Integration

## V13.14 (2026-07-02)

### Added
- `erp_core/transaction_engine.py` — unified document registry and lifecycle hooks
- `erp_core/enterprise_search.py` — cross-module search (documents + masters)
- `erp_core/approval_engine.py` — configurable approval rules
- `erp_core/print_engine.py` — print logging and watermarks
- `erp_core/inventory_service.py` — real-time stock position buckets
- `erp_core/error_handler.py` — professional error dialogs + error log
- `erp_core/maintenance.py` — startup backup/optimize/cleanup
- `erp_core/services/` — posting and audit service facades
- `erp_ui/enterprise_search.py` — toolbar search widget
- `erp_ui/document_hub.py` — Open Existing document center
- `erp_ui/line_entry_engine.py` — unified line grid with copy/paste/move
- `db_v13_14.py` — safe migration (approval rules, error log, print log, favorites, period locks)
- Sales / Purchase **Open Existing** tabs
- Report Center favorites and recent reports
- Expanded Enterprise Health Check + `HEALTH_CHECK_REPORT.md` generation

### Changed
- App title and version → **V13.14 Enterprise Workflow & Integration**
- Module topbar and CEO desktop toolbar include enterprise search
- `app.py` main router catches exceptions per screen
- `database.init_db()` runs startup maintenance after schema apply

### Preserved
- All existing menus, screens, and data
- V13.13 workflow columns and draft registry
- Admin login (`admin` / `admin123`)
- `RUN_SOFTWARE.bat` launch path

### Migration
- Additive only — no data reset
- Schema marker: `erp_v13_14_enterprise`
