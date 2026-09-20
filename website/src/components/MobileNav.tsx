"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { contact } from "@/lib/content";

const links = [
  { href: "/", label: "Home" },
  { href: "/products", label: "Products" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((v) => !v)}
        className="flex h-11 w-11 items-center justify-center rounded border border-white/25 text-white"
      >
        <span className="sr-only">Menu</span>
        <span className="relative flex h-4 w-5 flex-col justify-between">
          <span
            className={`block h-0.5 w-full bg-white transition ${open ? "translate-y-[7px] rotate-45" : ""}`}
          />
          <span className={`block h-0.5 w-full bg-white transition ${open ? "opacity-0" : ""}`} />
          <span
            className={`block h-0.5 w-full bg-white transition ${open ? "-translate-y-[7px] -rotate-45" : ""}`}
          />
        </span>
      </button>

      {open ? (
        <div className="fixed inset-0 z-[60] flex flex-col bg-[#071833] px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))]">
          <div className="flex items-center justify-between py-3">
            <Image
              src="/images/logo.png"
              alt="IFS Chemicals"
              width={160}
              height={44}
              className="h-10 w-auto"
            />
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="flex h-11 w-11 items-center justify-center border border-white/25 text-lg text-white"
            >
              ✕
            </button>
          </div>
          <nav className="mt-4 flex flex-col">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="border-b border-white/10 py-4 text-lg font-semibold uppercase tracking-[0.12em] text-white"
              >
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto flex flex-col gap-3 pt-10">
            <Link
              href="/contact"
              onClick={() => setOpen(false)}
              className="bg-[#c41e26] px-5 py-3.5 text-center text-sm font-bold uppercase tracking-[0.1em] text-white"
            >
              Get a quote
            </Link>
            <a
              href={contact.whatsapp}
              target="_blank"
              rel="noreferrer"
              className="border border-white/35 px-5 py-3.5 text-center text-sm font-semibold uppercase tracking-[0.1em] text-white"
            >
              WhatsApp
            </a>
            <a
              href={contact.phoneHref}
              className="py-2 text-center text-sm font-semibold text-white/80"
            >
              {contact.phone}
            </a>
          </div>
        </div>
      ) : null}
    </div>
  );
}
