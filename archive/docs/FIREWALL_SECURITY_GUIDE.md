# Firewall & Network Security — IFS ERP V15

**Server:** `138.201.139.157`

## UFW (Ubuntu)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'    # 80 + 443 only
sudo ufw deny 8501
sudo ufw deny 8502
sudo ufw enable
sudo ufw status verbose
```

## Rules summary

| Port | Exposure | Purpose |
|------|----------|---------|
| 22 | Restrict to admin IPs if possible | SSH |
| 80 | Public | HTTP → HTTPS redirect |
| 443 | Public | Nginx HTTPS |
| 8501 | **localhost only** | Internal ERP |
| 8502 | **localhost only** | Distributor portal |

## Never do this in production

```
http://138.201.139.157:8501   ← blocked / not exposed
```

## Additional hardening

- Fail2ban on SSH and Nginx 401/403 storms
- Rate-limit login at Nginx (`limit_req_zone`)
- Daily off-site backup of `ifs_erp.db`
- Separate OS user `ifs` with no shell login for service account if desired
