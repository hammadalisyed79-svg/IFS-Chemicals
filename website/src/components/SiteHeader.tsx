"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { contact } from "@/lib/content";
import { MobileNav } from "@/components/MobileNav";
import { QuoteNavLink } from "@/components/QuoteNavLink";

const links = [
  { href: "/", label: "Home" },
  { href: "/products", label: "Products" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 border-b border-[var(--line)] bg-white/92 text-[var(--ink)] backdrop-blur-md transition-[box-shadow] duration-300 ${
        scrolled ? "shadow-[0_8px_24px_rgba(10,22,40,0.06)]" : ""
      }`}
    >
      <div className="hidden border-b border-white/10 bg-[var(--navy)] text-[12px] text-white/85 md:block">
        <div className="container-site flex items-center justify-between gap-4 py-2">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
            <a href={contact.phoneHref} className="transition hover:text-white">
              {contact.phone}
            </a>
            <a
              href={`mailto:${contact.emails[0]}`}
              className="transition hover:text-white"
            >
              {contact.emails[0]}
            </a>
          </div>
          <div className="flex items-center gap-5">
            <a
              href={contact.social.linkedin}
              target="_blank"
              rel="noreferrer"
              className="transition hover:text-white"
            >
              LinkedIn
            </a>
            <a
              href={contact.erpUrl}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-white transition hover:opacity-90"
            >
              Partner portal
            </a>
          </div>
        </div>
      </div>
      <div
        className={`container-site flex items-center justify-between gap-3 transition-[padding] duration-300 ${
          scrolled ? "py-2.5 md:py-3" : "py-3 md:py-4"
        }`}
      >
        <Link href="/" className="flex shrink-0 items-center gap-3">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={200}
            height={56}
            className={`w-auto transition-[height] duration-300 ${
              scrolled ? "h-8 md:h-10" : "h-9 md:h-11"
            }`}
            priority
          />
        </Link>
        <nav className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-[13px] font-medium tracking-[0.04em] text-[var(--ink-soft)] transition hover:text-[var(--navy)]"
            >
              {l.label}
            </Link>
          ))}
          <QuoteNavLink />
          <Link href="/quote" className="btn btn-accent">
            Request a quote
          </Link>
        </nav>
        <div className="flex items-center gap-2.5 md:hidden">
          <a
            href={contact.phoneHref}
            className="flex h-11 w-11 items-center justify-center border border-[var(--line-strong)] text-[var(--ink)] transition active:scale-95"
            aria-label="Call IFS Chemicals"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
              <path
                d="M7.5 4.5h3l1.2 3.2-1.8 1.8a12.5 12.5 0 0 0 5.4 5.4l1.8-1.8 3.2 1.2v3A2 2 0 0 1 18.3 19 14.8 14.8 0 0 1 5 5.7a2 2 0 0 1 2.5-1.2Z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
          </a>
          <QuoteNavLink className="flex h-11 items-center px-2 text-[12px] font-semibold tracking-[0.04em] text-[var(--navy)]" />
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
