import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { contact, highlights } from "@/lib/content";

export const metadata: Metadata = {
  title: "About",
  description:
    "IFS Chemicals manufactures cleaning solutions and packaging materials in Gujrat, Pakistan.",
};

export default function AboutPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="relative overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src="/images/factory.jpg"
          alt="IFS Chemicals facility"
          fill
          className="object-cover opacity-40"
          sizes="100vw"
          priority
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/85 to-[var(--navy)]/40" />
        <div className="relative mx-auto max-w-6xl px-5 pb-16 pt-16 md:px-8 md:pb-24 md:pt-20">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--red)]">
            About us
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">
            Innovative Future Solutions.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-white/80">
            A trusted manufacturer of cleaning solutions and packaging materials
            for households and commercial partners.
          </p>
        </div>
      </div>

      <div className="mx-auto grid max-w-6xl gap-12 px-5 py-16 md:grid-cols-2 md:px-8 md:py-24">
        <div className="space-y-5 text-base leading-relaxed text-[var(--muted)] md:text-lg">
          <p>
            IFS Chemicals is a leading manufacturer of high-quality cleaning
            solutions and packaging materials. With a strong commitment to
            innovation, quality, and customer satisfaction, we have established
            ourselves as a trusted name for households and commercial partners.
          </p>
          <p>
            Manufactured using the latest technology and high-quality
            ingredients, our cleaning products cater to various needs — ensuring
            cleanliness, hygiene, and convenience. From detergent powders
            produced on a fully automated imported plant to dishwash liquids,
            toilet cleaners, bars, oils, and packaging lines, we cover the full
            path from formula to finished pack.
          </p>
          <p>
            Our operations are based at {contact.address}. Distributors and
            partners can reach us anytime for supply, branding, and custom
            packaging requirements.
          </p>
        </div>
        <div className="relative min-h-[320px] overflow-hidden bg-[#e8edf3]">
          <Image
            src="/images/hero/products-showcase.jpg"
            alt="IFS product lineup"
            fill
            className="object-cover"
            sizes="(max-width: 768px) 100vw, 50vw"
          />
        </div>
      </div>

      <div className="border-y border-[var(--line)] bg-white">
        <div className="mx-auto grid max-w-6xl md:grid-cols-3">
          {highlights.map((h) => (
            <div
              key={h}
              className="border-b border-[var(--line)] px-5 py-10 last:border-b-0 md:border-b-0 md:border-r md:px-8 md:last:border-r-0"
            >
              <span className="mb-3 block h-1 w-10 bg-[var(--blue)]" />
              <p className="font-display text-lg font-bold text-[var(--ink)]">{h}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-20">
        <Link
          href="/contact"
          className="inline-block bg-[var(--navy)] px-6 py-3 text-sm font-bold uppercase tracking-[0.1em] text-white hover:bg-[var(--blue)]"
        >
          Contact IFS
        </Link>
      </div>
    </div>
  );
}
