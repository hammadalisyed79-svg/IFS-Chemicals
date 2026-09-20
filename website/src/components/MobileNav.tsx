"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { contact } from "@/lib/content";
import { useQuote } from "@/components/QuoteProvider";

const links = [
  { href: "/", label: "Home" },
  { href: "/products", label: "Products" },
  { href: "/quote", label: "Quote" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const { count, ready } = useQuote();

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-10 items-center justify-center border border-[var(--line-strong)] bg-white text-[var(--ink)]"
      >
        <span className="sr-only">Menu</span>
        <span className="relative flex h-3 w-4 flex-col justify-between">
          <span
            className={`block h-px w-full bg-current transition duration-200 ${open ? "translate-y-[5.5px] rotate-45" : ""}`}
          />
          <span
            className={`block h-px w-full bg-current transition duration-200 ${open ? "opacity-0" : ""}`}
          />
          <span
            className={`block h-px w-full bg-current transition duration-200 ${open ? "-translate-y-[5.5px] -rotate-45" : ""}`}
          />
        </span>
      </button>

      {open ? (
        <div
          className="mobile-menu-sheet fixed inset-0 z-[70] flex flex-col bg-white text-[var(--ink)]"
          role="dialog"
          aria-modal="true"
          aria-label="Site menu"
        >
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
            <Image
              src="/images/logo.png"
              alt="IFS Chemicals"
              width={150}
              height={42}
              className="h-8 w-auto"
            />
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="flex h-10 w-10 items-center justify-center border border-[var(--line)] text-[var(--ink)]"
            >
              ✕
            </button>
          </div>

          <nav className="flex flex-1 flex-col px-5 pt-2">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="flex items-center justify-between border-b border-[var(--line)] py-4"
              >
                <span className="font-display text-[1.35rem] font-semibold tracking-tight text-[var(--ink)]">
                  {l.label}
                </span>
                {l.href === "/quote" && ready && count > 0 ? (
                  <span className="bg-[var(--red)] px-2 py-0.5 text-[11px] font-semibold text-white">
                    {count}
                  </span>
                ) : (
                  <span className="text-[var(--muted)]">→</span>
                )}
              </Link>
            ))}
          </nav>

          <div className="space-y-2.5 border-t border-[var(--line)] px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-5">
            <Link
              href="/quote"
              onClick={() => setOpen(false)}
              className="btn btn-accent w-full"
            >
              Request a quote
            </Link>
            <div className="grid grid-cols-2 gap-2.5">
              <a href={contact.phoneHref} className="btn btn-outline w-full">
                Call
              </a>
              <a
                href={contact.whatsapp}
                target="_blank"
                rel="noreferrer"
                className="btn btn-outline w-full"
              >
                WhatsApp
              </a>
            </div>
            <p className="pt-1 text-center text-[11px] tracking-[0.12em] text-[var(--muted)] uppercase">
              Gujrat · Pakistan
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
