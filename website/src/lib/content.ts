export const brand = {
  name: "IFS Chemicals",
  tagline: "Innovative Future Solutions",
  short:
    "A leading manufacturer of high-quality cleaning solutions and packaging materials.",
};

export type CatalogItem = {
  name: string;
  image: string;
};

export type ProductFamily = {
  slug: string;
  name: string;
  blurb: string;
  image: string;
  items: CatalogItem[];
};

export const products: ProductFamily[] = [
  {
    slug: "detergent-powder",
    name: "Detergent Powder",
    blurb:
      "Manufactured on a fully automated imported detergent powder plant for domestic and commercial laundry.",
    image: "/images/products/happy-detergent.jpg",
    items: [
      { name: "Detergent Base Powder", image: "/images/products/detergent-base.jpg" },
      { name: "Happy Detergent Powder", image: "/images/products/happy-detergent.jpg" },
      { name: "JagMag Detergent Powder", image: "/images/products/jagmag.jpg" },
      { name: "Lashkara Detergent Powder", image: "/images/products/lashkara.jpg" },
      { name: "Train Detergent Powder", image: "/images/products/train-detergent.jpg" },
    ],
  },
  {
    slug: "bars-oil",
    name: "Bars & Oil",
    blurb: "Suitable for domestic and commercial use — dishwash bars, detergent bars, and cooking oil.",
    image: "/images/products/happy-bar.jpg",
    items: [
      { name: "Bahar Rapeseed Oil", image: "/images/products/bahar-oil.jpg" },
      { name: "Happy Dishwash & Detergent Bar", image: "/images/products/happy-bar.jpg" },
      { name: "Ring Dishwash Bar", image: "/images/products/ring-bar.jpg" },
      { name: "Train Dishwash Bar", image: "/images/products/train-bar.jpg" },
    ],
  },
  {
    slug: "dishwash-toilet",
    name: "Dishwash Liquid & Toilet Cleaner",
    blurb: "Concentrated formulas for efficient cleaning and everyday hygiene.",
    image: "/images/products/bahar-dishwash.jpg",
    items: [
      { name: "Bahar Dishwash Liquid", image: "/images/products/bahar-dishwash.jpg" },
      { name: "Bahar Toilet Cleaner", image: "/images/products/bahar-toilet.jpg" },
      { name: "Happy Dishwash Liquid", image: "/images/products/happy-dishwash.jpg" },
      { name: "Happy Toilet Cleaner", image: "/images/products/happy-toilet.jpg" },
    ],
  },
  {
    slug: "flexible-packaging",
    name: "Flexible Packaging",
    blurb: "Custom flexible packaging with durable laminates and print-ready finishes for brand owners.",
    image: "/images/packaging.jpg",
    items: [
      { name: "Pouches", image: "/images/packaging.jpg" },
      { name: "Laminates", image: "/images/packaging.jpg" },
      { name: "Printed rolls", image: "/images/packaging.jpg" },
    ],
  },
  {
    slug: "corrugated",
    name: "Corrugated Box",
    blurb: "Protective corrugated packaging for shipping, retail, and industrial supply.",
    image: "/images/corrugated.jpg",
    items: [
      { name: "Shippers", image: "/images/corrugated.jpg" },
      { name: "Retail cartons", image: "/images/corrugated.jpg" },
      { name: "Custom die-cuts", image: "/images/corrugated.jpg" },
    ],
  },
  {
    slug: "pet-bottle",
    name: "PET Bottle Blowing",
    blurb: "PET bottle blowing for liquid household and commercial products.",
    image: "/images/pet-blowing.jpg",
    items: [
      { name: "Standard necks", image: "/images/pet-blowing.jpg" },
      { name: "Custom profiles", image: "/images/pet-blowing.jpg" },
      { name: "Bulk supply", image: "/images/pet-blowing.jpg" },
    ],
  },
];

export const highlights = [
  "Fully automated plant-based manufacturing",
  "Concentrated formulas for efficient cleaning",
  "Suitable for domestic & commercial use",
] as const;

export const contact = {
  phone: "+92 321 6001040",
  phoneHref: "tel:+923216001040",
  whatsapp: "https://wa.me/923216001040",
  emails: ["ifschemicals@outlook.com", "info@ifschemicals.com"],
  address: "Bridge Canal Saroki, Gujrat, Pakistan",
  erpUrl: "https://erp.ifschemicals.com/",
  social: {
    facebook: "https://www.facebook.com/",
    linkedin: "https://www.linkedin.com/",
    instagram: "https://www.instagram.com/",
  },
};
