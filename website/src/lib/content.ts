export const brand = {
  name: "IFS Chemicals",
  tagline: "Innovative Future Solutions",
  short:
    "Manufacturer of cleaning solutions and packaging systems for retail and professional markets.",
};

export type CatalogItem = {
  name: string;
  image: string;
  pack: string;
  use: string;
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
      {
        name: "Detergent Base Powder",
        image: "/images/products/detergent-base.jpg",
        pack: "Industrial bulk sacks",
        use: "B2B / reformulation base",
      },
      {
        name: "Happy Detergent Powder",
        image: "/images/products/happy-detergent.jpg",
        pack: "Retail pouches",
        use: "Household laundry",
      },
      {
        name: "JagMag Detergent Powder",
        image: "/images/products/jagmag.jpg",
        pack: "Retail pouches",
        use: "Everyday wash & brightness",
      },
      {
        name: "Lashkara Detergent Powder",
        image: "/images/products/lashkara.jpg",
        pack: "Retail pouches",
        use: "Tough stain removal",
      },
      {
        name: "Train Detergent Powder",
        image: "/images/products/train-detergent.jpg",
        pack: "Retail pouches",
        use: "Domestic & commercial laundry",
      },
    ],
  },
  {
    slug: "bars-oil",
    name: "Bars & Oil",
    blurb: "Suitable for domestic and commercial use — dishwash bars, detergent bars, and cooking oil.",
    image: "/images/products/happy-bar.jpg",
    items: [
      {
        name: "Bahar Rapeseed Oil",
        image: "/images/products/bahar-oil.jpg",
        pack: "Bottles & bulk",
        use: "Cooking / kitchen",
      },
      {
        name: "Happy Dishwash & Detergent Bar",
        image: "/images/products/happy-bar.jpg",
        pack: "Bar packs",
        use: "Utensils & laundry bar",
      },
      {
        name: "Ring Dishwash Bar",
        image: "/images/products/ring-bar.jpg",
        pack: "Bar packs",
        use: "Kitchen dishwash",
      },
      {
        name: "Train Dishwash Bar",
        image: "/images/products/train-bar.jpg",
        pack: "Bar packs",
        use: "Domestic & commercial kitchens",
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
        name: "Bahar Dishwash Liquid",
        image: "/images/products/bahar-dishwash.jpg",
        pack: "Bottles & refill pouches",
        use: "Kitchen grease cutting",
      },
      {
        name: "Bahar Toilet Cleaner",
        image: "/images/products/bahar-toilet.jpg",
        pack: "Bottles",
        use: "Bathroom hygiene",
      },
      {
        name: "Happy Dishwash Liquid",
        image: "/images/products/happy-dishwash.jpg",
        pack: "Bottles & refill pouches",
        use: "Everyday dishwash",
      },
      {
        name: "Happy Toilet Cleaner",
        image: "/images/products/happy-toilet.jpg",
        pack: "Bottles",
        use: "Toilet & ceramic clean",
      },
    ],
  },
  {
    slug: "flexible-packaging",
    name: "Flexible Packaging",
    blurb: "Custom flexible packaging with durable laminates and print-ready finishes for brand owners.",
    image: "/images/packaging.jpg",
    items: [
      {
        name: "Pouches",
        image: "/images/packaging.jpg",
        pack: "Custom sizes",
        use: "Retail & industrial fill",
      },
      {
        name: "Laminates",
        image: "/images/packaging.jpg",
        pack: "Rolls / sheets",
        use: "Barrier & print layers",
      },
      {
        name: "Printed rolls",
        image: "/images/packaging.jpg",
        pack: "Printed film rolls",
        use: "Brand packaging lines",
      },
    ],
  },
  {
    slug: "corrugated",
    name: "Corrugated Box",
    blurb: "Protective corrugated packaging for shipping, retail, and industrial supply.",
    image: "/images/corrugated.jpg",
    items: [
      {
        name: "Shippers",
        image: "/images/corrugated.jpg",
        pack: "Multi-ply cartons",
        use: "Transit protection",
      },
      {
        name: "Retail cartons",
        image: "/images/corrugated.jpg",
        pack: "Shelf-ready boxes",
        use: "Retail display & pack",
      },
      {
        name: "Custom die-cuts",
        image: "/images/corrugated.jpg",
        pack: "Die-cut to order",
        use: "Brand-fit packaging",
      },
    ],
  },
  {
    slug: "pet-bottle",
    name: "PET Bottle Blowing",
    blurb: "PET bottle blowing for liquid household and commercial products.",
    image: "/images/pet-blowing.jpg",
    items: [
      {
        name: "Standard necks",
        image: "/images/pet-blowing.jpg",
        pack: "Common neck finishes",
        use: "Liquids & cleaners",
      },
      {
        name: "Custom profiles",
        image: "/images/pet-blowing.jpg",
        pack: "Custom bottle shapes",
        use: "Private-label brands",
      },
      {
        name: "Bulk supply",
        image: "/images/pet-blowing.jpg",
        pack: "Volume production",
        use: "OEM / contract fill",
      },
    ],
  },
];

export const highlights = [
  "Fully automated manufacturing with process control",
  "Formulated for efficient, consistent cleaning performance",
  "Supply programmes for retail and professional buyers",
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
