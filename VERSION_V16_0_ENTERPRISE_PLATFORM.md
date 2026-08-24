# VERSION V16.0 — Enterprise Platform Modernization

**Release:** V16.0  
**Previous:** V15.0 Multi-Access Web + Distributor Portal  
**Build:** 20260703  

---

## Mission accomplished

Transform IFS ERP into a **commercial multi-company platform** without adding new business modules.

- Existing ERP, portal, and workflows: **preserved**
- Feature freeze: **honored**
- Platform layers, API, events, jobs, docs: **delivered**

---

## Quick start

```batch
install\windows_install.bat
RUN_SOFTWARE.bat    REM ERP
RUN_API.bat         REM API docs at /api/v1/docs
```

```bash
python tests/test_v16_platform.py
python tests/test_api_v1.py
```

Health Check: Administration → **ERP Health Check** (expect 100%)

---

## Key documents

| Document | Purpose |
|----------|---------|
| ENTERPRISE_ARCHITECTURE_REPORT.md | Layer diagram & scores |
| API_DOCUMENTATION.md | REST API reference |
| DATABASE_DICTIONARY.md | V16 tables |
| INSTALLATION_GUIDE.md | Install steps |
| UPGRADE_GUIDE.md | V15 → V16 |
| PRODUCTION_CERTIFICATION.md | Certification verdict |
| SECURITY_AUDIT_V16.md | Security review |
| LOAD_TEST_REPORT.md | Performance baseline |

---

## Architecture rule for developers

```
erp_ui (presentation) → application.services → infrastructure / database
api (REST)           → application.services → infrastructure / database
```

Do not add business rules in `erp_ui/` or `api/` route handlers.
