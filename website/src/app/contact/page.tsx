import type { Metadata } from "next";
import { contact } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";

export const metadata: Metadata = {
  title: "Contact",
  description: "Contact IFS Chemicals in Gujrat — phone, email, and inquiry form.",
};

export default function ContactPage() {
  return (
    <div className="bg-[var(--foam)]">
      <div className="bg-[var(--ink)] px-5 pb-16 pt-16 text-[var(--foam)] md:px-8">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--teal-bright)]">
            Contact us
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">
            We are ready when you are.
          </h1>
        </div>
      </div>
      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-16 md:grid-cols-2 md:px-8 md:py-24">
        <div className="space-y-4 text-[var(--ink-soft)]">
          <p className="text-lg">{contact.address}</p>
          <p>
            <a className="text-xl font-semibold text-[var(--ink)]" href={contact.phoneHref}>
              {contact.phone}
            </a>
          </p>
          {contact.emails.map((e) => (
            <p key={e}>
              <a className="hover:text-[var(--teal)]" href={`mailto:${e}`}>
                {e}
              </a>
            </p>
          ))}
          <p className="pt-4 text-sm">
            Staff & distributors:{" "}
            <a
              href={contact.erpUrl}
              target="_blank"
              rel="noreferrer"
              className="font-semibold text-[var(--teal)]"
            >
              ERP portal
            </a>
          </p>
        </div>
        <ContactForm />
      </div>
    </div>
  );
}
