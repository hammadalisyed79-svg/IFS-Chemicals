import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { products } from "@/lib/content";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: "Products — Detergent, Hygiene Care & Packaging",
  description:
    "IFS Chemicals product platforms: detergent powders, dishwash and toilet care, bars and oil, flexible packaging, corrugated boxes, and PET bottle blowing — manufactured in Gujrat, Pakistan.",
  path: "/products",
});

export default function ProductsPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="relative overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src="/images/hero/banner-1.jpg"
          alt=""
          fill
          className="object-cover opacity-25"
          sizes="100vw"
          priority
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/90 to-[var(--navy)]/50" />
        <div className="container-site relative pb-16 pt-14 md:pb-24 md:pt-20">
          <p className="eyebrow !text-white/50">Products</p>
          <h1 className="font-display mt-4 max-w-3xl text-3xl font-semibold sm:text-4xl md:text-6xl">
            Product platforms for retail and professional supply.
          </h1>
          <p className="mt-5 max-w-xl text-[1.05rem] leading-relaxed text-white/70">
            Explore our catalogue — from automated detergent production to
            packaging systems that complete the finished pack.
          </p>
        </div>
      </div>

      <div className="sticky top-[3.75rem] z-30 border-b border-[var(--line)] bg-white/95 backdrop-blur sm:top-[4.25rem] md:top-[6.75rem]">
        <div className="container-site flex gap-1 overflow-x-auto py-3 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {products.map((p) => (
            <a
              key={p.slug}
              href={`#${p.slug}`}
              className="shrink-0 whitespace-nowrap px-3.5 py-2 text-[12px] font-medium tracking-[0.04em] text-[var(--muted)] transition hover:bg-[var(--navy)] hover:text-white"
            >
              {p.name}
            </a>
          ))}
        </div>
      </div>

      <div className="container-site space-y-20 py-16 md:space-y-28 md:py-24">
        {products.map((p) => (
          <section key={p.slug} id={p.slug} className="scroll-mt-32 md:scroll-mt-40">
            <div className="max-w-2xl">
              <h2 className="font-display text-2xl font-semibold sm:text-3xl md:text-4xl">
                {p.name}
              </h2>
              <p className="mt-3 text-[15px] leading-relaxed text-[var(--muted)] md:text-base">
                {p.blurb}
              </p>
            </div>
            <div className="mt-8 grid grid-cols-1 gap-5 min-[420px]:grid-cols-2 lg:grid-cols-3">
              {p.items.map((item) => (
                <article key={item.name} className="surface-card flex flex-col overflow-hidden">
                  <div className="img-well relative aspect-square overflow-hidden">
                    <Image
                      src={item.image}
                      alt={item.name}
                      fill
                      className="object-contain p-6 sm:p-7"
                      sizes="(max-width: 420px) 100vw, (max-width: 1024px) 50vw, 33vw"
                    />
                  </div>
                  <div className="flex flex-1 flex-col border-t border-[var(--line)] px-5 py-5">
                    <h3 className="font-display text-base font-semibold text-[var(--ink)] sm:text-lg">
                      {item.name}
                    </h3>
                    <dl className="mt-3 space-y-2 text-sm text-[var(--muted)]">
                      <div className="flex gap-2">
                        <dt className="shrink-0 font-medium text-[var(--ink-soft)]">Pack</dt>
                        <dd>{item.pack}</dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="shrink-0 font-medium text-[var(--ink-soft)]">Use</dt>
                        <dd>{item.use}</dd>
                      </div>
                    </dl>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}

        <div className="surface-card px-6 py-12 text-center md:px-12 md:py-14">
          <h2 className="font-display text-2xl font-semibold md:text-3xl">
            Bulk supply and private-label programmes
          </h2>
          <p className="mx-auto mt-3 max-w-lg text-[var(--muted)]">
            Speak with our commercial team about volume pricing, distributor
            arrangements, and custom packaging.
          </p>
          <Link href="/contact" className="btn btn-accent mt-8">
            Contact sales
          </Link>
        </div>
      </div>
    </div>
  );
}
