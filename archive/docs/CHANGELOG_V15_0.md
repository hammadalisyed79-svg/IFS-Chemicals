# CHANGELOG — V15.0

## V15.0 — Multi-Access Web + Distributor Portal (2026-07-02)

### Added
- Distributor portal (catalogue, cart, orders, invoices, payment proof, profile)
- `portal_app.py` for `/portal` reverse-proxy deployment
- Price list master and distributor assignment UI
- Mobile Approvals for distributor orders
- Internal **Distributor Orders** admin screen
- `erp_notifications` in-app notification store
- Enterprise role matrix (20 roles)
- Login lockout, session idle timeout, access logging
- Deployment guides (Nginx, systemd, firewall, SSL)
- Automated portal security tests

### Changed
- `authenticate()` — lockout, PBKDF2 verify, login audit
- `user_can()` — portal isolation + matrix permissions
- Login screen — SSL warning; removed default password display
- Session TTL reduced to 7 days with idle timeout
- Health Check 2.0 — V15 deployment and portal checks

### Security
- New passwords require 8+ chars, letter + digit
- Distributor users cannot access internal ERP navigation
- Portal queries enforce `linked_customer_id` isolation

### Unchanged
- Existing desktop/server workflow via `app.py`
- All V14 modules and data preserved
