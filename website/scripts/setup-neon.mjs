/**
 * Optional: create/upgrade contact_inquiries table for Phase 2 fields.
 * Usage: DATABASE_URL=... node scripts/setup-neon.mjs
 * Contact API also auto-migrates columns on first successful save.
 */
import { neon } from "@neondatabase/serverless";

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("Set DATABASE_URL first (Neon pooled connection string).");
  process.exit(1);
}

const sql = neon(url);
await sql`
  CREATE TABLE IF NOT EXISTS contact_inquiries (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    message TEXT NOT NULL,
    inquiry_type TEXT NOT NULL DEFAULT 'general',
    city TEXT,
    volume TEXT,
    brand TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )
`;
await sql`ALTER TABLE contact_inquiries ADD COLUMN IF NOT EXISTS inquiry_type TEXT NOT NULL DEFAULT 'general'`;
await sql`ALTER TABLE contact_inquiries ADD COLUMN IF NOT EXISTS city TEXT`;
await sql`ALTER TABLE contact_inquiries ADD COLUMN IF NOT EXISTS volume TEXT`;
await sql`ALTER TABLE contact_inquiries ADD COLUMN IF NOT EXISTS brand TEXT`;
await sql`ALTER TABLE contact_inquiries ADD COLUMN IF NOT EXISTS quote_items TEXT`;
console.log("contact_inquiries table is ready (Phase 2–5 columns included).");
