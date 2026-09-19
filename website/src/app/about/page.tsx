import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About",
  description:
    "IFS Chemicals manufactures cleaning solutions and packaging materials in Gujrat, Pakistan.",
};

export default function AboutPage() {
  return (
    <div className="bg-[var(--foam)]">
      <div className="bg-[var(--ink)] px-5 pb-16 pt-16 text-[var(--foam)] md:px-8">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--teal-bright)]">
            About us
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">
            Innovative Future Solutions.
          </h1>
        </div>
      </div>
      <div className="mx-auto max-w-3xl space-y-6 px-5 py-16 text-base leading-relaxed text-[var(--ink-soft)] md:px-8 md:py-24 md:text-lg">
        <p>
          IFS Chemicals is a leading manufacturer of high-quality cleaning
          solutions and packaging materials. With a strong commitment to
          innovation, quality, and customer satisfaction, we have established
          ourselves as a trusted name for households and commercial partners.
        </p>
        <p>
          Manufactured using the latest technology and high-quality ingredients,
          our cleaning products cater to various needs — ensuring cleanliness,
          hygiene, and convenience. From detergent powders produced on a fully
          automated imported plant to dishwash liquids, toilet cleaners, bars,
          oils, and packaging lines, we cover the full path from formula to
          finished pack.
        </p>
        <p>
          Our operations are based at Bridge Canal Saroki, Gujrat, Pakistan.
          Distributors and partners can reach us anytime for supply, branding,
          and custom packaging requirements.
        </p>
        <Link
          href="/contact"
          className="inline-block bg-[var(--ink)] px-6 py-3 text-sm font-semibold text-[var(--foam)]"
        >
          Contact IFS
        </Link>
      </div>
    </div>
  );
}
