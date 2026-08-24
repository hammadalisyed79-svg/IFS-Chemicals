# IFS Industrial ERP — V14.0 Enterprise Release Candidate (RC1)

**Release:** V14.0-RC1  
**Codename:** Enterprise Release Candidate (RC1)  
**Build:** 20260702  
**Previous:** V13.14  

## Summary

RC1 completes integration work started in V13.14: every major transactional document uses the unified **Document Hub**, **Approval Designer**, **period locking**, **inventory guards**, **GL drill-down**, and **Health Check 2.0** with automated regression and report generation.

## Highlights

### Document Hub (all registered types)
Open, Search, Edit Draft, Duplicate, Delete, Approve, Reject, Post, Print, Export PDF, History — via `erp_ui/document_hub.py` and `erp_core/document_workflow.py`.

### Approval Engine
- Rules, matrix, history, delegation — `erp_ui/approval_designer.py`
- Tables: `erp_approval_rules`, `erp_approval_history`, `erp_approval_delegation`

### Period locking
`erp_core/period_lock.py` enforced on invoice approve, GRN/DN/JV post.

### Inventory guards
`erp_core/inventory_guards.py` — negative stock, inactive item/warehouse, closed warehouse, batch warehouse mismatch.

### GL drill-down
`erp_core/gl_drilldown.py` — document ↔ GL bidirectional links in hub history panel.

### Health Check 2.0
**Administration → ERP Health Check → Run Full RC1 Suite**

Generates:
- `ENTERPRISE_HEALTH_REPORT.md`
- `DATABASE_INTEGRITY_REPORT.md`
- `PERFORMANCE_REPORT.md`
- `TEST_EXECUTION_REPORT.md`
- `KNOWN_ISSUES.md`

### Enterprise Search
Journal vouchers and production orders included.

## Migration

`migrate_v14_rc1_enterprise()` runs on startup via `db_v3.apply_v3()`.

## Launch

```bat
RUN_SOFTWARE.bat
```

Login: `admin` / `admin123`
