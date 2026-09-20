"use client";

import Link from "next/link";
import { useQuote } from "@/components/QuoteProvider";

export function QuoteNavLink({
  className = "text-[13px] font-medium tracking-[0.04em] text-[var(--ink-soft)] transition hover:text-[var(--navy)]",
}: {
  className?: string;
}) {
  const { count, ready } = useQuote();
  return (
    <Link href="/quote" className={`relative inline-flex items-center gap-1.5 ${className}`}>
      Quote
      {ready && count > 0 ? (
        <span className="inline-flex min-w-[1.25rem] items-center justify-center bg-[var(--red)] px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white">
          {count > 99 ? "99+" : count}
        </span>
      ) : null}
    </Link>
  );
}
