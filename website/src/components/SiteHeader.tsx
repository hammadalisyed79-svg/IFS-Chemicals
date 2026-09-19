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
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[var(--ink)]/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-4 md:px-8">
        <Link href="/" className="group flex flex-col leading-none">
          <span className="font-display text-xl font-extrabold tracking-tight text-[var(--foam)] md:text-2xl">
            IFS Chemicals
          </span>
          <span className="mt-1 text-[10px] font-medium uppercase tracking-[0.22em] text-[var(--teal-bright)]/90">
            Innovative Future Solutions
          </span>
        </Link>
        <nav className="hidden items-center gap-7 md:flex">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-sm font-medium text-[var(--foam)]/80 transition hover:text-[var(--foam)]"
            >
              {l.label}
            </Link>
          ))}
          <a
            href={contact.erpUrl}
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-[var(--teal-bright)]/40 bg-[var(--teal-bright)]/10 px-4 py-2 text-sm font-semibold text-[var(--teal-bright)] transition hover:bg-[var(--teal-bright)] hover:text-[var(--ink)]"
          >
            ERP Login
          </a>
        </nav>
        <div className="flex items-center gap-4 md:hidden">
          <Link href="/products" className="text-sm font-medium text-[var(--foam)]/90">
            Products
          </Link>
          <a href={contact.phoneHref} className="text-sm font-semibold text-[var(--teal-bright)]">
            Call
          </a>
        </div>
      </div>
    </header>
  );
}
