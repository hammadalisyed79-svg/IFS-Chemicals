# Open port 80 in Hetzner Cloud (required for external ERP access)

RDP works but `http://138.201.139.157/` times out because **Hetzner Cloud Firewall** blocks port **80** from the internet. Windows firewall alone is not enough.

## Steps (5 minutes)

1. Open **https://console.hetzner.cloud**
2. Select your **project**
3. Go to **Firewalls** (left menu)
   - If the server has no firewall: **Create Firewall** → name it `ifs-erp`
   - If a firewall exists: click it → **Rules**
4. Add **Inbound rule**:

   | Field | Value |
   |-------|--------|
   | Protocol | **TCP** |
   | Port | **80** |
   | Source | **0.0.0.0/0** (anywhere) |

5. **Apply** the firewall to your ERP server (`138.201.139.157`)
6. Wait 30 seconds, then test: **http://138.201.139.157/**

## Optional (HTTPS later)

| Port | Purpose |
|------|---------|
| 443 | HTTPS (production) |
| 8501 | Do **not** open — ERP stays internal |

## On the ERP server (Windows)

Run as **Administrator**:

```batch
open_erp_firewall.bat
restart_external.bat
```

## Verify from your PC

```powershell
Test-NetConnection 138.201.139.157 -Port 80
```

`TcpTestSucceeded : True` → open **http://138.201.139.157/** in browser.

## Domain (after port 80 works)

Add DNS A record:

```
erp.ifschemicals.com  →  138.201.139.157
```

Use: **http://erp.ifschemicals.com/**

Keep **ifschemicals.com** on your website server (170.249.216.178).
