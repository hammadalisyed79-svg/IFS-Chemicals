import Image from "next/image";
import Link from "next/link";
import { contact } from "@/lib/content";
import { mapsSearchUrl, trustPillars } from "@/lib/seo";

const gallery = [
  {
    src: "/images/factory.jpg",
    alt: "IFS Chemicals manufacturing facility in Gujrat",
    label: "Production facility",
  },
  {
    src: "/images/products/pet-bottle.jpg",
    alt: "PET bottle blowing process",
    label: "PET systems",
  },
  {
    src: "/images/about-team.jpg",
    alt: "IFS Chemicals operations",
    label: "Operations",
  },
  {
    src: "/images/products/flexible-packaging.jpg",
    alt: "Flexible packaging formats",
    label: "Packaging lines",
  },
  {
    src: "/images/products/corrugated-box.jpg",
    alt: "Corrugated box styles",
    label: "Corrugated cartons",
  },
] as const;

export function TrustSection() {
  return (
    <section className="border-y border-[var(--line)] bg-white">
      <div className="container-site py-20 md:py-28">
        <div className="max-w-2xl">
          <p className="eyebrow">Operations</p>
          <h2 className="font-display mt-3 text-3xl font-semibold text-[var(--ink)] md:text-5xl">
            Built in Gujrat. Delivered with consistency.
          </h2>
          <p className="lead mt-4">
            Our manufacturing base at {contact.address} supports national
            distribution with controlled production and packaging capability.
          </p>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {gallery.map((shot) => (
            <figure
              key={shot.src}
              className="group relative aspect-[4/5] overflow-hidden bg-[var(--paper-2)]"
            >
              <Image
                src={shot.src}
                alt={shot.alt}
                fill
                className="object-contain p-3 transition duration-700 group-hover:scale-[1.02]"
                sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 25vw"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-[var(--navy)]/80 via-transparent to-transparent" />
              <figcaption className="absolute inset-x-0 bottom-0 px-4 pb-4 text-[12px] font-medium tracking-[0.08em] text-white">
                {shot.label}
              </figcaption>
            </figure>
          ))}
        </div>

        <div className="mt-14 grid gap-10 border-t border-[var(--line)] pt-12 md:grid-cols-3 md:gap-8">
          {trustPillars.map((p, i) => (
            <div key={p.title}>
              <p className="text-[11px] font-semibold tracking-[0.16em] text-[var(--muted)]">
                0{i + 1}
              </p>
              <h3 className="font-display mt-3 text-lg font-semibold text-[var(--ink)]">
                {p.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{p.body}</p>
            </div>
          ))}
        </div>

        <div className="surface-card mt-14 flex flex-col gap-5 px-6 py-7 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div>
            <p className="font-display text-lg font-semibold text-[var(--ink)]">
              Visit our location
            </p>
            <p className="mt-1 text-sm text-[var(--muted)]">{contact.address}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a
              href={mapsSearchUrl}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary"
            >
              Open in Google Maps
            </a>
            <Link href="/about" className="btn btn-outline">
              Company profile
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
