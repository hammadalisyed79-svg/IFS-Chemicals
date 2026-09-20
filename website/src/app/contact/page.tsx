import type { Metadata } from "next";
import { contact } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";

export const metadata: Metadata = {
  title: "Contact",
  description: "Contact IFS Chemicals in Gujrat — phone, email, and inquiry form.",
};

export default function ContactPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="bg-[var(--navy)] px-5 pb-16 pt-16 text-white md:px-8">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--red)]">
            Contact us
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">
            We are ready when you are.
          </h1>
          <p className="mt-4 max-w-xl text-white/75">
            Reach sales for quotes, distributor onboarding, or packaging
            inquiries.
          </p>
        </div>
      </div>
      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-16 md:grid-cols-2 md:px-8 md:py-24">
        <div className="space-y-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--red)]">
              Address
            </p>
            <p className="mt-2 text-lg text-[var(--ink)]">{contact.address}</p>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--red)]">
              Phone / WhatsApp
            </p>
            <p className="mt-2">
              <a className="text-2xl font-bold text-[var(--blue)]" href={contact.phoneHref}>
                {contact.phone}
              </a>
            </p>
            <a
              href={contact.whatsapp}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-sm font-semibold text-[var(--ink)] underline"
            >
              Chat on WhatsApp
            </a>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--red)]">
              Email
            </p>
            <ul className="mt-2 space-y-1">
              {contact.emails.map((e) => (
                <li key={e}>
                  <a className="text-[var(--ink)] hover:text-[var(--blue)]" href={`mailto:${e}`}>
                    {e}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <p className="pt-2 text-sm text-[var(--muted)]">
            Staff & distributors:{" "}
            <a
              href={contact.erpUrl}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-[var(--blue)]"
            >
              ERP portal
            </a>
          </p>
        </div>
        <div className="bg-white p-6 md:p-8">
          <h2 className="font-display text-xl font-bold">Send an inquiry</h2>
          <div className="mt-6">
            <ContactForm />
          </div>
        </div>
      </div>
    </div>
  );
}
