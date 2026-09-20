"use client";

import { FormEvent, useState } from "react";

export function ContactForm() {
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setStatus("sending");
    setMessage("");
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
      setMessage("Thanks — we received your message and will reply soon.");
      form.reset();
    } catch (err) {
      setStatus("err");
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  const field =
    "w-full min-h-11 border border-[var(--line)] bg-white px-3 py-3 text-base outline-none ring-[#0b5ea8]/25 focus:ring-2 sm:text-sm";

  return (
    <form onSubmit={onSubmit} className="space-y-4">
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
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Message</span>
        <textarea
          name="message"
          required
          rows={5}
          className={`${field} min-h-[8rem] resize-y`}
        />
      </label>
      <button
        type="submit"
        disabled={status === "sending"}
        className="min-h-12 w-full bg-[#071833] px-6 py-3 text-sm font-bold uppercase tracking-[0.08em] text-white transition hover:bg-[#0b5ea8] disabled:opacity-60 sm:w-auto"
      >
        {status === "sending" ? "Sending…" : "Send inquiry"}
      </button>
      {message ? (
        <p
          className={`text-sm ${status === "ok" ? "text-[#0b5ea8]" : "text-red-700"}`}
          role="status"
        >
          {message}
        </p>
      ) : null}
    </form>
  );
}
