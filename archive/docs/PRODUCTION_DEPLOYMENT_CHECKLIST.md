# Production Deployment Checklist — V17.2

## Pre-deployment

- [ ] Run `python tools/generate_v17_2_reports.py`
- [ ] Run `run_tests.bat` — all suites green
- [ ] Resolve security C-01..C-03 (see SECURITY_CERTIFICATION.md)
- [x] Finance cash/bank GL gaps resolved
- [ ] Department UAT sign-off (UAT_TRACKING.md)
- [ ] Backup production database
- [ ] Run `python install/upgrade.py` on target server

## Post-deployment

- [ ] Verify ERP Health Check 100%
- [ ] Smoke test Spray Dryer batch
- [ ] Verify Trial Balance opens
- [ ] Monitor `/metrics` endpoint

## Gate status

- **Functional Tests**: PASS
- **Finance Certified**: PASS
- **Manufacturing Certified**: PASS
- **Warehouse Certified**: PASS
- **Security Certified**: FAIL
- **Performance**: PASS
- **Database Healthy**: PASS