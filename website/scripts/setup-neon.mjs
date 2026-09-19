/**
 * Optional: create contact_inquiries table.
 * Usage: DATABASE_URL=... node scripts/setup-neon.mjs
 * Contact API also auto-creates the table on first successful save.
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )
`;
console.log("contact_inquiries table is ready.");
