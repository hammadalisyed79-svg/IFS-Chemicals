import Image from "next/image";
import Link from "next/link";
import { contact, products } from "@/lib/content";

export function SiteFooter() {
  return (
    <footer className="bg-[var(--navy)] text-white">
      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-16 md:grid-cols-12 md:px-8">
        <div className="md:col-span-5">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={220}
            height={62}
            className="h-12 w-auto"
          />
          <p className="mt-5 max-w-md text-sm leading-relaxed text-white/70">
            A leading manufacturer of high-quality cleaning solutions and
            packaging materials — built on innovation, quality, and customer
            trust. Made in Pakistan.
          </p>
        </div>
        <div className="md:col-span-3">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--red)]">
            Products
          </p>
          <ul className="mt-4 space-y-2 text-sm text-white/75">
            {products.slice(0, 5).map((p) => (
              <li key={p.slug}>
                <Link href={`/products#${p.slug}`} className="hover:text-white">
                  {p.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div className="md:col-span-4">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--red)]">
            Contact
          </p>
          <ul className="mt-4 space-y-2 text-sm text-white/75">
            <li>{contact.address}</li>
            <li>
              <a href={contact.phoneHref} className="hover:text-white">
                {contact.phone}
              </a>
            </li>
            {contact.emails.map((e) => (
              <li key={e}>
                <a href={`mailto:${e}`} className="hover:text-white">
                  {e}
                </a>
              </li>
            ))}
            <li className="pt-2">
              <a
                href={contact.erpUrl}
                target="_blank"
                rel="noreferrer"
                className="font-semibold text-white hover:underline"
              >
                erp.ifschemicals.com
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10 py-5 text-center text-xs text-white/45">
        © {new Date().getFullYear()} IFS Chemicals. All rights reserved.
      </div>
    </footer>
  );
}
