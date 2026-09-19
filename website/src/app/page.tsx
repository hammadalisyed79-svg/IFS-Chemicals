import Link from "next/link";
import { contact, products } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";

export default function HomePage() {
  return (
    <>
      <section className="relative min-h-[calc(100svh-4.5rem)] overflow-hidden bg-[var(--ink)] text-[var(--foam)]">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_35%,rgba(24,196,168,0.28),transparent_55%),radial-gradient(ellipse_at_15%_80%,rgba(232,165,75,0.18),transparent_45%),linear-gradient(160deg,#07141c_0%,#0b2a2a_55%,#07141c_100%)]" />
          <div className="hero-grid absolute inset-0 animate-drift" />
          <div className="absolute -right-24 top-24 h-[420px] w-[420px] rounded-full border border-[var(--teal-bright)]/20" />
          <div className="absolute -right-8 top-40 h-[280px] w-[280px] rounded-full border border-[var(--amber)]/25" />
        </div>

        <div className="relative mx-auto flex min-h-[calc(100svh-4.5rem)] max-w-6xl flex-col justify-end px-5 pb-16 pt-16 md:justify-center md:px-8 md:pb-24 md:pt-20">
          <p className="animate-rise text-xs font-semibold uppercase tracking-[0.28em] text-[var(--teal-bright)]">
            Gujrat · Pakistan
          </p>
          <h1 className="animate-rise-delay font-display mt-4 max-w-4xl text-5xl font-extrabold leading-[0.95] tracking-tight md:text-7xl lg:text-8xl">
            <span className="brand-shimmer">IFS Chemicals</span>
          </h1>
          <p className="animate-rise-delay-2 mt-6 max-w-xl text-lg leading-relaxed text-[var(--foam)]/80 md:text-xl">
            Cleaning solutions and packaging materials engineered for everyday
            brilliance — from detergent powders to PET, corrugated, and flexible
            packs.
          </p>
          <div className="animate-rise-delay-2 mt-10 flex flex-wrap gap-3">
            <Link
              href="/products"
              className="bg-[var(--teal-bright)] px-6 py-3 text-sm font-bold text-[var(--ink)] transition hover:bg-[var(--foam)]"
            >
              Explore products
            </Link>
            <Link
              href="/contact"
              className="border border-[var(--foam)]/35 px-6 py-3 text-sm font-semibold text-[var(--foam)] transition hover:border-[var(--foam)] hover:bg-[var(--foam)]/10"
            >
              Talk to us
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--teal)]">
          What we make
        </p>
        <h2 className="font-display mt-3 max-w-2xl text-3xl font-bold tracking-tight text-[var(--ink)] md:text-5xl">
          Six product families. One manufacturing standard.
        </h2>
        <div className="mt-12 grid gap-px bg-[var(--line)] sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <Link
              key={p.slug}
              href={`/products#${p.slug}`}
              className="group bg-[var(--foam)] p-7 transition hover:bg-white"
            >
              <h3 className="font-display text-xl font-bold text-[var(--ink)] group-hover:text-[var(--teal)]">
                {p.name}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-[var(--ink-soft)]/80">
                {p.blurb}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section className="bg-[var(--ink-soft)] text-[var(--foam)]">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-20 md:grid-cols-2 md:px-8 md:py-28">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--teal-bright)]">
              About
            </p>
            <h2 className="font-display mt-3 text-3xl font-bold tracking-tight md:text-5xl">
              Trusted cleaning power, made in Pakistan.
            </h2>
          </div>
          <div className="space-y-4 text-base leading-relaxed text-[var(--foam)]/80 md:pt-8">
            <p>
              IFS Chemicals is a leading manufacturer of high-quality cleaning
              solutions and packaging materials. With a strong commitment to
              innovation, quality, and customer satisfaction, we serve domestic
              and commercial needs across detergent, dishwash, toilet care, and
              packaging.
            </p>
            <p>
              Our detergent powders are manufactured using the latest technology
              and high-quality ingredients — ensuring cleanliness, hygiene, and
              convenience wash after wash.
            </p>
            <Link
              href="/about"
              className="inline-block pt-2 text-sm font-semibold text-[var(--teal-bright)] hover:underline"
            >
              More about IFS →
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <div className="grid gap-12 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--teal)]">
              Contact
            </p>
            <h2 className="font-display mt-3 text-3xl font-bold tracking-tight md:text-4xl">
              Request a quote or distributor intro.
            </h2>
            <ul className="mt-8 space-y-3 text-sm text-[var(--ink-soft)]">
              <li>{contact.address}</li>
              <li>
                <a className="font-semibold text-[var(--ink)]" href={contact.phoneHref}>
                  {contact.phone}
                </a>
              </li>
              {contact.emails.map((e) => (
                <li key={e}>
                  <a className="hover:text-[var(--teal)]" href={`mailto:${e}`}>
                    {e}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <ContactForm />
        </div>
      </section>
    </>
  );
}
