import Image from "next/image";
import Link from "next/link";
import { contact, highlights, products } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";
import { TrustSection } from "@/components/TrustSection";

export default function HomePage() {
  return (
    <>
      <section className="relative min-h-[min(92svh,860px)] overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src="/images/hero/products-showcase.jpg"
          alt="IFS Chemicals product portfolio"
          fill
          priority
          className="animate-kenburns object-cover object-[70%_40%] md:object-[64%_38%]"
          sizes="100vw"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/90 to-[var(--navy)]/25 md:via-[var(--navy)]/88 md:to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-t from-[var(--navy)] via-transparent to-[var(--navy)]/35" />

        <div className="container-site relative flex min-h-[min(92svh,860px)] flex-col justify-end pb-[calc(5.5rem+var(--dock-h,0px))] pt-20 md:justify-center md:pb-24 md:pt-24">
          <p className="animate-rise text-[11px] font-semibold uppercase tracking-[0.22em] text-white/70">
            IFS Chemicals
          </p>
          <h1 className="animate-rise-delay font-display mt-5 max-w-2xl text-[2.35rem] font-semibold text-white sm:text-5xl md:text-6xl lg:text-[4.25rem]">
            Innovative Future Solutions for everyday performance.
          </h1>
          <p className="animate-rise-delay-2 mt-5 max-w-lg text-[1.05rem] leading-relaxed text-white/78 md:mt-6 md:text-lg">
            Detergent powders, hygiene care, and packaging systems for retail
            brands and professional buyers — manufactured to international
            quality standards.
          </p>
          <div className="animate-rise-delay-2 mt-9 flex flex-col gap-3 sm:mt-10 sm:flex-row">
            <Link href="/products" className="btn btn-accent">
              Explore products
            </Link>
            <Link href="/quote" className="btn btn-ghost">
              Request a quote
            </Link>
          </div>
        </div>
      </section>

      <section className="border-b border-[var(--line)] bg-white">
        <div className="container-site grid divide-y divide-[var(--line)] md:grid-cols-3 md:divide-x md:divide-y-0">
          {highlights.map((item, i) => (
            <div key={item} className="px-1 py-8 md:px-8 md:py-10">
              <p className="text-[11px] font-semibold tracking-[0.16em] text-[var(--muted)]">
                0{i + 1}
              </p>
              <p className="mt-3 text-[15px] font-medium leading-snug text-[var(--ink)] md:text-base">
                {item}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="container-site py-14 md:py-28">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <p className="eyebrow">Capabilities</p>
            <h2 className="font-display mt-3 text-3xl font-semibold text-[var(--ink)] md:text-5xl">
              An integrated portfolio of cleaning and packaging platforms.
            </h2>
            <p className="lead mt-4 max-w-xl">
              From formulation through finished packaging, IFS Chemicals supplies
              brand owners and distributors with reliable quality and commercial
              continuity.
            </p>
          </div>
          <Link href="/products" className="btn btn-outline shrink-0 self-start md:self-auto">
            View full catalogue
          </Link>
        </div>

        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <Link
              key={p.slug}
              href={`/products/${p.slug}`}
              className="group surface-card overflow-hidden transition hover:-translate-y-0.5"
            >
              <div className="img-well relative aspect-[5/4] overflow-hidden">
                <Image
                  src={p.image}
                  alt={p.name}
                  fill
                  className="object-contain p-8 transition duration-500 group-hover:scale-[1.03]"
                  sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                />
              </div>
              <div className="border-t border-[var(--line)] px-5 py-5">
                <h3 className="font-display text-lg font-semibold text-[var(--ink)] transition group-hover:text-[var(--blue)]">
                  {p.name}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.blurb}</p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <TrustSection />

      <section className="relative overflow-hidden bg-[var(--navy)] text-white">
        <div className="absolute inset-y-0 right-0 hidden w-[48%] lg:block">
          <Image
            src="/images/factory.jpg"
            alt="IFS Chemicals manufacturing facility"
            fill
            className="object-cover opacity-50"
            sizes="48vw"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/70 to-transparent" />
        </div>
        <div className="container-site relative py-20 md:py-28">
          <div className="max-w-xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/45">
              Company
            </p>
            <h2 className="font-display mt-3 text-3xl font-semibold md:text-5xl">
              A manufacturing partner built for long-term supply.
            </h2>
            <p className="mt-5 text-[1.05rem] leading-relaxed text-white/70">
              IFS Chemicals develops cleaning formulations and packaging
              materials with a focus on process control, product consistency, and
              durable commercial partnerships.
            </p>
            <p className="mt-4 text-[1.05rem] leading-relaxed text-white/70">
              We support distributors, retailers, and professional buyers with
              reliable supply programmes and responsive commercial service.
            </p>
            <Link
              href="/about"
              className="btn btn-ghost mt-9 border-white/30"
            >
              About the company
            </Link>
          </div>
        </div>
      </section>

      <section className="container-site py-14 md:py-28">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
          <div>
            <p className="eyebrow">Contact</p>
            <h2 className="font-display mt-3 text-3xl font-semibold text-[var(--ink)] md:text-4xl">
              Discuss supply, distribution, or private label.
            </h2>
            <p className="lead mt-4">
              Share your requirements and our commercial team will respond with
              product guidance, packaging options, and next steps.
            </p>
            <ul className="mt-9 space-y-3 text-[15px] text-[var(--muted)]">
              <li className="font-medium text-[var(--ink)]">{contact.address}</li>
              <li>
                <a className="text-xl font-semibold text-[var(--blue)]" href={contact.phoneHref}>
                  {contact.phone}
                </a>
              </li>
              <li>
                <a
                  className="font-medium text-[var(--blue)] transition hover:underline"
                  href={contact.whatsapp}
                  target="_blank"
                  rel="noreferrer"
                >
                  Continue on WhatsApp
                </a>
              </li>
              {contact.emails.map((e) => (
                <li key={e}>
                  <a className="transition hover:text-[var(--blue)]" href={`mailto:${e}`}>
                    {e}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <div className="surface-card p-6 md:p-8">
            <h3 className="font-display text-xl font-semibold text-[var(--ink)]">
              Inquiry form
            </h3>
            <p className="mt-2 text-sm text-[var(--muted)]">
              General, distributor, and B2B enquiries.
            </p>
            <div className="mt-6">
              <ContactForm />
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
