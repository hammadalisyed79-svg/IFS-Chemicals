# Security Audit — V16.0

**Audit type:** Platform security review (automated + code structure)  
**Date:** 2026-07-03  

---

## Summary

| Area | Rating | Notes |
|------|--------|-------|
| API authentication | B+ | JWT with configurable secret |
| Session management | B | Idle timeout (V15), URL token legacy |
| Password storage | B | PBKDF2 new; SHA-256 legacy supported |
| Portal isolation | A | Automated tests pass |
| SQL injection | B+ | Parameterized queries; review dynamic ORDER BY |
| File access | B | Documents in `data/documents/` — verify upload sanitization |
| Multi-tenancy | C+ | Columns added; enforcement partial |
| Secrets in config | B | JWT in `erp_config`; use env override in production |

---

## V16 improvements

- JWT API auth separate from Streamlit session
- Centralized `erp_config` security section
- Access logging (`access_log`, `login_attempts`)
- API bound to localhost by default
- Integration connectors inactive until explicitly enabled

---

## Open items (from V14/V15)

| ID | Issue | Priority |
|----|-------|----------|
| S-01 | Streamlit session in URL query param | High |
| S-02 | Enforce `company_id` on all queries | Medium |
| S-03 | Rate limit API login | Medium |
| S-04 | Rotate JWT secret procedure documented | Low |

---

## Automated security tests

```
tests/test_portal_security.py  — 6/6 PASS
tests/test_api_v1.py           — 3/3 PASS
```

---

## Production checklist

- [ ] HTTPS via Nginx
- [ ] `ssl_configured=1`
- [ ] Change admin password
- [ ] Set `IFS_SECURITY_JWT_SECRET` env var
- [ ] Do not expose ports 8501/8502/8600
- [ ] Firewall per FIREWALL_SECURITY_GUIDE.md

---

## Verdict

**Suitable for secured pilot deployment** with HTTPS and checklist complete.  
**Full enterprise security certification** pending S-01 resolution and multi-tenant query enforcement.
