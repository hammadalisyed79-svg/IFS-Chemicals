import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { products } from "@/lib/content";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: "Products — Detergent, Dishwash, Packaging & PET",
  description:
    "Browse IFS Chemicals products: Happy, Train, JagMag, Lashkara & Bahar detergents, dishwash bars and liquids, toilet cleaners, flexible packaging, corrugated boxes, and PET bottle blowing.",
  path: "/products",
});

export default function ProductsPage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="relative overflow-hidden bg-[#071833] text-white">
        <Image
          src="/images/hero/banner-1.jpg"
          alt=""
          fill
          className="object-cover opacity-30"
          sizes="100vw"
          priority
        />
        <div className="relative mx-auto max-w-6xl px-5 pb-14 pt-14 md:px-8 md:pb-20 md:pt-20">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#ff6b6b]">
            Products
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-3xl font-bold tracking-tight sm:text-4xl md:text-6xl">
            Built for homes, shops, and industrial supply.
          </h1>
          <p className="mt-4 max-w-xl text-white/75">
            Explore our full catalog — from automated detergent powder production
            to packaging lines that finish the pack.
          </p>
        </div>
      </div>

      <div className="sticky top-[3.75rem] z-30 border-b border-[var(--line)] bg-white/95 backdrop-blur sm:top-[4.25rem] md:top-[7rem]">
        <div className="mx-auto flex max-w-6xl gap-2 overflow-x-auto px-4 py-3 [-ms-overflow-style:none] [scrollbar-width:none] md:px-8 [&::-webkit-scrollbar]:hidden">
          {products.map((p) => (
            <a
              key={p.slug}
              href={`#${p.slug}`}
              className="shrink-0 whitespace-nowrap px-3 py-2 text-xs font-bold uppercase tracking-[0.08em] text-[var(--muted)] transition hover:bg-[#071833] hover:text-white"
            >
              {p.name}
            </a>
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-16 px-5 py-12 sm:space-y-20 sm:py-16 md:space-y-24 md:px-8 md:py-24">
        {products.map((p) => (
          <section key={p.slug} id={p.slug} className="scroll-mt-28 md:scroll-mt-40">
            <div className="max-w-2xl">
              <h2 className="font-display text-2xl font-bold sm:text-3xl md:text-4xl">
                {p.name}
              </h2>
              <p className="mt-3 text-[var(--muted)]">{p.blurb}</p>
            </div>
            <div className="mt-6 grid grid-cols-1 gap-4 min-[420px]:grid-cols-2 sm:mt-8 sm:gap-6 lg:grid-cols-3">
              {p.items.map((item) => (
                <article key={item.name} className="flex flex-col bg-white shadow-sm">
                  <div className="relative aspect-square overflow-hidden bg-[#eef2f7]">
                    <Image
                      src={item.image}
                      alt={item.name}
                      fill
                      className="object-contain p-4 sm:p-5"
                      sizes="(max-width: 420px) 100vw, (max-width: 1024px) 50vw, 33vw"
                    />
                  </div>
                  <div className="flex flex-1 flex-col border-t border-[var(--line)] px-4 py-4">
                    <h3 className="font-display text-base font-bold text-[var(--ink)] sm:text-lg">
                      {item.name}
                    </h3>
                    <dl className="mt-3 space-y-1.5 text-sm text-[var(--muted)]">
                      <div className="flex gap-2">
                        <dt className="shrink-0 font-semibold text-[var(--ink-soft)]">Pack:</dt>
                        <dd>{item.pack}</dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="shrink-0 font-semibold text-[var(--ink-soft)]">Use:</dt>
                        <dd>{item.use}</dd>
                      </div>
                    </dl>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}

        <div className="border border-[var(--line)] bg-white px-5 py-10 text-center sm:px-6 md:px-10">
          <h2 className="font-display text-2xl font-bold md:text-3xl">
            Need bulk supply or private label?
          </h2>
          <p className="mx-auto mt-3 max-w-lg text-[var(--muted)]">
            Talk to our team for B2B pricing, distributor arrangements, and custom
            packaging.
          </p>
          <Link
            href="/contact"
            className="mt-6 inline-block bg-[#c41e26] px-6 py-3.5 text-sm font-bold uppercase tracking-[0.1em] text-white hover:bg-[#9e161d]"
          >
            Contact sales
          </Link>
        </div>
      </div>
    </div>
  );
}
