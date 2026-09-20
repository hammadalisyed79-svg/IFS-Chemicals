import Image from "next/image";
import Link from "next/link";
import { contact, highlights, products } from "@/lib/content";
import { ContactForm } from "@/components/ContactForm";
import { TrustSection } from "@/components/TrustSection";

export default function HomePage() {
  return (
    <>
      <section className="relative min-h-[min(100svh,920px)] overflow-hidden bg-[#071833] text-white">
        <Image
          src="/images/hero/products-showcase.jpg"
          alt="IFS Chemicals product range — Happy, Train, JagMag, Lashkara, Bahar, Ring"
          fill
          priority
          className="animate-kenburns object-cover object-[72%_40%] sm:object-[68%_38%] md:object-[62%_36%]"
          sizes="100vw"
        />
        {/* Strong left scrim so brand + copy stay readable over products */}
        <div className="absolute inset-0 bg-gradient-to-r from-[#071833] from-0% via-[#071833]/92 via-35% to-[#071833]/25 to-75% md:via-40% md:to-[#071833]/15" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#071833] via-transparent to-[#071833]/50" />
        <div className="pointer-events-none absolute inset-y-0 left-0 w-full max-w-3xl bg-gradient-to-r from-[#071833]/55 to-transparent md:max-w-2xl" />

        <div className="relative mx-auto flex min-h-[min(100svh,920px)] max-w-6xl flex-col justify-end px-5 pb-14 pt-16 sm:pb-16 md:justify-center md:px-8 md:pb-24 md:pt-20">
          <Image
            src="/images/logo.png"
            alt="IFS Chemicals"
            width={320}
            height={90}
            className="animate-rise h-14 w-auto drop-shadow-lg sm:h-16 md:h-20"
            priority
          />
          <div className="brand-rule mt-5 h-1 w-24 bg-[#c41e26]" />
          <h1 className="animate-rise-delay font-display mt-6 max-w-xl text-[2.35rem] font-bold leading-[1.05] tracking-tight text-white drop-shadow-md sm:text-5xl md:max-w-2xl md:text-6xl lg:text-7xl">
            Cleaning power, engineered in Gujrat.
          </h1>
          <p className="animate-rise-delay-2 mt-5 max-w-md text-base leading-relaxed text-white/90 sm:max-w-lg sm:text-lg">
            Detergent powders, dishwash care, and packaging — manufactured for
            homes, retailers, and B2B partners across Pakistan.
          </p>
          <div className="animate-rise-delay-2 mt-8 flex flex-col gap-3 sm:mt-9 sm:flex-row sm:flex-wrap">
            <Link
              href="/products"
              className="bg-[#c41e26] px-6 py-3.5 text-center text-sm font-bold uppercase tracking-[0.1em] text-white transition hover:bg-[#9e161d]"
            >
              View products
            </Link>
            <Link
              href="/contact"
              className="border border-white/50 bg-white/5 px-6 py-3.5 text-center text-sm font-semibold uppercase tracking-[0.1em] text-white backdrop-blur-sm transition hover:border-white hover:bg-white/15"
            >
              Request a quote
            </Link>
          </div>
          <p className="animate-rise-delay-2 mt-8 text-xs font-semibold uppercase tracking-[0.28em] text-white/60">
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
              <span className="mb-2 block h-1 w-8 bg-[#0b5ea8]" />
              {item}
            </p>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16 sm:py-20 md:px-8 md:py-28">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#c41e26]">
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

        <div className="mt-10 grid gap-x-5 gap-y-8 sm:mt-12 sm:grid-cols-2 sm:gap-y-10 lg:grid-cols-3">
          {products.map((p) => (
            <Link key={p.slug} href={`/products#${p.slug}`} className="group block">
              <div className="relative aspect-[4/3] overflow-hidden bg-[#e8edf3]">
                <Image
                  src={p.image}
                  alt={p.name}
                  fill
                  className="object-contain p-4 transition duration-500 group-hover:scale-[1.04] sm:p-6"
                  sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                />
              </div>
              <h3 className="font-display mt-3 text-lg font-bold text-[var(--ink)] group-hover:text-[#0b5ea8] sm:mt-4 sm:text-xl">
                {p.name}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.blurb}</p>
            </Link>
          ))}
        </div>
      </section>

      <TrustSection />

      <section className="relative overflow-hidden bg-[#071833] text-white">
        <div className="absolute inset-y-0 right-0 hidden w-1/2 lg:block">
          <Image
            src="/images/factory.jpg"
            alt="IFS Chemicals manufacturing facility in Gujrat, Pakistan"
            fill
            className="object-cover opacity-55"
            sizes="50vw"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-[#071833] to-transparent" />
        </div>
        <div className="relative mx-auto max-w-6xl px-5 py-16 sm:py-20 md:px-8 md:py-28">
          <div className="max-w-xl">
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#ff6b6b]">
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
              className="mt-8 inline-block border border-white/35 px-5 py-3 text-sm font-semibold uppercase tracking-[0.1em] transition hover:bg-white hover:text-[#071833]"
            >
              More about us
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-16 sm:py-20 md:px-8 md:py-28">
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-12">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#c41e26]">
              Contact
            </p>
            <h2 className="font-display mt-3 text-3xl font-bold tracking-tight md:text-4xl">
              Request a quote or distributor intro.
            </h2>
            <ul className="mt-8 space-y-3 text-[var(--muted)]">
              <li className="text-[var(--ink)]">{contact.address}</li>
              <li>
                <a className="text-xl font-bold text-[#0b5ea8]" href={contact.phoneHref}>
                  {contact.phone}
                </a>
              </li>
              <li>
                <a
                  className="font-semibold text-[#0b5ea8] hover:underline"
                  href={contact.whatsapp}
                  target="_blank"
                  rel="noreferrer"
                >
                  Chat on WhatsApp
                </a>
              </li>
              {contact.emails.map((e) => (
                <li key={e}>
                  <a className="hover:text-[#0b5ea8]" href={`mailto:${e}`}>
                    {e}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-sm bg-white p-5 shadow-sm sm:p-6 md:p-8">
            <ContactForm />
          </div>
        </div>
      </section>
    </>
  );
}
