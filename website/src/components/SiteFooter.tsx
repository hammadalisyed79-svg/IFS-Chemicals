import Link from "next/link";
import { contact, products } from "@/lib/content";

export function SiteFooter() {
  return (
    <footer className="border-t border-[var(--line)] bg-[var(--ink)] text-[var(--foam)]">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 py-14 md:grid-cols-3 md:px-8">
        <div>
          <p className="font-display text-2xl font-bold">IFS Chemicals</p>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-[var(--foam)]/70">
            A leading manufacturer of high-quality cleaning solutions and
            packaging materials — built on innovation, quality, and customer
            trust.
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--teal-bright)]">
            Products
          </p>
          <ul className="mt-4 space-y-2 text-sm text-[var(--foam)]/80">
            {products.slice(0, 4).map((p) => (
              <li key={p.slug}>
                <Link href={`/products#${p.slug}`} className="hover:text-[var(--foam)]">
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--teal-bright)]">
            Contact
          </p>
          <ul className="mt-4 space-y-2 text-sm text-[var(--foam)]/80">
            <li>{contact.address}</li>
            <li>
              <a href={contact.phoneHref} className="hover:text-[var(--foam)]">
                {contact.phone}
              </a>
            </li>
            {contact.emails.map((e) => (
              <li key={e}>
                <a href={`mailto:${e}`} className="hover:text-[var(--foam)]">
                  {e}
                </a>
              </li>
            ))}
            <li>
              <a
                href={contact.erpUrl}
                target="_blank"
                rel="noreferrer"
                className="text-[var(--teal-bright)] hover:underline"
              >
                erp.ifschemicals.com
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10 py-5 text-center text-xs text-[var(--foam)]/50">
        © {new Date().getFullYear()} IFS Chemicals. All rights reserved.
      </div>
    </footer>
  );
}
