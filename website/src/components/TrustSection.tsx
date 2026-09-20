import Image from "next/image";
import Link from "next/link";
import { contact } from "@/lib/content";
import { mapsSearchUrl, trustPillars } from "@/lib/seo";

const gallery = [
  {
    src: "/images/factory.jpg",
    alt: "IFS Chemicals manufacturing facility in Gujrat",
    label: "Plant",
  },
  {
    src: "/images/pet-blowing.jpg",
    alt: "PET bottle blowing equipment",
    label: "PET blowing",
  },
  {
    src: "/images/about-team.jpg",
    alt: "IFS Chemicals operations",
    label: "Operations",
  },
  {
    src: "/images/packaging.jpg",
    alt: "Flexible packaging production",
    label: "Packaging",
  },
] as const;

export function TrustSection() {
  return (
    <section className="border-y border-[var(--line)] bg-white">
      <div className="mx-auto max-w-6xl px-5 py-16 md:px-8 md:py-24">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-[0.22em] text-[#c41e26]">
            Trust & manufacturing
          </p>
          <h2 className="font-display mt-3 text-3xl font-bold tracking-tight text-[var(--ink)] md:text-5xl">
            Built in Gujrat. Supplied nationwide.
          </h2>
          <p className="mt-4 text-base leading-relaxed text-[var(--muted)] md:text-lg">
            From detergent powder to finished packaging, IFS Chemicals runs
            manufacturing at {contact.address} — Made in Pakistan for domestic and
            commercial partners.
          </p>
        </div>

        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {gallery.map((shot) => (
            <figure key={shot.src} className="group relative aspect-[4/3] overflow-hidden bg-[#e8edf3]">
              <Image
                src={shot.src}
                alt={shot.alt}
                fill
                className="object-cover transition duration-500 group-hover:scale-[1.03]"
                sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
              />
              <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#071833]/85 to-transparent px-3 pb-3 pt-10 text-xs font-semibold uppercase tracking-[0.14em] text-white">
                {shot.label}
              </figcaption>
            </figure>
          ))}
        </div>

        <div className="mt-12 grid gap-8 md:grid-cols-3">
          {trustPillars.map((p) => (
            <div key={p.title}>
              <span className="mb-3 block h-1 w-8 bg-[#0b5ea8]" />
              <h3 className="font-display text-lg font-bold text-[var(--ink)]">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border border-[var(--line)] bg-[var(--paper)] px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div>
            <p className="font-display text-lg font-bold text-[var(--ink)]">
              Find us on the map
            </p>
            <p className="mt-1 text-sm text-[var(--muted)]">{contact.address}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a
              href={mapsSearchUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex bg-[#071833] px-5 py-3 text-sm font-bold uppercase tracking-[0.08em] text-white hover:bg-[#0b5ea8]"
            >
              Open in Google Maps
            </a>
            <Link
              href="/about"
              className="inline-flex border border-[var(--line)] bg-white px-5 py-3 text-sm font-semibold uppercase tracking-[0.08em] text-[var(--ink)] hover:border-[#071833]"
            >
              About IFS
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
