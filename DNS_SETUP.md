# DNS setup for IFS ERP and website

## Hosts (target end state)

| Host | Points to | What you see |
|------|-----------|--------------|
| **ifschemicals.com** / **www** | Vercel `76.76.21.21` (or CNAME `cname.vercel-dns.com` for www) | Next.js marketing site |
| **erp.ifschemicals.com** | 138.201.139.157 | IFS Industrial ERP |

Do **not** point the apex domain at the ERP IP or the public website goes offline.

## Current issue (apex Parked)

GoDaddy authoritative DNS currently serves parking IPs for `@`:

- `3.33.130.190`
- `15.197.148.33`

`www` is a CNAME to `ifschemicals.com`. Nameservers: `ns19.domaincontrol.com` / `ns20.domaincontrol.com`.

The marketing site is already deployed on Vercel (`ifs-website` → https://ifs-website-phi.vercel.app) with both domains attached, but DNS still points at GoDaddy parking — so the custom domain does not serve the site yet.

### GoDaddy changes required

| Action | Type | Name | Value |
|--------|------|------|-------|
| Delete | A (Parked / forwarding) | @ | 3.33.130.190 / 15.197.148.33 |
| Add | A | @ | **76.76.21.21** |
| Replace | CNAME (or A) | www | **cname.vercel-dns.com** (or A **76.76.21.21**) |
| Keep | A | erp | **138.201.139.157** |

Optional TXT verification records only if Vercel shows them in Domains settings.

## ERP subdomain (already correct pattern)

```
Type   Name   Value               TTL
A      erp    138.201.139.157     300
```

Result: **https://erp.ifschemicals.com/** → ERP login

Optional distributor portal: **https://erp.ifschemicals.com/portal**

## Verify

```powershell
nslookup ifschemicals.com ns19.domaincontrol.com
# Expect: 76.76.21.21

nslookup erp.ifschemicals.com
# Must show: 138.201.139.157
```

Marketing site source: `website/` in this repo and `C:\ifs-chemicals` on the server.

## Vercel project notes

| Vercel project | Purpose |
|----------------|---------|
| **ifs-website** | Correct Next.js marketing deploy (`ifs-website-phi.vercel.app`) |
| **ifs-chemicals** | Same GitHub repo — must build from `website/` (root `vercel.json` copies that folder for install/build). Do not treat the Python ERP root as a Next.js app. |

## EasyHost WordPress (previous production) — restore apex to old host

The site that was live on EasyHost ~10–15 days ago is **WordPress + WooCommerce** still served at IP **`170.249.216.178`**. It was never stored as `public_html` on this Windows server.

Local archive + how-to: **`C:\ifs-chemicals-easyhost`** (does not replace the Vercel Next.js app).

To make **public** `ifschemicals.com` show EasyHost again (instead of Vercel):

| Action | Type | Name | Value |
|--------|------|------|-------|
| Change | A | @ | **170.249.216.178** |
| Change | A / CNAME | www | **170.249.216.178** (or CNAME to apex) |
| Keep | A | erp | **138.201.139.157** |

Temporary preview without DNS change: run `C:\ifs-chemicals-easyhost\VIEW_LIVE_VIA_HOSTS.ps1` (edits local hosts).
