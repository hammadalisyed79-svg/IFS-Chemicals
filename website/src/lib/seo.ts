import type { Metadata } from "next";
import { contact } from "@/lib/content";

export const siteUrl = "https://ifschemicals.com";

export const defaultOgImage = {
  url: "/images/og.jpg",
  width: 1200,
  height: 630,
  alt: "IFS Chemicals product range — Made in Gujrat, Pakistan",
};

export function pageMeta({
  title,
  description,
  path,
}: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  const url = `${siteUrl}${path}`;
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: `${title} · IFS Chemicals`,
      description,
      url,
      siteName: "IFS Chemicals",
      type: "website",
      locale: "en_PK",
      images: [defaultOgImage],
    },
    twitter: {
      card: "summary_large_image",
      title: `${title} · IFS Chemicals`,
      description,
      images: [defaultOgImage.url],
    },
  };
}

/** LocalBusiness + Organization for Google rich results */
export function localBusinessJsonLd() {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteUrl}/#organization`,
        name: "IFS Chemicals",
        legalName: "IFS Chemicals",
        alternateName: "Innovative Future Solutions",
        url: siteUrl,
        logo: `${siteUrl}/images/logo.png`,
        image: `${siteUrl}/images/og.jpg`,
        email: contact.emails[0],
        telephone: contact.phone,
        sameAs: [
          contact.social.facebook,
          contact.social.instagram,
          contact.social.linkedin,
        ],
        address: {
          "@type": "PostalAddress",
          streetAddress: "Bridge Canal Saroki",
          addressLocality: "Gujrat",
          addressRegion: "Punjab",
          addressCountry: "PK",
        },
      },
      {
        "@type": "LocalBusiness",
        "@id": `${siteUrl}/#localbusiness`,
        name: "IFS Chemicals",
        description:
          "Manufacturer of detergent powders, dishwash & toilet cleaners, bars & oil, and packaging materials in Gujrat, Pakistan.",
        url: siteUrl,
        image: [`${siteUrl}/images/factory.jpg`, `${siteUrl}/images/og.jpg`],
        telephone: contact.phone,
        email: contact.emails[0],
        priceRange: "$$",
        address: {
          "@type": "PostalAddress",
          streetAddress: "Bridge Canal Saroki",
          addressLocality: "Gujrat",
          addressRegion: "Punjab",
          addressCountry: "PK",
        },
        geo: {
          "@type": "GeoCoordinates",
          // Approximate Gujrat / Saroki industrial corridor — refine in Google Business
          latitude: 32.5731,
          longitude: 74.0789,
        },
        areaServed: {
          "@type": "Country",
          name: "Pakistan",
        },
        knowsAbout: [
          "Detergent powder manufacturing",
          "Dishwash liquid",
          "Toilet cleaner",
          "Flexible packaging",
          "Corrugated boxes",
          "PET bottle blowing",
        ],
        parentOrganization: { "@id": `${siteUrl}/#organization` },
      },
    ],
  };
}

export const mapsSearchUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
  contact.address,
)}`;

export const trustPillars = [
  {
    title: "Made in Gujrat, Pakistan",
    body: "Formulated and packed at Bridge Canal Saroki — supporting retail and professional buyers nationwide.",
  },
  {
    title: "Automated production",
    body: "Detergent powders manufactured on a fully automated imported plant with consistent quality control.",
  },
  {
    title: "End-to-end capability",
    body: "Cleaning lines plus flexible packaging, corrugated cartons, and PET blowing under one manufacturing group.",
  },
] as const;
