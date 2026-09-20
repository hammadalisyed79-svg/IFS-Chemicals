import type { Metadata, Viewport } from "next";
import { Outfit, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { WhatsAppFloat } from "@/components/WhatsAppFloat";
import { JsonLd } from "@/components/JsonLd";
import { defaultOgImage, siteUrl } from "@/lib/seo";

const display = Outfit({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700", "800"],
});

const body = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#071833",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "IFS Chemicals — Detergent & Packaging Manufacturer in Gujrat",
    template: "%s · IFS Chemicals",
  },
  description:
    "IFS Chemicals manufactures detergent powders, dishwash & toilet cleaners, bars & oil, flexible packaging, corrugated boxes, and PET bottles in Gujrat, Pakistan.",
  keywords: [
    "IFS Chemicals",
    "detergent powder Pakistan",
    "Gujrat manufacturer",
    "Happy detergent",
    "Train detergent",
    "dishwash liquid",
    "flexible packaging",
    "PET bottle blowing",
    "Made in Pakistan",
  ],
  authors: [{ name: "IFS Chemicals" }],
  creator: "IFS Chemicals",
  publisher: "IFS Chemicals",
  icons: {
    icon: [{ url: "/images/icon.png", type: "image/png" }],
    apple: [{ url: "/images/icon.png" }],
  },
  alternates: { canonical: siteUrl },
  openGraph: {
    title: "IFS Chemicals — Detergent & Packaging Manufacturer in Gujrat",
    description:
      "High-quality cleaning solutions and packaging materials from Gujrat, Pakistan. Made in Pakistan.",
    url: siteUrl,
    siteName: "IFS Chemicals",
    type: "website",
    locale: "en_PK",
    images: [defaultOgImage],
  },
  twitter: {
    card: "summary_large_image",
    title: "IFS Chemicals — Made in Gujrat, Pakistan",
    description:
      "Detergent powders, dishwash care, and packaging manufactured in Gujrat.",
    images: [defaultOgImage.url],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable} antialiased`}>
        <JsonLd />
        <SiteHeader />
        <main>{children}</main>
        <SiteFooter />
        <WhatsAppFloat />
      </body>
    </html>
  );
}
