import type { Metadata } from "next";
import { Outfit, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";

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

export const metadata: Metadata = {
  title: {
    default: "IFS Chemicals — Innovative Future Solutions",
    template: "%s · IFS Chemicals",
  },
  description:
    "Leading manufacturer of detergent powders, dishwash & toilet cleaners, bars & oil, and packaging materials in Gujrat, Pakistan.",
  metadataBase: new URL("https://ifschemicals.com"),
  openGraph: {
    title: "IFS Chemicals — Innovative Future Solutions",
    description:
      "High-quality cleaning solutions and packaging materials from Gujrat, Pakistan.",
    url: "https://ifschemicals.com",
    siteName: "IFS Chemicals",
    type: "website",
    images: [{ url: "/images/hero/products-showcase.jpg" }],
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
        <SiteHeader />
        <main>{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
