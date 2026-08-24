# DNS setup for IFS ERP

## Why ifschemicals.com does not show the ERP

| Host | Points to | What you see |
|------|-----------|--------------|
| **ifschemicals.com** | 170.249.216.178 | Company website (WooCommerce shop) |
| **138.201.139.157** | ERP server | IFS Industrial ERP login |

The main domain is already used for your public website. Do **not** change it to the ERP IP or the shop will go offline.

## Correct setup — ERP subdomain

In **Hetzner DNS** (or your domain registrar), add:

```
Type   Name   Value               TTL
A      erp    138.201.139.157     300
```

Result: **http://erp.ifschemicals.com/** → ERP login

Optional distributor portal: **http://erp.ifschemicals.com/portal**

## Use ERP immediately (before DNS)

Open in browser:

```
http://138.201.139.157/
```

## On the ERP server (Administrator)

```batch
run_external_port80.bat
setup_domain.bat
```

## HTTPS (production)

1. Issue SSL certificate for `erp.ifschemicals.com`
2. ERP → Administration → System Settings → set `ssl_configured = 1`
3. Use **https://erp.ifschemicals.com/**

## Verify

```powershell
nslookup erp.ifschemicals.com
# Must show: 138.201.139.157
```
