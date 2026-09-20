import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";
import type { LeadRow } from "@/lib/leads";

function unauthorized() {
  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

function checkAuth(req: NextRequest): boolean {
  const secret = process.env.LEADS_ADMIN_SECRET?.trim();
  if (!secret) return false;

  const header = req.headers.get("authorization") || "";
  if (header === `Bearer ${secret}`) return true;

  const alt = req.headers.get("x-leads-admin-secret") || "";
  return alt === secret;
}

async function ensureSchema(sql: {
  (strings: TemplateStringsArray, ...params: unknown[]): Promise<unknown>;
}) {
  await sql`ALTER TABLE contact_inquiries ADD COLUMN IF NOT EXISTS quote_items TEXT`;
}

export async function GET(req: NextRequest) {
  if (!checkAuth(req)) return unauthorized();

  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (!databaseUrl) {
    return NextResponse.json(
      { error: "DATABASE_URL is not configured on the server." },
      { status: 503 },
    );
  }

  const url = new URL(req.url);
  const limitRaw = Number(url.searchParams.get("limit") || "50");
  const limit = Math.min(200, Math.max(1, Number.isFinite(limitRaw) ? limitRaw : 50));
  const type = (url.searchParams.get("type") || "").trim().toLowerCase();

  try {
    const sql = neon(databaseUrl);
    await ensureSchema(sql);

    const rows =
      type && ["general", "distributor", "b2b", "quote"].includes(type)
        ? ((await sql`
            SELECT
              id, name, email, phone, message, inquiry_type, city, volume, brand,
              quote_items, created_at
            FROM contact_inquiries
            WHERE inquiry_type = ${type}
            ORDER BY created_at DESC
            LIMIT ${limit}
          `) as LeadRow[])
        : ((await sql`
            SELECT
              id, name, email, phone, message, inquiry_type, city, volume, brand,
              quote_items, created_at
            FROM contact_inquiries
            ORDER BY created_at DESC
            LIMIT ${limit}
          `) as LeadRow[]);

    return NextResponse.json({
      ok: true,
      count: rows.length,
      leads: rows,
    });
  } catch (err) {
    console.error("[admin/leads]", err);
    return NextResponse.json(
      { error: "Could not load leads from the database." },
      { status: 500 },
    );
  }
}
