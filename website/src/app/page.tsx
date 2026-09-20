import Image from "next/image";
import Link from "next/link";
import { contact, highlights, products } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";
import { TrustSection } from "@/components/TrustSection";

export default function HomePage() {
  return (
    <>
      <section className="hero-mobile relative min-h-[min(92svh,860px)] overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src="/images/hero/products-showcase.jpg"
          alt="IFS Chemicals product portfolio"
          fill
          priority
          className="animate-kenburns object-cover object-[72%_38%] sm:object-[70%_40%] md:object-[64%_38%]"
          sizes="100vw"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-[var(--navy)]/80 via-[var(--navy)]/55 to-[var(--navy)] md:bg-gradient-to-r md:from-[var(--navy)] md:via-[var(--navy)]/88 md:to-transparent" />
        <div className="absolute inset-0 hidden bg-gradient-to-t from-[var(--navy)] via-transparent to-[var(--navy)]/35 md:block" />

        <div className="hero-mobile-copy container-site relative flex min-h-[min(88svh,720px)] flex-col justify-end pb-10 pt-16 md:min-h-[min(92svh,860px)] md:justify-center md:pb-24 md:pt-24">
          <div className="mb-5 h-px w-12 origin-left bg-[var(--red)] brand-rule md:mb-0 md:hidden" />
          <p className="animate-rise text-[11px] font-semibold uppercase tracking-[0.22em] text-white/55">
            Manufacturer · Gujrat, Pakistan
          </p>
          <h1 className="animate-rise-delay font-display mt-4 max-w-2xl text-[2.15rem] font-semibold leading-[1.08] text-white sm:mt-5 sm:text-5xl md:text-6xl lg:text-[4.25rem]">
            Cleaning solutions engineered for everyday performance.
          </h1>
          <p className="animate-rise-delay-2 mt-4 max-w-lg text-[0.98rem] leading-relaxed text-white/78 sm:mt-6 sm:text-[1.05rem] md:text-lg">
            Detergent powders, hygiene care, and packaging systems for retail
            brands and professional buyers — manufactured to international
            standards from our facility in Pakistan.
          </p>
          <div className="animate-rise-delay-2 mt-8 grid grid-cols-1 gap-3 sm:mt-10 sm:flex sm:flex-row">
            <Link href="/products" className="btn btn-accent w-full sm:w-auto">
              Explore products
            </Link>
            <Link href="/quote" className="btn btn-ghost w-full sm:w-auto">
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
              Six product platforms. One manufacturing standard.
            </h2>
            <p className="lead mt-4 max-w-xl">
              From formulation to finished packaging, IFS supports brand owners
              and distributors with reliable supply and consistent quality.
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
            alt="IFS Chemicals manufacturing facility in Gujrat, Pakistan"
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
              A manufacturing partner you can scale with.
            </h2>
            <p className="mt-5 text-[1.05rem] leading-relaxed text-white/70">
              IFS Chemicals develops and produces cleaning solutions and packaging
              materials with a focus on process control, product consistency, and
              long-term supply partnerships.
            </p>
            <p className="mt-4 text-[1.05rem] leading-relaxed text-white/70">
              Based at Bridge Canal Saroki, Gujrat, we support distributors and
              professional clients across Pakistan.
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
              Start a supply or distribution conversation.
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
              General, distributor, and B2B requests welcome.
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
