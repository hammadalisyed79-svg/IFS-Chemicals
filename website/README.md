# IFS Chemicals — marketing website

Next.js marketing site for **https://ifschemicals.com** (Vercel project `ifs-website`).
Company ERP stays on **https://erp.ifschemicals.com/** — do not point the apex domain at the ERP server.

Canonical working copy on this machine: `C:\ifs-chemicals` (linked to Vercel).
This `website/` folder is the same source tree checked into the ERP GitHub repo for backup/discovery.

## Local

```bash
cd website   # or C:\ifs-chemicals
npm install
npm run dev
```

Optional Neon (contact form persistence) + notify:

```bash
cp .env.example .env.local
# paste DATABASE_URL from Neon console (pooled)
npm run db:setup   # optional; API also creates the table on first save
```

In **Vercel → ifs-website → Settings → Environment Variables**, set:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Store inquiries in Neon (required for inbox) |
| `RESEND_API_KEY` | Optional email notify |
| `CONTACT_NOTIFY_EMAIL` | Optional recipient (default `info@ifschemicals.com`) |
| `CONTACT_NOTIFY_WEBHOOK_URL` | Optional Slack/Discord/Make webhook |

Without `DATABASE_URL`, inquiries still succeed (console log + WhatsApp follow-up link). The floating WhatsApp button is always available.

## Deploy (Vercel)

Production is already on project **ifs-website**:
- https://ifs-website-phi.vercel.app
- Domains attached: `ifschemicals.com`, `www.ifschemicals.com`

Redeploy from `C:\ifs-chemicals`:

```bash
npx vercel deploy --prod --yes
```

Optional: set `DATABASE_URL` in Vercel project env for contact form storage.

## SEO (Phase 3)

- Sitemap: https://ifschemicals.com/sitemap.xml
- Robots: https://ifschemicals.com/robots.txt
- LocalBusiness JSON-LD is embedded site-wide
- Claim / verify the business in [Google Business Profile](https://business.google.com/) using address Bridge Canal Saroki, Gujrat, and link the website URL

## Catalog depth (Phase 4)

- Per-platform and per-SKU pages under `/products/[slug]` (e.g. `/products/happy-detergent`)
- Packaging / PET / corrugated platform pages include capability galleries
- Distributor price lists stay behind the partner portal (`erp.ifschemicals.com`) — public site links to request access / open portal

## GoDaddy DNS cutover (apex is currently Parked)

In GoDaddy → DNS for `ifschemicals.com` (nameservers `ns19`/`ns20.domaincontrol.com`):

1. **Delete** the Parked / forwarding A records on `@` (currently resolving to `3.33.130.190` and `15.197.148.33`).
2. **Add** apex:
   - Type: **A**
   - Name: **@**
   - Value: **76.76.21.21**
   - TTL: 600 (or default)
3. **Replace** `www` (today CNAME → `ifschemicals.com`) with either:
   - Type: **CNAME**, Name: **www**, Value: **cname.vercel-dns.com**
   - or Type: **A**, Name: **www**, Value: **76.76.21.21**
4. **Do not change** `erp` A record (`erp` → `138.201.139.157`).

After DNS propagates, https://ifschemicals.com and https://www.ifschemicals.com serve this Next.js site. SSL is issued by Vercel once the A/CNAME records validate.

## Content

Brand copy and product lines: detergents, bars & oil, dishwash/toilet, packaging, PET; ERP Login CTA → erp.ifschemicals.com.
