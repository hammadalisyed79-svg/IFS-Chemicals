import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { WhatsAppFloat } from "@/components/WhatsAppFloat";
import { JsonLd } from "@/components/JsonLd";
import { QuoteProvider } from "@/components/QuoteProvider";
import { Analytics } from "@/components/Analytics";
import { MobileDock } from "@/components/MobileDock";
import { defaultOgImage, siteUrl } from "@/lib/seo";

const display = Archivo({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700"],
});

const body = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: "#0a1628",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "IFS Chemicals — Innovative Future Solutions",
    template: "%s · IFS Chemicals",
  },
  description:
    "IFS Chemicals manufactures detergent powders, hygiene care products, and packaging systems for retail brands, distributors, and professional buyers.",
  keywords: [
    "IFS Chemicals",
    "Innovative Future Solutions",
    "detergent powder Pakistan",
    "Happy detergent",
    "Train detergent",
    "dishwash liquid",
    "flexible packaging",
    "PET bottle blowing",
    "corrugated packaging",
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
    title: "IFS Chemicals — Innovative Future Solutions",
    description:
      "Cleaning formulations and packaging systems for retail and professional markets.",
    url: siteUrl,
    siteName: "IFS Chemicals",
    type: "website",
    locale: "en_PK",
    images: [defaultOgImage],
  },
  twitter: {
    card: "summary_large_image",
    title: "IFS Chemicals — Innovative Future Solutions",
    description:
      "Detergent powders, hygiene care, and packaging systems for commercial buyers.",
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
        <Analytics />
        <QuoteProvider>
          <JsonLd />
          <SiteHeader />
          <main className="pb-2 md:pb-0">{children}</main>
          <SiteFooter />
          <WhatsAppFloat />
          <MobileDock />
        </QuoteProvider>
      </body>
    </html>
  );
}
