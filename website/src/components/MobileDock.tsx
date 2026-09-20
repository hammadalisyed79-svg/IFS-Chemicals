"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuote } from "@/components/QuoteProvider";

const items = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/products", label: "Catalogue", icon: GridIcon },
  { href: "/quote", label: "Quote", icon: QuoteIcon, badge: true },
  { href: "/contact", label: "Contact", icon: ContactIcon },
] as const;

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" aria-hidden>
      <path
        d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z"
        stroke="currentColor"
        strokeWidth={active ? 1.7 : 1.45}
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GridIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" aria-hidden>
      <path
        d="M5 5h6v6H5V5Zm8 0h6v6h-6V5ZM5 13h6v6H5v-6Zm8 0h6v6h-6v-6Z"
        stroke="currentColor"
        strokeWidth={active ? 1.7 : 1.45}
      />
    </svg>
  );
}

function QuoteIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" aria-hidden>
      <path
        d="M8 7h8v2H8V7Zm0 4h8v2H8v-2Zm0 4h5v2H8v-2Z"
        stroke="currentColor"
        strokeWidth={active ? 1.7 : 1.45}
        strokeLinejoin="round"
      />
      <path
        d="M5 5h14v14H5V5Z"
        stroke="currentColor"
        strokeWidth={active ? 1.7 : 1.45}
      />
    </svg>
  );
}

function ContactIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" aria-hidden>
      <path
        d="M7.5 4.5h3l1.1 3-1.7 1.7a11.5 11.5 0 0 0 5 5l1.7-1.7 3 1.1v3A1.8 1.8 0 0 1 18 18.4 13.8 13.8 0 0 1 5.6 6a1.8 1.8 0 0 1 1.9-1.5Z"
        stroke="currentColor"
        strokeWidth={active ? 1.7 : 1.45}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function MobileDock() {
  const pathname = usePathname();
  const { count, ready } = useQuote();

  if (pathname?.startsWith("/admin")) return null;

  return (
    <nav aria-label="Primary mobile" className="mobile-dock md:hidden">
      <div className="mobile-dock-inner">
        {items.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : Boolean(pathname?.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`mobile-dock-item ${active ? "is-active" : ""}`}
            >
              <span className="relative inline-flex">
                <Icon active={active} />
                {"badge" in item && item.badge && ready && count > 0 ? (
                  <span className="mobile-dock-badge">
                    {count > 9 ? "9+" : count}
                  </span>
                ) : null}
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
