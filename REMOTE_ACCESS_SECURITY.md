# Remote Access Security — IFS ERP V15

## Principles

1. **HTTPS only** for internet access.
2. **Reverse proxy** — never publish Streamlit ports.
3. **Role separation** — distributors use portal only (`user_type` = distributor).
4. **Data isolation** — every portal query filters by `linked_customer_id`.
5. **Audit** — `login_attempts`, `access_log`, `db_audit` events.

## V15 security controls

| Control | Implementation |
|---------|----------------|
| Session timeout | `session_idle_minutes` (default 480) + `user_sessions.last_activity_at` |
| Failed login lockout | `max_failed_logins` (5) / `lockout_minutes` (30) |
| Strong passwords | PBKDF2-SHA256 for new passwords; min 8 chars + letter + digit |
| Password change | `must_change_password` flag + change password screen |
| IP / device logging | `login_attempts`, `user_devices`, `access_log` |
| SSL warning | Shown when `ssl_configured` ≠ 1 |
| Admin protection | Nav + `role_permission_matrix`; distributors blocked from internal nav |

## Distributor portal

- Entry: `portal_app.py` or `/portal` via Nginx
- Distributors **cannot** see Finance, HR, Production, other distributors, or GL
- Orders create internal **Sales Order** drafts for approval

## Operational checklist

- [ ] Change default `admin` password
- [ ] Set `ssl_configured=1` after HTTPS
- [ ] Create distributor users with `linked_customer_id`
- [ ] Assign price lists (Masters → Price Lists)
- [ ] Run `python tests/test_portal_security.py`
- [ ] Review `login_attempts` periodically

## Incident response

1. Disable user (`is_active=0`)
2. Revoke sessions: `DELETE FROM user_sessions WHERE user_id=?`
3. Review `access_log` and `login_attempts`
4. Restore DB from backup if compromise suspected

See also: `SECURITY_DEPLOYMENT_GUIDE.md`
