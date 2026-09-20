"use client";

import { FormEvent, useMemo, useState } from "react";
import { trackEvent } from "@/lib/analytics";

type InquiryType = "general" | "distributor" | "b2b";

export function ContactForm() {
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const [inquiryType, setInquiryType] = useState<InquiryType>("general");
  const [whatsappFollowUp, setWhatsappFollowUp] = useState<string | null>(null);

  const needsB2b = inquiryType === "distributor" || inquiryType === "b2b";

  const typeLabel = useMemo(() => {
    if (inquiryType === "distributor") return "Distributor inquiry";
    if (inquiryType === "b2b") return "B2B / bulk inquiry";
    return "General inquiry";
  }, [inquiryType]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("sending");
    setMessage("");
    setWhatsappFollowUp(null);
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());

    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to send");
      setStatus("ok");
      setMessage("Thank you. We have received your inquiry and will respond shortly.");
      trackEvent("generate_lead", {
        inquiry_type: String(data.inquiryType || inquiryType),
        method: "contact_form",
      });
      if (typeof json.whatsappFollowUp === "string") {
        setWhatsappFollowUp(json.whatsappFollowUp);
      }
      form.reset();
      setInquiryType("general");
    } catch (err) {
      setStatus("err");
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  const field =
    "w-full min-h-12 border border-[var(--line)] bg-white px-3.5 py-3.5 text-base outline-none transition focus:border-[var(--blue)] focus:ring-2 focus:ring-[var(--blue)]/15 sm:min-h-11 sm:py-3 sm:text-sm";

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-[var(--ink-soft)]">
          Inquiry type
        </legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {(
            [
              ["general", "General"],
              ["distributor", "Distributor"],
              ["b2b", "B2B / bulk"],
            ] as const
          ).map(([value, label]) => (
            <label
              key={value}
              className={`flex min-h-11 cursor-pointer items-center justify-center border px-3 py-2 text-sm font-medium transition ${
                inquiryType === value
                  ? "border-[var(--navy)] bg-[var(--navy)] text-white"
                  : "border-[var(--line)] bg-white text-[var(--ink)] hover:border-[var(--ink-soft)]"
              }`}
            >
              <input
                type="radio"
                name="inquiryType"
                value={value}
                checked={inquiryType === value}
                onChange={() => setInquiryType(value)}
                className="sr-only"
              />
              {label}
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-[var(--muted)]">{typeLabel}</p>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Name</span>
          <input name="name" required autoComplete="name" className={field} />
        </label>
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Phone</span>
          <input
            name="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            className={field}
          />
        </label>
      </div>

      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Email</span>
        <input
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          className={field}
        />
      </label>

      {needsB2b ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block text-sm sm:col-span-1">
            <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
              City <span className="text-[var(--red)]">*</span>
            </span>
            <input
              name="city"
              required
              autoComplete="address-level2"
              placeholder="e.g. Gujrat"
              className={field}
            />
          </label>
          <label className="block text-sm sm:col-span-1">
            <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
              Monthly volume
            </span>
            <input
              name="volume"
              placeholder="e.g. 200 cartons"
              className={field}
            />
          </label>
          <label className="block text-sm sm:col-span-1">
            <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
              Brand / interest
            </span>
            <input
              name="brand"
              placeholder="Happy, Train, private label…"
              className={field}
            />
          </label>
        </div>
      ) : null}

      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Message</span>
        <textarea
          name="message"
          required
          rows={5}
          placeholder={
            needsB2b
              ? "Describe territory, products required, and timeline…"
              : "How can we help?"
          }
          className={`${field} min-h-[8rem] resize-y`}
        />
      </label>

      <button
        type="submit"
        disabled={status === "sending"}
        className="btn btn-primary min-h-12 w-full disabled:opacity-60 sm:w-auto"
      >
        {status === "sending" ? "Sending…" : "Submit inquiry"}
      </button>

      {message ? (
        <div className="space-y-2" role="status">
          <p
            className={`text-sm ${status === "ok" ? "text-[var(--blue)]" : "text-red-700"}`}
          >
            {message}
          </p>
          {status === "ok" && whatsappFollowUp ? (
            <a
              href={whatsappFollowUp}
              target="_blank"
              rel="noreferrer"
              className="inline-flex text-sm font-semibold text-[#128C7E] underline"
            >
              Also message us on WhatsApp →
            </a>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
