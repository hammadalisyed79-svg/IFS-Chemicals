import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  allCatalogSlugs,
  contact,
  getCatalogEntry,
  type CatalogItem,
  type ProductFamily,
} from "@/lib/content";
import { pageMeta, siteUrl } from "@/lib/seo";
import { AddToQuoteButton } from "@/components/AddToQuoteButton";

type Props = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return allCatalogSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const entry = getCatalogEntry(slug);
  if (!entry) return {};

  if (entry.kind === "family") {
    const f = entry.family;
    return pageMeta({
      title: `${f.name} — Products`,
      description: f.blurb,
      path: `/products/${f.slug}`,
    });
  }

  const { family, item } = entry;
  return pageMeta({
    title: `${item.name} — ${family.name}`,
    description:
      item.summary ||
      `${item.name}: ${item.pack}. ${item.use}. Manufactured by IFS Chemicals in Gujrat, Pakistan.`,
    path: `/products/${item.slug}`,
  });
}

export default async function CatalogDetailPage({ params }: Props) {
  const { slug } = await params;
  const entry = getCatalogEntry(slug);
  if (!entry) notFound();

  if (entry.kind === "family") {
    return <FamilyDetail family={entry.family} />;
  }
  return <ItemDetail family={entry.family} item={entry.item} />;
}

function DistributorCta() {
  return (
    <div className="surface-card mt-14 flex flex-col gap-5 px-6 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8">
      <div>
        <p className="font-display text-lg font-semibold text-[var(--ink)]">
          Distributor price lists
        </p>
        <p className="mt-1 max-w-md text-sm text-[var(--muted)]">
          Current trade pricing and partner tools are available in the secure
          partner portal for authorised distributors.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <a
          href={contact.erpUrl}
          target="_blank"
          rel="noreferrer"
          className="btn btn-primary"
        >
          Open partner portal
        </a>
        <Link href="/contact" className="btn btn-outline">
          Request access
        </Link>
      </div>
    </div>
  );
}

function FamilyDetail({ family }: { family: ProductFamily }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: family.name,
    description: family.blurb,
    url: `${siteUrl}/products/${family.slug}`,
    isPartOf: { "@type": "WebSite", name: "IFS Chemicals", url: siteUrl },
  };

  return (
    <div className="bg-[var(--paper)]">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="relative overflow-hidden bg-[var(--navy)] text-white">
        <Image
          src={family.image}
          alt=""
          fill
          className="object-cover opacity-20"
          sizes="100vw"
          priority
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--navy)] via-[var(--navy)]/92 to-[var(--navy)]/55" />
        <div className="container-site relative pb-14 pt-12 md:pb-20 md:pt-16">
          <nav className="text-[12px] text-white/50">
            <Link href="/products" className="transition hover:text-white">
              Products
            </Link>
            <span className="mx-2">/</span>
            <span className="text-white/80">{family.name}</span>
          </nav>
          <p className="eyebrow mt-6 !text-white/50">Product platform</p>
          <h1 className="font-display mt-3 max-w-3xl text-3xl font-semibold sm:text-4xl md:text-5xl">
            {family.name}
          </h1>
          <p className="mt-5 max-w-xl text-[1.05rem] leading-relaxed text-white/70">
            {family.blurb}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/contact" className="btn btn-accent">
              Request a quote
            </Link>
            <Link href="/products" className="btn btn-ghost">
              Back to catalogue
            </Link>
          </div>
        </div>
      </div>

      <div className="container-site py-16 md:py-20">
        {family.gallery && family.gallery.length > 0 ? (
          <section className="mb-16">
            <p className="eyebrow">Capability gallery</p>
            <h2 className="font-display mt-3 text-2xl font-semibold text-[var(--ink)] md:text-3xl">
              Production and packaging in context
            </h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {family.gallery.map((shot) => (
                <figure
                  key={shot.src + shot.label}
                  className="group relative aspect-[4/5] overflow-hidden bg-[var(--paper-2)]"
                >
                  <Image
                    src={shot.src}
                    alt={shot.alt}
                    fill
                    className="object-contain p-3 transition duration-700 group-hover:scale-[1.02] sm:p-4"
                    sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-[var(--navy)]/70 via-transparent to-transparent pointer-events-none" />
                  <figcaption className="absolute inset-x-0 bottom-0 px-4 pb-4 text-[12px] font-medium tracking-[0.06em] text-white">
                    {shot.label}
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>
        ) : null}

        <section>
          <p className="eyebrow">Range</p>
          <h2 className="font-display mt-3 text-2xl font-semibold text-[var(--ink)] md:text-3xl">
            SKUs in this platform
          </h2>
          <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {family.items.map((item) => (
              <Link
                key={item.slug}
                href={`/products/${item.slug}`}
                className="group surface-card overflow-hidden transition hover:-translate-y-0.5"
              >
                <div className="img-well relative aspect-square overflow-hidden">
                  <Image
                    src={item.image}
                    alt={item.name}
                    fill
                    className="object-contain p-7 transition duration-500 group-hover:scale-[1.03]"
                    sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                  />
                </div>
                <div className="border-t border-[var(--line)] px-5 py-5">
                  <h3 className="font-display text-lg font-semibold text-[var(--ink)] transition group-hover:text-[var(--blue)]">
                    {item.name}
                  </h3>
                  <p className="mt-2 text-sm text-[var(--muted)]">
                    {item.pack} · {item.use}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </section>

        <DistributorCta />
      </div>
    </div>
  );
}

function ItemDetail({
  family,
  item,
}: {
  family: ProductFamily;
  item: CatalogItem;
}) {
  const related = family.items.filter((i) => i.slug !== item.slug).slice(0, 3);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: item.name,
    description:
      item.summary ||
      `${item.name}. Pack: ${item.pack}. Use: ${item.use}.`,
    image: `${siteUrl}${item.image}`,
    brand: { "@type": "Brand", name: "IFS Chemicals" },
    manufacturer: {
      "@type": "Organization",
      name: "IFS Chemicals",
      url: siteUrl,
    },
    category: family.name,
    url: `${siteUrl}/products/${item.slug}`,
  };

  return (
    <div className="bg-[var(--paper)]">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="container-site py-10 md:py-16">
        <nav className="text-[12px] text-[var(--muted)]">
          <Link href="/products" className="transition hover:text-[var(--ink)]">
            Products
          </Link>
          <span className="mx-2">/</span>
          <Link
            href={`/products/${family.slug}`}
            className="transition hover:text-[var(--ink)]"
          >
            {family.name}
          </Link>
          <span className="mx-2">/</span>
          <span className="text-[var(--ink)]">{item.name}</span>
        </nav>

        <div className="mt-8 grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div className="img-well relative aspect-square overflow-hidden">
            <Image
              src={item.image}
              alt={item.name}
              fill
              priority
              className="object-contain p-10 md:p-14"
              sizes="(max-width: 1024px) 100vw, 50vw"
            />
          </div>
          <div className="flex flex-col justify-center">
            <p className="eyebrow">{family.name}</p>
            <h1 className="font-display mt-3 text-3xl font-semibold text-[var(--ink)] md:text-4xl">
              {item.name}
            </h1>
            <p className="lead mt-4">
              {item.summary ||
                `${item.name} from IFS Chemicals — ${item.use.toLowerCase()}, supplied in ${item.pack.toLowerCase()}.`}
            </p>
            <dl className="mt-8 grid gap-4 border-y border-[var(--line)] py-6 sm:grid-cols-2">
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Pack
                </dt>
                <dd className="mt-1.5 text-[15px] font-medium text-[var(--ink)]">
                  {item.pack}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Use
                </dt>
                <dd className="mt-1.5 text-[15px] font-medium text-[var(--ink)]">
                  {item.use}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Origin
                </dt>
                <dd className="mt-1.5 text-[15px] font-medium text-[var(--ink)]">
                  Gujrat, Pakistan
                </dd>
              </div>
              <div>
                <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Platform
                </dt>
                <dd className="mt-1.5 text-[15px] font-medium text-[var(--ink)]">
                  {family.name}
                </dd>
              </div>
            </dl>
            <div className="mt-8 flex flex-col gap-4">
              <div className="flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap">
                <AddToQuoteButton slug={item.slug} className="btn btn-accent" />
                <a
                  href={`${contact.whatsapp}?text=${encodeURIComponent(
                    `Hello — I am interested in ${item.name} from IFS Chemicals.`,
                  )}`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-outline w-full sm:w-auto"
                >
                  WhatsApp inquiry
                </a>
              </div>
              <p className="text-sm text-[var(--muted)]">
                No online checkout. Add SKUs to a quote list and our commercial
                team will respond with pricing.
              </p>
            </div>
          </div>
        </div>

        {related.length > 0 ? (
          <section className="mt-20 border-t border-[var(--line)] pt-14">
            <p className="eyebrow">Related</p>
            <h2 className="font-display mt-3 text-2xl font-semibold text-[var(--ink)]">
              More in {family.name}
            </h2>
            <div className="mt-8 grid gap-5 sm:grid-cols-3">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={`/products/${r.slug}`}
                  className="group surface-card overflow-hidden transition hover:-translate-y-0.5"
                >
                  <div className="img-well relative aspect-[5/4] overflow-hidden">
                    <Image
                      src={r.image}
                      alt={r.name}
                      fill
                      className="object-contain p-6 transition duration-500 group-hover:scale-[1.03]"
                      sizes="(max-width: 640px) 100vw, 33vw"
                    />
                  </div>
                  <div className="border-t border-[var(--line)] px-4 py-4">
                    <h3 className="font-display text-base font-semibold text-[var(--ink)] group-hover:text-[var(--blue)]">
                      {r.name}
                    </h3>
                  </div>
                </Link>
              ))}
            </div>
            <Link
              href={`/products/${family.slug}`}
              className="mt-8 inline-block text-sm font-semibold text-[var(--blue)] transition hover:underline"
            >
              View full {family.name} platform →
            </Link>
          </section>
        ) : null}

        <DistributorCta />
      </div>
    </div>
  );
}
