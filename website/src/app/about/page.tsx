import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { contact, highlights } from "@/lib/content";
import { mapsSearchUrl, pageMeta, trustPillars } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: "About — Manufacturer in Gujrat, Pakistan",
  description:
    "IFS Chemicals manufactures cleaning solutions and packaging materials at Bridge Canal Saroki, Gujrat. Automated production and Made in Pakistan quality for retail and B2B partners.",
  path: "/about",
});

export default function AboutPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="relative overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src="/images/factory.jpg"
          alt="IFS Chemicals manufacturing facility in Gujrat"
          fill
          className="object-cover opacity-35"
          sizes="100vw"
          priority
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/88 to-[var(--navy)]/35" />
        <div className="container-site relative pb-16 pt-14 md:pb-24 md:pt-20">
          <p className="eyebrow !text-white/50">Company</p>
          <h1 className="font-display mt-4 max-w-3xl text-3xl font-semibold sm:text-4xl md:text-6xl">
            Innovative Future Solutions.
          </h1>
          <p className="mt-5 max-w-xl text-[1.05rem] leading-relaxed text-white/75 md:text-lg">
            A manufacturing partner for cleaning solutions and packaging
            materials — serving households, retailers, and professional buyers
            from Gujrat, Pakistan.
          </p>
        </div>
      </div>

      <div className="container-site grid gap-14 py-16 md:grid-cols-2 md:gap-16 md:py-24">
        <div className="space-y-5 text-[1.05rem] leading-relaxed text-[var(--muted)]">
          <p>
            IFS Chemicals develops and produces high-quality cleaning solutions
            and packaging materials with a focus on process control, product
            consistency, and long-term supply partnerships.
          </p>
          <p>
            Our portfolio spans detergent powders from a fully automated
            imported plant, dishwash liquids and toilet cleaners, bars and oils,
            through to flexible packaging, corrugated cartons, and PET bottle
            blowing — covering the path from formulation to finished pack.
          </p>
          <p>
            Operations are based at {contact.address}. Distributors and
            commercial partners can contact us for supply, branding, and custom
            packaging requirements.
          </p>
          <a
            href={mapsSearchUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-sm font-semibold text-[var(--blue)] transition hover:underline"
          >
            View location on Google Maps →
          </a>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="relative min-h-[220px] overflow-hidden bg-[var(--paper-2)] sm:row-span-2 sm:min-h-full">
            <Image
              src="/images/factory.jpg"
              alt="IFS plant exterior"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 100vw, 25vw"
            />
          </div>
          <div className="relative min-h-[160px] overflow-hidden bg-[var(--paper-2)]">
            <Image
              src="/images/products/pet-bottle.jpg"
              alt="PET bottle blowing"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 50vw, 25vw"
            />
          </div>
          <div className="relative min-h-[160px] overflow-hidden bg-[var(--paper-2)]">
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
        <div className="container-site grid md:grid-cols-3">
          {trustPillars.map((p, i) => (
            <div
              key={p.title}
              className="border-b border-[var(--line)] px-1 py-10 last:border-b-0 md:border-b-0 md:border-r md:px-8 md:first:pl-0 md:last:border-r-0 md:last:pr-0"
            >
              <p className="text-[11px] font-semibold tracking-[0.16em] text-[var(--muted)]">
                0{i + 1}
              </p>
              <p className="font-display mt-3 text-lg font-semibold text-[var(--ink)]">
                {p.title}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.body}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="border-b border-[var(--line)] bg-[var(--paper)]">
        <div className="container-site grid divide-y divide-[var(--line)] md:grid-cols-3 md:divide-x md:divide-y-0">
          {highlights.map((h, i) => (
            <div key={h} className="px-1 py-8 md:px-8">
              <p className="text-[11px] font-semibold tracking-[0.16em] text-[var(--muted)]">
                0{i + 1}
              </p>
              <p className="mt-3 text-[15px] font-medium leading-snug text-[var(--ink)]">
                {h}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="container-site py-16 md:py-20">
        <Link href="/contact" className="btn btn-primary">
          Contact IFS
        </Link>
      </div>
    </div>
  );
}
