# CHANGELOG — V14.0 Enterprise Release Candidate (RC1)

## V14.0-RC1 (2026-07-02)

### Added
- `db_v14_rc1.py` — approval history, delegation, warehouse `is_closed`, default auto-backup
- `erp_core/document_workflow.py` — unified approve/reject/post/delete
- `erp_core/period_lock.py` — accounting period enforcement
- `erp_core/inventory_guards.py` — stock movement validation
- `erp_core/gl_drilldown.py` — GL ↔ source document navigation
- `erp_core/master_service.py` — deactivate, export, duplicate detection, customer merge
- `erp_core/regression_test.py` — rolled-back smoke tests
- `erp_core/performance_probe.py` — timing metrics
- `erp_core/health_engine.py` — Health Check 2.0 + report writers
- `erp_ui/approval_designer.py` — Administration screen
- Document Hub on all v3 line documents (Open Existing tab)
- `search_journal_vouchers()` in `db_v3.py`

### Changed
- Version → **V14.0 Enterprise Release Candidate (RC1)**
- Document Hub — full action bar (reject, history, GL, PDF)
- Approval engine — history, delegation, escalation fields
- `_adjust_warehouse_stock()` — inventory guard on outbound qty
- Invoice approve — period lock check
- KNOWN_ISSUES.md — regenerated from health run (verified fixes removed)

### Fixed (verified by Health Check 2.0)
- KI-01 Document Hub partial actions
- KI-02 Journal voucher search
- KI-05 Approval Designer UI
- KI-06 Period lock enforcement
- KI-08 v3_pages scaffold message
- KI-10 GL drill-down
- KI-12 Auto backup default

### Remaining (documented in KNOWN_ISSUES.md)
- Streamlit keyboard/double-click limitations
- Production WIP/QC full batch UI
- HR biometric hardware integration
- Master merge/import on every master screen UI
