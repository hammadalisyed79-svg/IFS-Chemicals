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
        className="flex h-11 w-11 items-center justify-center border border-[var(--line-strong)] text-[var(--ink)]"
      >
        <span className="sr-only">Menu</span>
        <span className="relative flex h-3.5 w-5 flex-col justify-between">
          <span
            className={`block h-px w-full bg-current transition ${open ? "translate-y-[7px] rotate-45" : ""}`}
          />
          <span className={`block h-px w-full bg-current transition ${open ? "opacity-0" : ""}`} />
          <span
            className={`block h-px w-full bg-current transition ${open ? "-translate-y-[7px] -rotate-45" : ""}`}
          />
        </span>
      </button>

      {open ? (
        <div className="fixed inset-0 z-[60] flex flex-col bg-white px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))]">
          <div className="flex items-center justify-between border-b border-[var(--line)] py-4">
            <Image
              src="/images/logo.png"
              alt="IFS Chemicals"
              width={160}
              height={44}
              className="h-9 w-auto"
            />
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="flex h-11 w-11 items-center justify-center border border-[var(--line)] text-lg text-[var(--ink)]"
            >
              ✕
            </button>
          </div>
          <nav className="mt-2 flex flex-col">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="border-b border-[var(--line)] py-4 text-lg font-medium tracking-wide text-[var(--ink)]"
              >
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto flex flex-col gap-3 pt-10">
            <Link
              href="/contact"
              onClick={() => setOpen(false)}
              className="btn btn-accent w-full"
            >
              Request a quote
            </Link>
            <a
              href={contact.whatsapp}
              target="_blank"
              rel="noreferrer"
              className="btn btn-outline w-full"
            >
              WhatsApp
            </a>
          </div>
        </div>
      ) : null}
    </div>
  );
}
