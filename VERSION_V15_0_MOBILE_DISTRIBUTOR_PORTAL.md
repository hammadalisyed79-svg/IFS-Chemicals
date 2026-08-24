# VERSION V15.0 — Multi-Access Web + Distributor Portal

**Release:** V15.0  
**Codename:** Multi-Access Web + Distributor Portal  
**Previous:** V14.0 RC1  

---

## Highlights

### Web & mobile access
- Responsive CSS for phones/tablets (touch buttons, scrollable tables)
- Mobile Approvals screen for internal users
- Desktop browser workflow unchanged (`app.py` + `RUN_SOFTWARE.bat`)

### Distributor portal
- Isolated portal UI (`erp_ui/portal_pages.py`, `portal_app.py`)
- Catalogue, cart, orders, invoices, payments, notifications
- Orders create ERP sales order drafts (`source_channel=portal`)
- Status workflow: Draft → Submitted → Under Review → Approved → … → Delivered

### Price lists
- Masters → **Price Lists** (retail, wholesale, distributor, special, region)
- Per-product rates, discount %, minimum qty
- Distributor assignment + credit limit

### Security
- PBKDF2 password hashing (legacy SHA-256 still accepted)
- Session idle timeout (configurable)
- Failed login lockout
- Login history (`login_attempts`) + access log
- SSL not-configured warning on login
- 20 enterprise roles + `role_permission_matrix`

### Deployment
- `.streamlit/config.toml` — bind `127.0.0.1` only
- Nginx, systemd, firewall, SSL guides for `138.201.139.157`

### Database
- Migration: `db_v15.migrate_v15_0_mobile_portal_distributor()`
- New tables: `portal_orders`, `price_lists`, `erp_notifications`, etc.

### Health Check
- V15 checks: portal routes, isolation tests, deployment config, lockout tables

---

## Upgrade

1. Backup `ifs_erp.db`
2. Start ERP once — migration runs automatically
3. Configure Nginx + HTTPS (see deployment guides)
4. Set `ssl_configured=1` after SSL
5. Create distributor customers + portal users
6. Run Health Check 2.0

---

## Files added

| Area | Path |
|------|------|
| Migration | `db_v15.py` |
| Security | `erp_core/v15_security.py` |
| Portal | `erp_core/portal_service.py`, `erp_ui/portal_pages.py`, `portal_app.py` |
| Notifications | `erp_core/notifications.py` |
| Roles | `erp_core/role_matrix.py` |
| Tests | `tests/test_portal_security.py` |
