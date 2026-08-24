# Security & Deployment Guide — V15.0

Consolidated security reference for production on **138.201.139.157**.

## Production access model

```
✅ https://138.201.139.157/          → Internal ERP (Nginx → :8501)
✅ https://138.201.139.157/portal/   → Distributor portal (Nginx → :8502)
❌ http://138.201.139.157:8501       → NEVER expose
```

## Document index

| Guide | Purpose |
|-------|---------|
| `DEPLOYMENT_SERVER_GUIDE.md` | End-to-end server setup |
| `NGINX_CONFIG_SAMPLE.conf` | Reverse proxy template |
| `SYSTEMD_SERVICE_SAMPLE.service` | Service unit template |
| `FIREWALL_SECURITY_GUIDE.md` | UFW / port rules |
| `SSL_SETUP_GUIDE.md` | HTTPS certificates |
| `REMOTE_ACCESS_SECURITY.md` | Access policies & audit |

## Application security settings

| Key | Default | Description |
|-----|---------|-------------|
| `ssl_configured` | 0 | Set 1 when HTTPS live |
| `session_idle_minutes` | 480 | Auto logout after idle |
| `max_failed_logins` | 5 | Lockout threshold |
| `lockout_minutes` | 30 | Lock duration |
| `password_min_length` | 8 | New password policy |

## Role model

- Internal users: `user_type=internal` + role from matrix
- Distributors: `user_type=distributor` + `linked_customer_id`
- Portal-only: no internal `NAV_GROUPS` visibility

## Verification

```bash
python tests/test_portal_security.py
python -c "from erp_core.health_engine import run_health_check_2, write_all_reports; write_all_reports(run_health_check_2())"
```

## Remaining V14 certification items

V15 adds external access; complete V14 accounting/security fixes (see `ENTERPRISE_CERTIFICATION_REPORT.md`) before full enterprise sign-off.
