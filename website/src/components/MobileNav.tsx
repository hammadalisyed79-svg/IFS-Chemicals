"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { contact } from "@/lib/content";
import { useQuote } from "@/components/QuoteProvider";

const links = [
  { href: "/", label: "Home", hint: "Overview" },
  { href: "/products", label: "Products", hint: "Full catalogue" },
  { href: "/quote", label: "Quote", hint: "Build a list" },
  { href: "/about", label: "About", hint: "Company" },
  { href: "/contact", label: "Contact", hint: "Talk to sales" },
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
        className="flex h-11 w-11 items-center justify-center border border-[var(--line-strong)] bg-white text-[var(--ink)] transition active:scale-95"
      >
        <span className="sr-only">Menu</span>
        <span className="relative flex h-3.5 w-5 flex-col justify-between">
          <span
            className={`block h-px w-full bg-current transition duration-300 ${open ? "translate-y-[7px] rotate-45" : ""}`}
          />
          <span
            className={`block h-px w-full bg-current transition duration-300 ${open ? "opacity-0" : ""}`}
          />
          <span
            className={`block h-px w-full bg-current transition duration-300 ${open ? "-translate-y-[7px] -rotate-45" : ""}`}
          />
        </span>
      </button>

      {open ? (
        <div
          className="mobile-menu-sheet fixed inset-0 z-[70] flex flex-col text-white"
          role="dialog"
          aria-modal="true"
          aria-label="Site menu"
        >
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            <div className="mobile-menu-glow" />
          </div>

          <div className="relative flex items-center justify-between px-5 pb-4 pt-[max(1rem,env(safe-area-inset-top))]">
            <Image
              src="/images/logo.png"
              alt="IFS Chemicals"
              width={160}
              height={44}
              className="h-9 w-auto brightness-0 invert"
            />
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="flex h-11 w-11 items-center justify-center border border-white/25 text-lg text-white transition active:scale-95"
            >
              ✕
            </button>
          </div>

          <nav className="relative mt-4 flex flex-1 flex-col px-5">
            {links.map((l, i) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="mobile-menu-link group border-b border-white/10 py-5"
                style={{ animationDelay: `${80 + i * 55}ms` }}
              >
                <span className="font-display text-[1.75rem] font-semibold tracking-tight text-white transition group-active:translate-x-1">
                  {l.label}
                  {l.href === "/quote" && ready && count > 0 ? (
                    <span className="ml-3 align-middle text-[12px] font-semibold tracking-[0.12em] text-white/55">
                      {count}
                    </span>
                  ) : null}
                </span>
                <span className="mt-1 block text-[12px] tracking-[0.14em] text-white/40 uppercase">
                  {l.hint}
                </span>
              </Link>
            ))}
          </nav>

          <div className="relative mt-auto space-y-3 px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-8">
            <Link
              href="/quote"
              onClick={() => setOpen(false)}
              className="btn btn-accent w-full min-h-12"
            >
              Request a quote
            </Link>
            <div className="grid grid-cols-2 gap-3">
              <a
                href={contact.phoneHref}
                className="btn btn-ghost w-full border-white/30"
              >
                Call
              </a>
              <a
                href={contact.whatsapp}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost w-full border-white/30"
              >
                WhatsApp
              </a>
            </div>
            <p className="pt-2 text-center text-[11px] tracking-[0.16em] text-white/35 uppercase">
              Gujrat · Pakistan
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
