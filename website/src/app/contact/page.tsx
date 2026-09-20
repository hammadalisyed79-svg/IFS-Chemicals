import type { Metadata } from "next";
import { contact } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";
import { mapsSearchUrl, pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: "Contact — Quotes, Distributors & B2B",
  description:
    "Contact IFS Chemicals for product quotes, distributor onboarding, and B2B supply. Call +92 321 6001040, WhatsApp, or send an enquiry online.",
  path: "/contact",
});

export default function ContactPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="bg-[var(--navy)] text-white">
        <div className="container-site pb-16 pt-14 md:pb-20 md:pt-20">
          <p className="eyebrow !text-white/70">Contact</p>
          <h1 className="font-display mt-4 max-w-3xl text-3xl font-semibold sm:text-4xl md:text-6xl">
            Speak with our commercial team.
          </h1>
          <p className="mt-5 max-w-xl text-[1.05rem] leading-relaxed text-white/70">
            Request a quote, discuss distributor onboarding, or enquire about
            packaging and private-label programmes.
          </p>
        </div>
      </div>
      <div className="container-site grid gap-12 py-16 md:grid-cols-2 md:gap-16 md:py-24">
        <div className="space-y-8">
          <div>
            <p className="eyebrow">Address</p>
            <p className="mt-3 text-lg font-medium text-[var(--ink)]">{contact.address}</p>
            <a
              href={mapsSearchUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-sm font-semibold text-[var(--blue)] transition hover:underline"
            >
              Open in Google Maps
            </a>
          </div>
          <div>
            <p className="eyebrow">Phone / WhatsApp</p>
            <p className="mt-3">
              <a className="text-2xl font-semibold text-[var(--blue)]" href={contact.phoneHref}>
                {contact.phone}
              </a>
            </p>
            <a
              href={contact.whatsapp}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-sm font-semibold text-[var(--ink)] transition hover:text-[var(--blue)]"
            >
              Continue on WhatsApp →
            </a>
          </div>
          <div>
            <p className="eyebrow">Email</p>
            <ul className="mt-3 space-y-1.5">
              {contact.emails.map((e) => (
                <li key={e}>
                  <a
                    className="text-[var(--ink)] transition hover:text-[var(--blue)]"
                    href={`mailto:${e}`}
                  >
                    {e}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <p className="text-sm text-[var(--muted)]">
            Staff &amp; distributors:{" "}
            <a
              href={contact.erpUrl}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-[var(--blue)]"
            >
              Partner portal
            </a>
          </p>
        </div>
        <div className="surface-card p-6 md:p-8">
          <h2 className="font-display text-xl font-semibold text-[var(--ink)]">
            Inquiry form
          </h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            General, distributor, and B2B requests welcome.
          </p>
          <div className="mt-6">
            <ContactForm />
          </div>
        </div>
      </div>
    </div>
  );
}
