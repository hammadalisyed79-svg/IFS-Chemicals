"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  const [mounted, setMounted] = useState(false);
  const { count, ready } = useQuote();
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    const trigger = triggerRef.current;
    document.body.style.overflow = "hidden";
    document.body.dataset.menuOpen = "true";
    const t = window.setTimeout(() => closeRef.current?.focus(), 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      document.body.style.overflow = prevOverflow;
      delete document.body.dataset.menuOpen;
      window.removeEventListener("keydown", onKey);
      trigger?.focus();
    };
  }, [open]);

  const sheet =
    open && mounted
      ? createPortal(
          <div
            className="mobile-menu-sheet fixed inset-0 z-[80] flex flex-col bg-white text-[var(--ink)] md:hidden"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <div className="flex items-center justify-between border-b border-[var(--line)] px-5 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
              <Image
                src="/images/logo.png"
                alt="IFS Chemicals"
                width={150}
                height={42}
                className="h-8 w-auto"
              />
              <p id={titleId} className="sr-only">
                Site menu
              </p>
              <button
                ref={closeRef}
                type="button"
                aria-label="Close menu"
                onClick={() => setOpen(false)}
                className="flex h-10 w-10 items-center justify-center border border-[var(--line)] text-[var(--ink)] transition hover:border-[var(--navy)] hover:bg-[var(--paper)]"
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
                  <path
                    d="M6 6l12 12M18 6 6 18"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="square"
                  />
                </svg>
              </button>
            </div>

            <nav className="flex flex-1 flex-col overflow-y-auto px-5 pt-1">
              {links.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="flex items-center justify-between border-b border-[var(--line)] py-4 transition hover:text-[var(--blue)]"
                >
                  <span className="font-display text-[1.35rem] font-semibold tracking-tight text-[var(--ink)]">
                    {l.label}
                  </span>
                  {l.href === "/quote" && ready && count > 0 ? (
                    <span className="bg-[var(--red)] px-2 py-0.5 text-[11px] font-semibold text-white">
                      {count}
                    </span>
                  ) : (
                    <span className="text-[var(--muted)]" aria-hidden>
                      →
                    </span>
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
                Innovative Future Solutions
              </p>
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="md:hidden">
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-10 items-center justify-center border border-[var(--line-strong)] bg-white text-[var(--ink)] transition hover:border-[var(--navy)]"
      >
        <span className="sr-only">Menu</span>
        <span className="relative flex h-3 w-4 flex-col justify-between" aria-hidden>
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
      {sheet}
    </div>
  );
}
