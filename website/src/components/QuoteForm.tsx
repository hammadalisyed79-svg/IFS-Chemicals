"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useQuote } from "@/components/QuoteProvider";
import { trackEvent } from "@/lib/analytics";

export function QuoteForm() {
  const { lines, setQty, remove, clear, count } = useQuote();
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const [whatsappFollowUp, setWhatsappFollowUp] = useState<string | null>(null);

  const field =
    "w-full min-h-12 border border-[var(--line)] bg-white px-3.5 py-3.5 text-base outline-none transition focus:border-[var(--blue)] focus:ring-2 focus:ring-[var(--blue)]/15 sm:min-h-11 sm:py-3 sm:text-sm";

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (lines.length === 0) {
      setStatus("err");
      setMessage("Add at least one product to your quote list.");
      return;
    }

    setStatus("sending");
    setMessage("");
    setWhatsappFollowUp(null);
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());

    const notes = String(data.notes || "").trim();
    const itemLines = lines
      .map((l) => `• ${l.name} × ${l.qty} (${l.pack})`)
      .join("\n");
    const composedMessage = [
      "Quote request from website catalogue",
      "",
      itemLines,
      notes ? `\nNotes:\n${notes}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: data.name,
          email: data.email,
          phone: data.phone,
          city: data.city,
          volume: data.volume,
          inquiryType: "quote",
          message: composedMessage,
          quoteItems: lines.map((l) => ({
            slug: l.slug,
            name: l.name,
            qty: l.qty,
            pack: l.pack,
            family: l.familyName,
          })),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to send");
      setStatus("ok");
      setMessage(
        "Thank you. Your quote request has been received — our commercial team will respond shortly.",
      );
      trackEvent("generate_lead", {
        inquiry_type: "quote",
        method: "quote_form",
        item_count: lines.length,
      });
      if (typeof json.whatsappFollowUp === "string") {
        setWhatsappFollowUp(json.whatsappFollowUp);
      }
      clear();
      form.reset();
    } catch (err) {
      setStatus("err");
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  if (lines.length === 0 && status !== "ok") {
    return (
      <div className="surface-card px-6 py-12 text-center md:px-10">
        <h2 className="font-display text-2xl font-semibold text-[var(--ink)]">
          Your quote list is empty
        </h2>
        <p className="mx-auto mt-3 max-w-md text-[var(--muted)]">
          Browse the catalogue and tap <strong>Add to quote</strong> on any SKU.
          No online checkout — we respond with trade pricing and availability.
        </p>
        <Link href="/products" className="btn btn-accent mt-8">
          Browse products
        </Link>
      </div>
    );
  }

  return (
    <div className="grid gap-10 lg:grid-cols-5 lg:gap-12">
      <div className="lg:col-span-3">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Quote list</p>
            <h2 className="font-display mt-2 text-2xl font-semibold text-[var(--ink)]">
              {count} item{count === 1 ? "" : "s"} selected
            </h2>
          </div>
          {lines.length > 0 ? (
            <button
              type="button"
              onClick={clear}
              className="text-sm font-medium text-[var(--muted)] transition hover:text-[var(--red)]"
            >
              Clear all
            </button>
          ) : null}
        </div>

        <ul className="mt-6 divide-y divide-[var(--line)] border border-[var(--line)] bg-white">
          {lines.map((line) => (
            <li key={line.slug} className="flex gap-4 p-4 sm:items-center sm:p-5">
              <div className="img-well relative h-20 w-20 shrink-0 overflow-hidden sm:h-24 sm:w-24">
                <Image
                  src={line.image}
                  alt={line.name}
                  fill
                  className="object-contain p-2"
                  sizes="96px"
                />
              </div>
              <div className="min-w-0 flex-1">
                <Link
                  href={`/products/${line.slug}`}
                  className="font-display text-base font-semibold text-[var(--ink)] transition hover:text-[var(--blue)]"
                >
                  {line.name}
                </Link>
                <p className="mt-0.5 text-sm text-[var(--muted)]">
                  {line.familyName} · {line.pack}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-sm text-[var(--ink-soft)]">
                    Qty
                    <input
                      type="number"
                      min={1}
                      max={9999}
                      value={line.qty}
                      onChange={(e) => setQty(line.slug, Number(e.target.value))}
                      className="w-20 border border-[var(--line)] px-2 py-1.5 text-sm outline-none focus:border-[var(--blue)]"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => remove(line.slug)}
                    className="text-sm font-medium text-[var(--muted)] transition hover:text-[var(--red)]"
                  >
                    Remove
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="lg:col-span-2">
        <div className="surface-card p-6 md:p-7">
          <h3 className="font-display text-xl font-semibold text-[var(--ink)]">
            Request pricing
          </h3>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Submit your list — we reply with availability and trade guidance. No
            payment is taken on this site.
          </p>

          {status === "ok" ? (
            <div className="mt-6 space-y-3" role="status">
              <p className="text-sm text-[var(--blue)]">{message}</p>
              {whatsappFollowUp ? (
                <a
                  href={whatsappFollowUp}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex text-sm font-semibold text-[#128C7E] underline"
                >
                  Continue on WhatsApp →
                </a>
              ) : null}
              <Link href="/products" className="btn btn-outline mt-4 w-full">
                Continue browsing
              </Link>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mt-6 space-y-4">
              <label className="block text-sm">
                <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
                  Name
                </span>
                <input name="name" required autoComplete="name" className={field} />
              </label>
              <label className="block text-sm">
                <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
                  Email
                </span>
                <input
                  name="email"
                  type="email"
                  required
                  autoComplete="email"
                  className={field}
                />
              </label>
              <label className="block text-sm">
                <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
                  Phone
                </span>
                <input
                  name="phone"
                  type="tel"
                  autoComplete="tel"
                  className={field}
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm">
                  <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
                    City
                  </span>
                  <input name="city" autoComplete="address-level2" className={field} />
                </label>
                <label className="block text-sm">
                  <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
                    Est. monthly volume
                  </span>
                  <input name="volume" placeholder="Optional" className={field} />
                </label>
              </div>
              <label className="block text-sm">
                <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
                  Notes
                </span>
                <textarea
                  name="notes"
                  rows={4}
                  placeholder="Territory, branding, delivery timeline…"
                  className={`${field} min-h-[6rem] resize-y`}
                />
              </label>
              <button
                type="submit"
                disabled={status === "sending" || lines.length === 0}
                className="btn btn-accent sticky bottom-[calc(var(--dock-h)+0.65rem)] z-20 w-full shadow-[0_10px_30px_rgba(185,28,34,0.35)] disabled:opacity-60 md:static md:shadow-[0_8px_20px_rgba(185,28,34,0.22)]"
              >
                {status === "sending"
                  ? "Sending…"
                  : `Submit quote${count ? ` · ${count}` : ""}`}
              </button>
              {message && status === "err" ? (
                <p className="text-sm text-red-700" role="status">
                  {message}
                </p>
              ) : null}
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
