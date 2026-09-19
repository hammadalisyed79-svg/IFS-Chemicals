import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

type Body = {
  name?: string;
  email?: string;
  phone?: string;
  message?: string;
};

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const name = String(body.name || "").trim();
  const email = String(body.email || "").trim();
  const phone = String(body.phone || "").trim();
  const message = String(body.message || "").trim();

  if (!name || !email || !message) {
    return NextResponse.json(
      { error: "Name, email, and message are required." },
      { status: 400 },
    );
  }

  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    console.info("[contact]", { name, email, phone, message });
    return NextResponse.json({
      ok: true,
      stored: false,
      note: "DATABASE_URL not set — inquiry logged only.",
    });
  }

  try {
    const sql = neon(databaseUrl);
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
    await sql`
      INSERT INTO contact_inquiries (name, email, phone, message)
      VALUES (${name}, ${email}, ${phone || null}, ${message})
    `;
    return NextResponse.json({ ok: true, stored: true });
  } catch (err) {
    console.error("[contact] neon error", err);
    return NextResponse.json(
      { error: "Could not save inquiry. Please email info@ifschemicals.com." },
      { status: 500 },
    );
  }
}
