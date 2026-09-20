"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuote } from "@/components/QuoteProvider";

const items = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/products", label: "Products", icon: GridIcon },
  { href: "/quote", label: "Quote", icon: QuoteIcon, badge: true },
  { href: "/contact", label: "Contact", icon: ContactIcon },
] as const;

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
      <path
        d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z"
        stroke="currentColor"
        strokeWidth={active ? 1.8 : 1.5}
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GridIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
      <path
        d="M5 5h6v6H5V5Zm8 0h6v6h-6V5ZM5 13h6v6H5v-6Zm8 0h6v6h-6v-6Z"
        stroke="currentColor"
        strokeWidth={active ? 1.8 : 1.5}
      />
    </svg>
  );
}

function QuoteIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
      <path
        d="M7 7h10v10H7V7Zm3 13h4M9 4h6"
        stroke="currentColor"
        strokeWidth={active ? 1.8 : 1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ContactIcon({ active }: { active: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
      <path
        d="M5 6.5A1.5 1.5 0 0 1 6.5 5h11A1.5 1.5 0 0 1 19 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 17.5v-11Z"
        stroke="currentColor"
        strokeWidth={active ? 1.8 : 1.5}
      />
      <path
        d="M8 9h8M8 12h8M8 15h5"
        stroke="currentColor"
        strokeWidth={active ? 1.8 : 1.5}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function MobileDock() {
  const pathname = usePathname();
  const { count, ready } = useQuote();

  if (pathname?.startsWith("/admin")) return null;

  return (
    <nav
      aria-label="Primary mobile"
      className="mobile-dock md:hidden"
    >
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
              <span className="relative">
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
