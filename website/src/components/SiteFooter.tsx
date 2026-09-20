import Image from "next/image";
import Link from "next/link";
import { contact, products } from "@/lib/content";

const social = [
  { label: "Facebook", href: contact.social.facebook },
  { label: "Instagram", href: contact.social.instagram },
  { label: "LinkedIn", href: contact.social.linkedin },
  { label: "WhatsApp", href: contact.whatsapp },
];

export function SiteFooter() {
  return (
    <footer className="bg-[#071833] text-white">
      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-14 md:grid-cols-12 md:px-8 md:py-16">
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
          <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-sm font-semibold">
            {social.map((s) => (
              <a
                key={s.label}
                href={s.href}
                target="_blank"
                rel="noreferrer"
                className="text-white/80 underline-offset-4 hover:text-white hover:underline"
              >
                {s.label}
              </a>
            ))}
          </div>
        </div>
        <div className="md:col-span-3">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#ff6b6b]">
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
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#ff6b6b]">
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
