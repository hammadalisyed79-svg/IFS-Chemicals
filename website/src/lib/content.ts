export const brand = {
  name: "IFS Chemicals",
  tagline: "Innovative Future Solutions",
  short:
    "Industrial manufacturer of cleaning formulations and packaging systems for retail and professional markets.",
};

export type CatalogItem = {
  slug: string;
  name: string;
  image: string;
  pack: string;
  use: string;
  summary?: string;
};

export type ProductFamily = {
  slug: string;
  name: string;
  blurb: string;
  image: string;
  /** Extra gallery images for packaging / plant capability pages */
  gallery?: { src: string; alt: string; label: string }[];
  items: CatalogItem[];
};

export const products: ProductFamily[] = [
  {
    slug: "detergent-powder",
    name: "Detergent Powder",
    blurb:
      "Produced on a fully automated detergent powder plant for domestic and commercial laundry applications.",
    image: "/images/products/happy-detergent.jpg",
    items: [
      {
        slug: "detergent-base-powder",
        name: "Detergent Base Powder",
        image: "/images/products/detergent-base.jpg",
        pack: "Industrial bulk sacks",
        use: "B2B / reformulation base",
        summary:
          "Industrial base powder for reformulation and private-label programmes requiring consistent bulk supply.",
      },
      {
        slug: "lighter-density-base-powder",
        name: "Lighter Density Base Powder",
        image: "/images/products/lighter-density-base-powder.png",
        pack: "Industrial bulk sacks",
        use: "B2B / spray-dry grade base",
        summary:
          "Lighter-density detergent base powder for reformulation and private-label programmes that require free-flowing bulk characteristics.",
      },
      {
        slug: "happy-detergent",
        name: "Happy Detergent Powder",
        image: "/images/products/happy-detergent.jpg",
        pack: "Retail pouches",
        use: "Household laundry",
        summary:
          "Household laundry detergent manufactured for everyday wash performance and retail distribution.",
      },
      {
        slug: "jagmag-detergent",
        name: "JagMag Detergent Powder",
        image: "/images/products/jagmag.jpg",
        pack: "Retail pouches",
        use: "Everyday wash & brightness",
        summary:
          "Everyday detergent powder formulated for wash performance and brightness in domestic laundry.",
      },
      {
        slug: "lashkara-detergent",
        name: "Lashkara Detergent Powder",
        image: "/images/products/lashkara.jpg",
        pack: "Retail pouches",
        use: "Tough stain removal",
        summary:
          "Detergent powder positioned for tougher soil and stain removal in household laundry routines.",
      },
      {
        slug: "train-detergent",
        name: "Train Detergent Powder",
        image: "/images/products/train-detergent.jpg",
        pack: "Retail pouches",
        use: "Domestic & commercial laundry",
        summary:
          "Laundry detergent suited to domestic and light commercial wash applications.",
      },
    ],
  },
  {
    slug: "bars-oil",
    name: "Bars & Oil",
    blurb:
      "Suitable for domestic and commercial use — dishwash bars, detergent bars, and cooking oil.",
    image: "/images/products/happy-bar.jpg",
    items: [
      {
        slug: "bahar-rapeseed-oil",
        name: "Bahar Rapeseed Oil",
        image: "/images/products/bahar-oil.jpg",
        pack: "Bottles & bulk",
        use: "Cooking / kitchen",
        summary: "Cooking oil available in retail bottles and bulk formats for kitchen and commercial use.",
      },
      {
        slug: "happy-dishwash-bar",
        name: "Happy Dishwash & Detergent Bar",
        image: "/images/products/happy-bar.jpg",
        pack: "Bar packs",
        use: "Utensils & laundry bar",
        summary: "Dual-purpose bar for utensil cleaning and laundry applications.",
      },
      {
        slug: "ring-dishwash-bar",
        name: "Ring Dishwash Bar",
        image: "/images/products/ring-bar.jpg",
        pack: "Bar packs",
        use: "Kitchen dishwash",
        summary: "Kitchen dishwash bar for everyday utensil cleaning.",
      },
      {
        slug: "train-dishwash-bar",
        name: "Train Dishwash Bar",
        image: "/images/products/train-bar.jpg",
        pack: "Bar packs",
        use: "Domestic & commercial kitchens",
        summary: "Dishwash bar for domestic and commercial kitchen use.",
      },
    ],
  },
  {
    slug: "dishwash-toilet",
    name: "Dishwash Liquid & Toilet Cleaner",
    blurb: "Concentrated formulas for efficient cleaning and everyday hygiene.",
    image: "/images/products/bahar-dishwash.jpg",
    items: [
      {
        slug: "bahar-dishwash-liquid",
        name: "Bahar Dishwash Liquid",
        image: "/images/products/bahar-dishwash.jpg",
        pack: "Bottles & refill pouches",
        use: "Kitchen grease cutting",
        summary: "Concentrated dishwash liquid for kitchen grease cutting and everyday utensil care.",
      },
      {
        slug: "bahar-toilet-cleaner",
        name: "Bahar Toilet Cleaner",
        image: "/images/products/bahar-toilet.jpg",
        pack: "Bottles",
        use: "Bathroom hygiene",
        summary: "Toilet cleaner formulated for bathroom hygiene and ceramic surfaces.",
      },
      {
        slug: "happy-dishwash-liquid",
        name: "Happy Dishwash Liquid",
        image: "/images/products/happy-dishwash.jpg",
        pack: "Bottles & refill pouches",
        use: "Everyday dishwash",
        summary: "Everyday dishwash liquid for household kitchens and retail distribution.",
      },
      {
        slug: "happy-toilet-cleaner",
        name: "Happy Toilet Cleaner",
        image: "/images/products/happy-toilet.jpg",
        pack: "Bottles",
        use: "Toilet & ceramic clean",
        summary: "Toilet and ceramic cleaner for routine bathroom maintenance.",
      },
    ],
  },
  {
    slug: "flexible-packaging",
    name: "Flexible Packaging",
    blurb:
      "Custom flexible packaging with durable laminates and print-ready finishes for brand owners.",
    image: "/images/products/flexible-packaging.jpg",
    gallery: [
      {
        src: "/images/products/flexible-packaging.jpg",
        alt: "Packaging film rolls for flexible packaging",
        label: "Film rolls",
      },
      {
        src: "/images/products/flex-gallery-capability.jpg",
        alt: "Film roll with finished stand-up pouches",
        label: "Film to pouch",
      },
      {
        src: "/images/factory.jpg",
        alt: "IFS Chemicals manufacturing facility",
        label: "Manufacturing facility",
      },
      {
        src: "/images/products/bahar-dishwash.jpg",
        alt: "Finished IFS liquid packs",
        label: "Finished packs",
      },
    ],
    items: [
      {
        slug: "flexible-pouches",
        name: "Pouches",
        image: "/images/products/flexible-pouches.jpg",
        pack: "Custom sizes",
        use: "Retail & industrial fill",
        summary:
          "Custom pouch formats for retail and industrial fill programmes with print-ready finishes.",
      },
      {
        slug: "flexible-laminates",
        name: "Laminates",
        image: "/images/products/flexible-laminates.jpg",
        pack: "Rolls / sheets",
        use: "Barrier & print layers",
        summary: "Laminate structures for barrier performance and brand print layers.",
      },
      {
        slug: "printed-rolls",
        name: "Printed rolls",
        image: "/images/products/printed-rolls.jpg",
        pack: "Printed film rolls",
        use: "Brand packaging lines",
        summary: "Printed film rolls for continuous packaging and brand-owner lines.",
      },
    ],
  },
  {
    slug: "corrugated",
    name: "Corrugated Box",
    blurb: "Protective corrugated packaging for shipping, retail, and industrial supply.",
    image: "/images/products/corrugated-box.jpg",
    gallery: [
      {
        src: "/images/products/corrugated-box.jpg",
        alt: "Corrugated carton styles for shipping and retail",
        label: "Carton range",
      },
      {
        src: "/images/products/corrugated-gallery-warehouse.jpg",
        alt: "Stacked corrugated cartons in warehouse supply",
        label: "Volume supply",
      },
      {
        src: "/images/factory.jpg",
        alt: "IFS Chemicals manufacturing plant",
        label: "Plant",
      },
      {
        src: "/images/products/corrugated-shippers.jpg",
        alt: "Shipper cartons ready for transit",
        label: "Shippers",
      },
    ],
    items: [
      {
        slug: "corrugated-shippers",
        name: "Shippers",
        image: "/images/products/corrugated-shippers.jpg",
        pack: "Multi-ply cartons",
        use: "Transit protection",
        summary: "Multi-ply shipper cartons for transit protection across retail and industrial supply.",
      },
      {
        slug: "retail-cartons",
        name: "Retail cartons",
        image: "/images/products/retail-cartons.jpg",
        pack: "Shelf-ready boxes",
        use: "Retail display & pack",
        summary: "Shelf-ready retail cartons for display and secondary packaging.",
      },
      {
        slug: "custom-die-cuts",
        name: "Custom die-cuts",
        image: "/images/products/custom-die-cuts.jpg",
        pack: "Die-cut to order",
        use: "Brand-fit packaging",
        summary: "Custom die-cut corrugated formats fitted to brand and product requirements.",
      },
    ],
  },
  {
    slug: "pet-bottle",
    name: "PET Bottle Blowing",
    blurb: "PET bottle blowing for liquid household and commercial products.",
    image: "/images/products/pet-bottle.jpg",
    gallery: [
      {
        src: "/images/products/pet-bottle.jpg",
        alt: "PET bottle blow molding production",
        label: "Blow molding",
      },
      {
        src: "/images/products/pet-standard-necks.jpg",
        alt: "PET preforms and standard neck bottles",
        label: "Preform to bottle",
      },
      {
        src: "/images/factory.jpg",
        alt: "IFS manufacturing facility",
        label: "Facility",
      },
      {
        src: "/images/products/bahar-dishwash.jpg",
        alt: "Finished IFS liquid product packs",
        label: "Finished packs",
      },
    ],
    items: [
      {
        slug: "pet-standard-necks",
        name: "Standard necks",
        image: "/images/products/pet-standard-necks.jpg",
        pack: "Common neck finishes",
        use: "Liquids & cleaners",
        summary: "Standard PET neck finishes for liquid household and commercial products.",
      },
      {
        slug: "pet-custom-profiles",
        name: "Custom profiles",
        image: "/images/products/pet-custom-profiles.jpg",
        pack: "Custom bottle shapes",
        use: "Private-label brands",
        summary: "Custom PET bottle profiles for private-label and brand-differentiated packs.",
      },
      {
        slug: "pet-bulk-supply",
        name: "Bulk supply",
        image: "/images/products/pet-bulk-supply.jpg",
        pack: "Volume production",
        use: "OEM / contract fill",
        summary: "Volume PET bottle supply for OEM and contract-fill programmes.",
      },
    ],
  },
];

export const highlights = [
  "Automated production with disciplined process control",
  "Formulations engineered for consistent cleaning performance",
  "Commercial supply programmes for retail and professional buyers",
] as const;

export const contact = {
  phone: "+92 321 6001040",
  phoneHref: "tel:+923216001040",
  whatsapp: "https://wa.me/923216001040",
  emails: ["ifschemicals@outlook.com", "info@ifschemicals.com"],
  address: "Bridge Canal Saroki, Gujrat, Pakistan",
  erpUrl: "https://erp.ifschemicals.com/",
  social: {
    facebook: "https://www.facebook.com/ifschemicals/",
    instagram: "https://www.instagram.com/ifschemicals/",
    linkedin: "https://www.linkedin.com/in/hammad-syed-b877111a3",
  },
};

export type CatalogEntry =
  | { kind: "family"; family: ProductFamily }
  | { kind: "item"; family: ProductFamily; item: CatalogItem };

export function getCatalogEntry(slug: string): CatalogEntry | undefined {
  const family = products.find((p) => p.slug === slug);
  if (family) return { kind: "family", family };

  for (const f of products) {
    const item = f.items.find((i) => i.slug === slug);
    if (item) return { kind: "item", family: f, item };
  }
  return undefined;
}

export function allCatalogSlugs(): string[] {
  const slugs: string[] = [];
  for (const f of products) {
    slugs.push(f.slug);
    for (const i of f.items) slugs.push(i.slug);
  }
  return slugs;
}
