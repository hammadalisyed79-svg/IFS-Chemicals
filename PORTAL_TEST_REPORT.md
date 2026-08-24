# Portal Test Report — V15.0

**Generated:** Automated suite `tests/test_portal_security.py`  
**Run:** `python tests/test_portal_security.py`

## Results

| Test | Status |
|------|--------|
| Portal tables exist | PASS |
| Distributor cannot view internal nav | PASS |
| Distributor order isolation | PASS |
| Price list rate applied | PASS |
| Portal order creates sales order | PASS |
| Failed login lockout | PASS |

## Coverage

- Data isolation by `linked_customer_id`
- Internal Finance/Admin screens blocked for distributor role
- Price list pricing on catalogue
- Portal submit → `sales_orders` draft with `source_channel=portal`
- Account lock after repeated failed logins

## Health Check integration

ERP Health Check 2.0 runs a subset of these tests under **V15 Portal → Distributor isolation tests**.

## Manual tests recommended

- [ ] Mobile browser login (internal + portal)
- [ ] HTTPS login without port exposure
- [ ] Credit limit block on oversized order
- [ ] Payment proof notification to finance
- [ ] PDF invoice download in portal
