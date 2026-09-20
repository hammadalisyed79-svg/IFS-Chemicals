import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

type Body = {
  name?: string;
  email?: string;
  phone?: string;
  message?: string;
  inquiryType?: string;
  city?: string;
  volume?: string;
  brand?: string;
};

type Inquiry = {
  name: string;
  email: string;
  phone: string;
  message: string;
  inquiryType: string;
  city: string;
  volume: string;
  brand: string;
};

const ALLOWED_TYPES = new Set(["general", "distributor", "b2b"]);

async function ensureSchema(sql: {
  (strings: TemplateStringsArray, ...params: unknown[]): Promise<unknown>;
}) {
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
}

async function notifyStaff(inquiry: Inquiry) {
  const lines = [
    `New IFS website inquiry (${inquiry.inquiryType})`,
    `Name: ${inquiry.name}`,
    `Email: ${inquiry.email}`,
    `Phone: ${inquiry.phone || "—"}`,
    `City: ${inquiry.city || "—"}`,
    `Volume: ${inquiry.volume || "—"}`,
    `Brand / interest: ${inquiry.brand || "—"}`,
    "",
    inquiry.message,
  ];
  const text = lines.join("\n");

  const webhook = process.env.CONTACT_NOTIFY_WEBHOOK_URL?.trim();
  if (webhook) {
    try {
      await fetch(webhook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          inquiry,
          source: "ifschemicals.com",
        }),
      });
    } catch (err) {
      console.error("[contact] webhook notify failed", err);
    }
  }

  const resendKey = process.env.RESEND_API_KEY?.trim();
  const notifyTo =
    process.env.CONTACT_NOTIFY_EMAIL?.trim() || "info@ifschemicals.com";
  if (resendKey) {
    try {
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${resendKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from:
            process.env.CONTACT_NOTIFY_FROM?.trim() ||
            "IFS Website <onboarding@resend.dev>",
          to: [notifyTo],
          subject: `[IFS] ${inquiry.inquiryType} inquiry from ${inquiry.name}`,
          text,
        }),
      });
      if (!res.ok) {
        console.error("[contact] resend failed", await res.text());
      }
    } catch (err) {
      console.error("[contact] resend error", err);
    }
  }
}

export async function POST(req: NextRequest) {
  let body: Body;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const inquiry: Inquiry = {
    name: String(body.name || "").trim(),
    email: String(body.email || "").trim(),
    phone: String(body.phone || "").trim(),
    message: String(body.message || "").trim(),
    inquiryType: String(body.inquiryType || "general").trim().toLowerCase(),
    city: String(body.city || "").trim(),
    volume: String(body.volume || "").trim(),
    brand: String(body.brand || "").trim(),
  };

  if (!ALLOWED_TYPES.has(inquiry.inquiryType)) {
    inquiry.inquiryType = "general";
  }

  if (!inquiry.name || !inquiry.email || !inquiry.message) {
    return NextResponse.json(
      { error: "Name, email, and message are required." },
      { status: 400 },
    );
  }

  if (
    (inquiry.inquiryType === "distributor" || inquiry.inquiryType === "b2b") &&
    !inquiry.city
  ) {
    return NextResponse.json(
      { error: "City is required for distributor / B2B inquiries." },
      { status: 400 },
    );
  }

  const databaseUrl = process.env.DATABASE_URL;
  let stored = false;

  if (!databaseUrl) {
    console.info("[contact]", inquiry);
  } else {
    try {
      const sql = neon(databaseUrl);
      await ensureSchema(sql);
      await sql`
        INSERT INTO contact_inquiries
          (name, email, phone, message, inquiry_type, city, volume, brand)
        VALUES
          (
            ${inquiry.name},
            ${inquiry.email},
            ${inquiry.phone || null},
            ${inquiry.message},
            ${inquiry.inquiryType},
            ${inquiry.city || null},
            ${inquiry.volume || null},
            ${inquiry.brand || null}
          )
      `;
      stored = true;
    } catch (err) {
      console.error("[contact] neon error", err);
      return NextResponse.json(
        { error: "Could not save inquiry. Please email info@ifschemicals.com or WhatsApp +92 321 6001040." },
        { status: 500 },
      );
    }
  }

  await notifyStaff(inquiry);

  const waText = encodeURIComponent(
    `IFS inquiry (${inquiry.inquiryType})\n${inquiry.name} — ${inquiry.city || "n/a"}\n${inquiry.message.slice(0, 200)}`,
  );

  return NextResponse.json({
    ok: true,
    stored,
    note: stored
      ? undefined
      : "DATABASE_URL not set — inquiry logged only.",
    whatsappFollowUp: `https://wa.me/923216001040?text=${waText}`,
  });
}
