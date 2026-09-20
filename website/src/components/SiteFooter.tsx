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
    <footer className="bg-[var(--navy)] text-white">
      <div className="container-site grid gap-12 py-16 md:grid-cols-12 md:py-20">
        <div className="md:col-span-5">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={220}
            height={62}
            className="h-11 w-auto"
          />
          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-white/65">
            Manufacturing partner for cleaning solutions and packaging systems —
            delivering consistent quality for households, retailers, and industrial
            buyers across Pakistan.
          </p>
          <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-[13px] font-medium tracking-wide">
            {social.map((s) => (
              <a
                key={s.label}
                href={s.href}
                target="_blank"
                rel="noreferrer"
                className="text-white/70 transition hover:text-white"
              >
                {s.label}
              </a>
            ))}
          </div>
        </div>
        <div className="md:col-span-3">
          <p className="eyebrow !text-white/45">Products</p>
          <ul className="mt-5 space-y-2.5 text-[14px] text-white/70">
            {products.slice(0, 5).map((p) => (
              <li key={p.slug}>
                <Link href={`/products/${p.slug}`} className="transition hover:text-white">
                  {p.name}
                </Link>
              </li>
            ))}
            <li>
              <Link href="/quote" className="transition hover:text-white">
                Request a quote
              </Link>
            </li>
          </ul>
        </div>
        <div className="md:col-span-4">
          <p className="eyebrow !text-white/45">Headquarters</p>
          <ul className="mt-5 space-y-2.5 text-[14px] text-white/70">
            <li>{contact.address}</li>
            <li>
              <a href={contact.phoneHref} className="transition hover:text-white">
                {contact.phone}
              </a>
            </li>
            {contact.emails.map((e) => (
              <li key={e}>
                <a href={`mailto:${e}`} className="transition hover:text-white">
                  {e}
                </a>
              </li>
            ))}
            <li className="pt-3">
              <a
                href={contact.erpUrl}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-white transition hover:opacity-90"
              >
                Partner portal →
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="container-site flex flex-col gap-2 py-5 text-[12px] text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} IFS Chemicals. All rights reserved.</p>
          <p>Innovative Future Solutions · Gujrat, Pakistan</p>
        </div>
      </div>
    </footer>
  );
}
