import Image from "next/image";
import Link from "next/link";
import { contact } from "@/lib/content";

const links = [
  { href: "/", label: "Home" },
  { href: "/products", label: "Products" },
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-[var(--navy)]/95 text-white backdrop-blur-md">
      <div className="hidden border-b border-white/10 bg-[var(--red)] text-[13px] sm:block">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-1.5 md:px-8">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            <a href={contact.phoneHref} className="hover:underline">
              {contact.phone}
            </a>
            <a href={`mailto:${contact.emails[0]}`} className="hover:underline">
              {contact.emails[0]}
            </a>
          </div>
          <a
            href={contact.erpUrl}
            target="_blank"
            rel="noreferrer"
            className="font-semibold tracking-wide"
          >
            ERP Login
          </a>
        </div>
      </div>
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-3 md:px-8">
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={200}
            height={56}
            className="h-11 w-auto md:h-12"
            priority
          />
        </Link>
        <nav className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-sm font-semibold uppercase tracking-[0.14em] text-white/85 transition hover:text-white"
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/contact"
            className="bg-[var(--red)] px-4 py-2.5 text-sm font-semibold uppercase tracking-[0.08em] text-white transition hover:bg-[var(--red-deep)]"
          >
            Get a quote
          </Link>
        </nav>
        <div className="flex items-center gap-4 md:hidden">
          <Link href="/products" className="text-sm font-semibold">
            Products
          </Link>
          <a href={contact.phoneHref} className="text-sm font-bold text-[var(--red)]">
            Call
          </a>
        </div>
      </div>
    </header>
  );
}
