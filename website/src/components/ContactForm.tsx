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

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Name</span>
          <input
            name="name"
            required
            className="w-full border border-[var(--line)] bg-white px-3 py-2.5 outline-none ring-[var(--teal)]/30 focus:ring-2"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Phone</span>
          <input
            name="phone"
            className="w-full border border-[var(--line)] bg-white px-3 py-2.5 outline-none ring-[var(--teal)]/30 focus:ring-2"
          />
        </label>
      </div>
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Email</span>
        <input
          name="email"
          type="email"
          required
          className="w-full border border-[var(--line)] bg-white px-3 py-2.5 outline-none ring-[var(--teal)]/30 focus:ring-2"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">Message</span>
        <textarea
          name="message"
          required
          rows={5}
          className="w-full resize-y border border-[var(--line)] bg-white px-3 py-2.5 outline-none ring-[var(--teal)]/30 focus:ring-2"
        />
      </label>
      <button
        type="submit"
        disabled={status === "sending"}
        className="bg-[var(--ink)] px-6 py-3 text-sm font-semibold text-[var(--foam)] transition hover:bg-[var(--teal)] disabled:opacity-60"
      >
        {status === "sending" ? "Sending…" : "Send inquiry"}
      </button>
      {message ? (
        <p
          className={`text-sm ${status === "ok" ? "text-[var(--teal)]" : "text-red-700"}`}
          role="status"
        >
          {message}
        </p>
      ) : null}
    </form>
  );
}
