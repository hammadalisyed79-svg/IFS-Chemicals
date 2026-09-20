import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { contact, highlights } from "@/lib/content";
import { mapsSearchUrl, pageMeta, trustPillars } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: "About Us — Manufacturer in Gujrat, Pakistan",
  description:
    "Learn about IFS Chemicals: detergent and packaging manufacturing at Bridge Canal Saroki, Gujrat. Automated plant, Made in Pakistan quality for homes and B2B partners.",
  path: "/about",
});

export default function AboutPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="relative overflow-hidden bg-[#071833] text-white">
        <Image
          src="/images/factory.jpg"
          alt="IFS Chemicals manufacturing facility in Gujrat"
          fill
          className="object-cover opacity-40"
          sizes="100vw"
          priority
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#071833] via-[#071833]/85 to-[#071833]/40" />
        <div className="relative mx-auto max-w-6xl px-5 pb-14 pt-14 md:px-8 md:pb-24 md:pt-20">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#ff6b6b]">
            About us
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-3xl font-bold tracking-tight sm:text-4xl md:text-6xl">
            Innovative Future Solutions.
          </h1>
          <p className="mt-5 max-w-xl text-base text-white/80 sm:text-lg">
            A trusted manufacturer of cleaning solutions and packaging materials
            for households and commercial partners — based in Gujrat, Pakistan.
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
          <a
            href={mapsSearchUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-sm font-semibold text-[#0b5ea8] underline"
          >
            View location on Google Maps →
          </a>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="relative min-h-[200px] overflow-hidden bg-[#e8edf3] sm:row-span-2 sm:min-h-full">
            <Image
              src="/images/factory.jpg"
              alt="IFS plant exterior"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 100vw, 25vw"
            />
          </div>
          <div className="relative min-h-[160px] overflow-hidden bg-[#e8edf3]">
            <Image
              src="/images/pet-blowing.jpg"
              alt="PET bottle blowing"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 50vw, 25vw"
            />
          </div>
          <div className="relative min-h-[160px] overflow-hidden bg-[#e8edf3]">
            <Image
              src="/images/about-team.jpg"
              alt="IFS operations"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 50vw, 25vw"
            />
          </div>
        </div>
      </div>

      <div className="border-y border-[var(--line)] bg-white">
        <div className="mx-auto grid max-w-6xl md:grid-cols-3">
          {trustPillars.map((p) => (
            <div
              key={p.title}
              className="border-b border-[var(--line)] px-5 py-10 last:border-b-0 md:border-b-0 md:border-r md:px-8 md:last:border-r-0"
            >
              <span className="mb-3 block h-1 w-10 bg-[#0b5ea8]" />
              <p className="font-display text-lg font-bold text-[var(--ink)]">{p.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.body}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="border-b border-[var(--line)] bg-[var(--paper)]">
        <div className="mx-auto grid max-w-6xl md:grid-cols-3">
          {highlights.map((h) => (
            <div
              key={h}
              className="border-b border-[var(--line)] px-5 py-8 last:border-b-0 md:border-b-0 md:border-r md:px-8 md:last:border-r-0"
            >
              <p className="text-sm font-semibold text-[var(--ink)]">{h}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-20">
        <Link
          href="/contact"
          className="inline-block bg-[#071833] px-6 py-3 text-sm font-bold uppercase tracking-[0.1em] text-white hover:bg-[#0b5ea8]"
        >
          Contact IFS
        </Link>
      </div>
    </div>
  );
}
