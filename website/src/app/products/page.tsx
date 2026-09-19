import type { Metadata } from "next";
import { products } from "@/lib/content";

export const metadata: Metadata = {
  title: "Products",
  description:
    "Detergent powders, bars & oil, dishwash & toilet cleaners, flexible packaging, corrugated boxes, and PET bottle blowing.",
};

export default function ProductsPage() {
  return (
    <div className="bg-[var(--foam)]">
      <div className="bg-[var(--ink)] px-5 pb-16 pt-16 text-[var(--foam)] md:px-8">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--teal-bright)]">
            Products
          </p>
          <h1 className="font-display mt-3 max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">
            Built for homes, shops, and industrial supply.
          </h1>
        </div>
      </div>
      <div className="mx-auto max-w-6xl space-y-16 px-5 py-16 md:px-8 md:py-24">
        {products.map((p) => (
          <section key={p.slug} id={p.slug} className="scroll-mt-24">
            <h2 className="font-display text-2xl font-bold md:text-3xl">{p.name}</h2>
            <p className="mt-2 max-w-2xl text-[var(--ink-soft)]/85">{p.blurb}</p>
            <ul className="mt-6 grid gap-2 sm:grid-cols-2">
              {p.items.map((item) => (
                <li
                  key={item}
                  className="border-l-2 border-[var(--teal)] bg-white px-4 py-3 text-sm font-medium"
                >
                  {item}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
