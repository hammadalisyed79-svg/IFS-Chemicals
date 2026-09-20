"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuote } from "@/components/QuoteProvider";

export function AddToQuoteButton({
  slug,
  className = "btn btn-outline",
}: {
  slug: string;
  className?: string;
}) {
  const { add, has } = useQuote();
  const [justAdded, setJustAdded] = useState(false);
  const inQuote = has(slug);

  function onClick() {
    const ok = add(slug, 1);
    if (!ok) return;
    setJustAdded(true);
    window.setTimeout(() => setJustAdded(false), 2200);
  }

  if (justAdded || inQuote) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onClick} className={className}>
          {justAdded ? "Added to quote" : "Add another unit"}
        </button>
        <Link
          href="/quote"
          className="text-sm font-semibold text-[var(--blue)] transition hover:underline"
        >
          View quote →
        </Link>
      </div>
    );
  }

  return (
    <button type="button" onClick={onClick} className={className}>
      Add to quote
    </button>
  );
}
