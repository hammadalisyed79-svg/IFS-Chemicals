import type { Metadata } from "next";
import Link from "next/link";
import { QuoteForm } from "@/components/QuoteForm";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: "Request a Quote",
  description:
    "Build a product quote list from the IFS Chemicals catalogue and submit for trade pricing. No online checkout — commercial response from Gujrat, Pakistan.",
  path: "/quote",
});

export default function QuotePage() {
  return (
    <div className="bg-[var(--paper)]">
      <div className="bg-[var(--navy)] text-white">
        <div className="container-site pb-12 pt-10 md:pb-20 md:pt-16">
          <p className="eyebrow !text-white/50">Commerce</p>
          <h1 className="font-display mt-4 max-w-3xl text-[1.85rem] font-semibold leading-tight sm:text-4xl md:text-5xl">
            Request a quote — no online checkout.
          </h1>
          <p className="mt-4 max-w-xl text-[0.98rem] leading-relaxed text-white/70 md:mt-5 md:text-[1.05rem]">
            Select products, adjust quantities, and send your list. We reply with
            pricing — nothing is paid on this site.
          </p>
          <Link href="/products" className="btn btn-ghost mt-7 w-full sm:mt-8 sm:w-auto">
            Browse catalogue
          </Link>
        </div>
      </div>
      <div className="container-site py-14 md:py-20">
        <QuoteForm />
      </div>
    </div>
  );
}
