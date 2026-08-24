# SSL / HTTPS Setup — IFS ERP

## Quick enable (this server)

1. DNS A record: `erp.ifschemicals.com` → `138.201.139.157` (EasyHost Zone Editor)
2. Open **TCP 80** and **TCP 443** in **Hetzner Cloud Firewall**
3. Run as Administrator:

```batch
enable_https.bat
```

4. Open: **https://erp.ifschemicals.com/**

HTTP automatically redirects to HTTPS. Renew / restart later with `restart_https.bat`.

## What it does

- Let's Encrypt certificate for `erp.ifschemicals.com`
- Reverse proxy listens on **80** (redirect + ACME) and **443** (HTTPS)
- Streamlit stays on `127.0.0.1:8501` (not public)
- Sets `ssl_configured = 1` in ERP settings

## Renew certificate (before expiry)

```batch
venv\Scripts\activate.bat
python tools\obtain_letsencrypt.py
restart_https.bat
```

Certs live under `certs\config\live\erp.ifschemicals.com\`.

## Hetzner firewall

| Port | Purpose |
|------|---------|
| 80 | ACME + HTTP→HTTPS redirect |
| 443 | HTTPS ERP |
| 8501 | Do **not** open publicly |

## Notes

- Do **not** point `ifschemicals.com` (website) at the ERP server.
- IP-only HTTPS (`https://138.201.139.157/`) will show a certificate name warning — use the domain.
