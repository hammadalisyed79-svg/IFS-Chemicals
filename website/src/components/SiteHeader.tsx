import Image from "next/image";
import Link from "next/link";
import { contact } from "@/lib/content";
import { MobileNav } from "@/components/MobileNav";

const links = [
  { href: "/", label: "Home" },
  { href: "/products", label: "Products" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-[var(--line)] bg-white/95 text-[var(--ink)] backdrop-blur-md">
      <div className="hidden border-b border-white/10 bg-[var(--navy)] text-[12px] text-white/85 sm:block">
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
      <div className="container-site flex items-center justify-between gap-4 py-3.5 md:py-4">
        <Link href="/" className="flex shrink-0 items-center gap-3">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={200}
            height={56}
            className="h-9 w-auto md:h-11"
            priority
          />
        </Link>
        <nav className="hidden items-center gap-9 md:flex">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-[13px] font-medium tracking-[0.04em] text-[var(--ink-soft)] transition hover:text-[var(--navy)]"
            >
              {l.label}
            </Link>
          ))}
          <Link href="/contact" className="btn btn-accent">
            Request a quote
          </Link>
        </nav>
        <div className="flex items-center gap-3 md:hidden">
          <a
            href={contact.whatsapp}
            target="_blank"
            rel="noreferrer"
            className="text-[13px] font-semibold text-[var(--blue)]"
          >
            WhatsApp
          </a>
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
