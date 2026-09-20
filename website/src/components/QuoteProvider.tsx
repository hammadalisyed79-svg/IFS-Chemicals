"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { getCatalogEntry } from "@/lib/content";

export type QuoteLine = {
  slug: string;
  name: string;
  image: string;
  pack: string;
  familySlug: string;
  familyName: string;
  qty: number;
};

type QuoteContextValue = {
  lines: QuoteLine[];
  count: number;
  ready: boolean;
  add: (slug: string, qty?: number) => boolean;
  remove: (slug: string) => void;
  setQty: (slug: string, qty: number) => void;
  clear: () => void;
  has: (slug: string) => boolean;
};

const STORAGE_KEY = "ifs-quote-v1";
const QuoteContext = createContext<QuoteContextValue | null>(null);

function hydrateLine(slug: string, qty: number): QuoteLine | null {
  const entry = getCatalogEntry(slug);
  if (!entry || entry.kind !== "item") return null;
  const q = Math.min(9999, Math.max(1, Math.round(qty) || 1));
  return {
    slug: entry.item.slug,
    name: entry.item.name,
    image: entry.item.image,
    pack: entry.item.pack,
    familySlug: entry.family.slug,
    familyName: entry.family.name,
    qty: q,
  };
}

export function QuoteProvider({ children }: { children: ReactNode }) {
  const [lines, setLines] = useState<QuoteLine[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { slug: string; qty: number }[];
        if (Array.isArray(parsed)) {
          const next = parsed
            .map((row) => hydrateLine(row.slug, row.qty))
            .filter((x): x is QuoteLine => Boolean(x));
          setLines(next);
        }
      }
    } catch {
      /* ignore corrupt storage */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const payload = lines.map((l) => ({ slug: l.slug, qty: l.qty }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }, [lines, ready]);

  const add = useCallback((slug: string, qty = 1) => {
    const line = hydrateLine(slug, qty);
    if (!line) return false;
    setLines((prev) => {
      const existing = prev.find((p) => p.slug === slug);
      if (existing) {
        return prev.map((p) =>
          p.slug === slug
            ? { ...p, qty: Math.min(9999, p.qty + line.qty) }
            : p,
        );
      }
      return [...prev, line];
    });
    return true;
  }, []);

  const remove = useCallback((slug: string) => {
    setLines((prev) => prev.filter((p) => p.slug !== slug));
  }, []);

  const setQty = useCallback((slug: string, qty: number) => {
    const q = Math.min(9999, Math.max(1, Math.round(qty) || 1));
    setLines((prev) =>
      prev.map((p) => (p.slug === slug ? { ...p, qty: q } : p)),
    );
  }, []);

  const clear = useCallback(() => setLines([]), []);

  const has = useCallback(
    (slug: string) => lines.some((l) => l.slug === slug),
    [lines],
  );

  const value = useMemo<QuoteContextValue>(
    () => ({
      lines,
      count: lines.reduce((n, l) => n + l.qty, 0),
      ready,
      add,
      remove,
      setQty,
      clear,
      has,
    }),
    [lines, ready, add, remove, setQty, clear, has],
  );

  return (
    <QuoteContext.Provider value={value}>{children}</QuoteContext.Provider>
  );
}

export function useQuote() {
  const ctx = useContext(QuoteContext);
  if (!ctx) throw new Error("useQuote must be used within QuoteProvider");
  return ctx;
}
