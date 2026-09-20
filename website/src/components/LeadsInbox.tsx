"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import type { LeadRow } from "@/lib/leads";

const STORAGE_KEY = "ifs-leads-admin-secret";

function formatWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString("en-PK", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function parseQuoteItems(raw: string | null): { name?: string; qty?: number }[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function LeadsInbox() {
  const [secret, setSecret] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [type, setType] = useState("");
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [configuredHint, setConfiguredHint] = useState(true);

  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      setSecret(saved);
      setUnlocked(true);
    }
  }, []);

  const load = useCallback(
    async (token: string, filterType: string) => {
      setLoading(true);
      setError("");
      try {
        const qs = new URLSearchParams({ limit: "100" });
        if (filterType) qs.set("type", filterType);
        const res = await fetch(`/api/admin/leads?${qs}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const json = await res.json();
        if (res.status === 401) {
          sessionStorage.removeItem(STORAGE_KEY);
          setUnlocked(false);
          setConfiguredHint(true);
          throw new Error("Invalid admin secret.");
        }
        if (res.status === 503) {
          setConfiguredHint(false);
          throw new Error(json.error || "Database not configured.");
        }
        if (!res.ok) throw new Error(json.error || "Failed to load leads");
        setLeads(json.leads || []);
        setUnlocked(true);
        sessionStorage.setItem(STORAGE_KEY, token);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
        setLeads([]);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!unlocked || !secret) return;
    void load(secret, type);
  }, [unlocked, secret, type, load]);

  function onUnlock(e: FormEvent) {
    e.preventDefault();
    const token = secret.trim();
    if (!token) {
      setError("Enter the admin secret.");
      return;
    }
    void load(token, type);
  }

  function signOut() {
    sessionStorage.removeItem(STORAGE_KEY);
    setSecret("");
    setUnlocked(false);
    setLeads([]);
    setError("");
  }

  if (!unlocked) {
    return (
      <div className="mx-auto max-w-md surface-card p-6 md:p-8">
        <h1 className="font-display text-2xl font-semibold text-[var(--ink)]">
          Leads inbox
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Staff-only. Enter the <code className="text-[var(--ink)]">LEADS_ADMIN_SECRET</code>{" "}
          configured in Vercel environment variables.
        </p>
        <form onSubmit={onUnlock} className="mt-6 space-y-4">
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-[var(--ink-soft)]">
              Admin secret
            </span>
            <input
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              autoComplete="current-password"
              className="w-full min-h-11 border border-[var(--line)] px-3.5 py-3 text-sm outline-none focus:border-[var(--blue)] focus:ring-2 focus:ring-[var(--blue)]/15"
            />
          </label>
          <button type="submit" className="btn btn-primary w-full" disabled={loading}>
            {loading ? "Checking…" : "Open inbox"}
          </button>
          {error ? (
            <p className="text-sm text-red-700" role="status">
              {error}
            </p>
          ) : null}
          {!configuredHint ? (
            <p className="text-sm text-[var(--muted)]">
              Also ensure <code>DATABASE_URL</code> is set on the Vercel project.
            </p>
          ) : null}
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Operations</p>
          <h1 className="font-display mt-2 text-3xl font-semibold text-[var(--ink)]">
            Website leads
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Contact and quote requests stored in Neon. Newest first.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-[var(--ink-soft)]">
            Type
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--blue)]"
            >
              <option value="">All</option>
              <option value="quote">Quote</option>
              <option value="b2b">B2B</option>
              <option value="distributor">Distributor</option>
              <option value="general">General</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void load(secret, type)}
            className="btn btn-outline"
            disabled={loading}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" onClick={signOut} className="btn btn-outline">
            Sign out
          </button>
        </div>
      </div>

      {error ? (
        <p className="text-sm text-red-700" role="status">
          {error}
        </p>
      ) : null}

      {leads.length === 0 && !loading ? (
        <div className="surface-card px-6 py-12 text-center text-[var(--muted)]">
          No inquiries match this filter yet.
        </div>
      ) : (
        <ul className="space-y-4">
          {leads.map((lead) => {
            const items = parseQuoteItems(lead.quote_items);
            return (
              <li key={lead.id} className="surface-card p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-display text-lg font-semibold text-[var(--ink)]">
                      {lead.name}
                    </p>
                    <p className="mt-1 text-sm text-[var(--muted)]">
                      <a
                        className="text-[var(--blue)] hover:underline"
                        href={`mailto:${lead.email}`}
                      >
                        {lead.email}
                      </a>
                      {lead.phone ? (
                        <>
                          {" · "}
                          <a
                            className="hover:text-[var(--blue)]"
                            href={`tel:${lead.phone}`}
                          >
                            {lead.phone}
                          </a>
                        </>
                      ) : null}
                      {lead.city ? ` · ${lead.city}` : null}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <span className="inline-block bg-[var(--paper-2)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--ink-soft)]">
                      {lead.inquiry_type}
                    </span>
                    <p className="mt-2 text-[var(--muted)]">
                      {formatWhen(lead.created_at)}
                    </p>
                  </div>
                </div>
                {(lead.volume || lead.brand) && (
                  <p className="mt-3 text-sm text-[var(--muted)]">
                    {lead.volume ? `Volume: ${lead.volume}` : null}
                    {lead.volume && lead.brand ? " · " : null}
                    {lead.brand ? `Brand: ${lead.brand}` : null}
                  </p>
                )}
                <pre className="mt-4 whitespace-pre-wrap border-t border-[var(--line)] pt-4 font-sans text-sm leading-relaxed text-[var(--ink-soft)]">
                  {lead.message}
                </pre>
                {items.length > 0 ? (
                  <ul className="mt-3 space-y-1 text-sm text-[var(--muted)]">
                    {items.map((item, i) => (
                      <li key={`${lead.id}-${i}`}>
                        • {item.name || "Item"}
                        {item.qty ? ` × ${item.qty}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
