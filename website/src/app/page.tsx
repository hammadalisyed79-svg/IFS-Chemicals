import Image from "next/image";
import Link from "next/link";
import { contact, highlights, products } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";

export default function HomePage() {
  return (
    <>
      <section className="relative min-h-[calc(100svh-5.5rem)] overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src="/images/hero/products-showcase.jpg"
          alt="IFS Chemicals product range"
          fill
          priority
          className="animate-kenburns object-cover object-[center_35%]"
          sizes="100vw"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/88 to-[var(--navy)]/35" />
        <div className="absolute inset-0 bg-gradient-to-t from-[var(--navy)] via-transparent to-[var(--navy)]/40" />

        <div className="relative mx-auto flex min-h-[calc(100svh-5.5rem)] max-w-6xl flex-col justify-end px-5 pb-16 pt-20 md:justify-center md:px-8 md:pb-24">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={320}
            height={90}
            className="animate-rise h-16 w-auto md:h-20"
            priority
          />
          <div className="brand-rule mt-5 h-1 w-24 bg-[var(--red)]" />
          <h1 className="animate-rise-delay font-display mt-6 max-w-2xl text-4xl font-bold leading-[1.05] tracking-tight md:text-6xl lg:text-7xl">
            Cleaning power, engineered in Gujrat.
          </h1>
          <p className="animate-rise-delay-2 mt-5 max-w-lg text-base leading-relaxed text-white/80 md:text-lg">
            Detergent powders, dishwash care, and packaging — manufactured for
            homes, retailers, and B2B partners across Pakistan.
          </p>
          <div className="animate-rise-delay-2 mt-9 flex flex-wrap gap-3">
            <Link
              href="/products"
              className="bg-[var(--red)] px-6 py-3.5 text-sm font-bold uppercase tracking-[0.1em] text-white transition hover:bg-[var(--red-deep)]"
            >
              View products
            </Link>
            <Link
              href="/contact"
              className="border border-white/40 px-6 py-3.5 text-sm font-semibold uppercase tracking-[0.1em] text-white transition hover:border-white hover:bg-white/10"
            >
              Request a quote
            </Link>
          </div>
          <p className="animate-rise-delay-2 mt-8 text-xs font-semibold uppercase tracking-[0.28em] text-white/55">
            Made in Pakistan
          </p>
        </div>
      </section>

      <section className="border-b border-[var(--line)] bg-white">
        <div className="mx-auto grid max-w-6xl divide-y divide-[var(--line)] md:grid-cols-3 md:divide-x md:divide-y-0">
          {highlights.map((item) => (
            <p
              key={item}
              className="px-5 py-7 text-sm font-semibold leading-snug text-[var(--ink)] md:px-8 md:py-9 md:text-[15px]"
            >
              <span className="mb-2 block h-1 w-8 bg-[var(--blue)]" />
              {item}
            </p>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--red)]">
            Product families
          </p>
          <h2 className="font-display mt-3 text-3xl font-bold tracking-tight text-[var(--ink)] md:text-5xl">
            From formula to finished pack.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-[var(--muted)] md:text-lg">
            Six manufacturing lines serving retail brands and industrial buyers —
            detergents, dishwash, toilet care, and packaging.
          </p>
        </div>

        <div className="mt-12 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <Link key={p.slug} href={`/products#${p.slug}`} className="group block">
              <div className="relative aspect-[4/3] overflow-hidden bg-[#e8edf3]">
                <Image
                  src={p.image}
                  alt={p.name}
                  fill
                  className="object-contain p-6 transition duration-500 group-hover:scale-[1.04]"
                  sizes="(max-width: 768px) 100vw, 33vw"
                />
              </div>
              <h3 className="font-display mt-4 text-xl font-bold text-[var(--ink)] group-hover:text-[var(--blue)]">
                {p.name}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.blurb}</p>
            </Link>
          ))}
        </div>
      </section>

      <section className="relative overflow-hidden bg-[var(--navy)] text-white">
        <div className="absolute inset-y-0 right-0 hidden w-1/2 lg:block">
          <Image
            src="/images/factory.jpg"
            alt="IFS Chemicals manufacturing facility"
            fill
            className="object-cover opacity-55"
            sizes="50vw"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] to-transparent" />
        </div>
        <div className="relative mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
          <div className="max-w-xl">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--red)]">
              About IFS
            </p>
            <h2 className="font-display mt-3 text-3xl font-bold tracking-tight md:text-5xl">
              Trusted cleaning power, made in Pakistan.
            </h2>
            <p className="mt-5 text-base leading-relaxed text-white/75 md:text-lg">
              IFS Chemicals manufactures high-quality cleaning solutions and
              packaging materials with a strong commitment to innovation, quality,
              and customer satisfaction. Our detergent powders are produced using
              the latest technology and high-quality ingredients — ensuring
              cleanliness, hygiene, and convenience wash after wash.
            </p>
            <p className="mt-4 text-base leading-relaxed text-white/75">
              B2B partnerships are encouraged. We serve companies and professional
              clients with reliable supply from Bridge Canal Saroki, Gujrat.
            </p>
            <Link
              href="/about"
              className="mt-8 inline-block border border-white/35 px-5 py-3 text-sm font-semibold uppercase tracking-[0.1em] transition hover:bg-white hover:text-[var(--navy)]"
            >
              More about us
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <div className="grid gap-12 lg:grid-cols-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-[var(--red)]">
              Contact
            </p>
            <h2 className="font-display mt-3 text-3xl font-bold tracking-tight md:text-4xl">
              Request a quote or distributor intro.
            </h2>
            <ul className="mt-8 space-y-3 text-[var(--muted)]">
              <li className="text-[var(--ink)]">{contact.address}</li>
              <li>
                <a className="text-xl font-bold text-[var(--blue)]" href={contact.phoneHref}>
                  {contact.phone}
                </a>
              </li>
              {contact.emails.map((e) => (
                <li key={e}>
                  <a className="hover:text-[var(--blue)]" href={`mailto:${e}`}>
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
