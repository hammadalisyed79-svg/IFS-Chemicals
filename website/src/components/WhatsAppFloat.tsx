import { contact } from "@/lib/content";

export function WhatsAppFloat() {
  const href = `${contact.whatsapp}?text=${encodeURIComponent(
    "Hello — I would like product or distributor information from IFS Chemicals.",
  )}`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label="Chat on WhatsApp"
      className="wa-float fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-[max(1.25rem,env(safe-area-inset-right))] z-50 hidden h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-lg shadow-black/25 transition hover:scale-105 hover:bg-[#1ebe57] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#25D366] md:flex"
    >
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
        <path
          fill="currentColor"
          d="M19.11 17.43c-.28-.14-1.64-.81-1.9-.9-.25-.1-.44-.14-.62.14-.18.28-.71.9-.87 1.08-.16.18-.32.2-.6.07-.28-.14-1.17-.43-2.23-1.37-.82-.73-1.38-1.64-1.54-1.92-.16-.28-.02-.43.12-.57.13-.13.28-.32.42-.48.14-.16.18-.28.28-.46.09-.18.05-.35-.02-.49-.07-.14-.62-1.49-.85-2.04-.22-.53-.45-.46-.62-.47h-.53c-.18 0-.48.07-.73.35-.25.28-.96.94-.96 2.3s.98 2.67 1.12 2.85c.14.18 1.93 2.95 4.68 4.13.65.28 1.16.45 1.56.57.65.21 1.25.18 1.72.11.52-.08 1.64-.67 1.87-1.32.23-.65.23-1.2.16-1.32-.07-.11-.25-.18-.53-.32z"
        />
        <path
          fill="currentColor"
          d="M16.02 3C9.4 3 4.03 8.36 4.03 14.98c0 2.1.55 4.15 1.6 5.96L4 28l7.25-1.9a12 12 0 0 0 4.77.98h.01c6.62 0 11.99-5.36 11.99-11.98C28.02 8.36 22.65 3 16.02 3zm0 21.82h-.01a9.8 9.8 0 0 1-5-.137l-.36-.21-4.3 1.13 1.15-4.19-.23-.37a9.82 9.82 0 0 1-1.5-5.24c0-5.43 4.42-9.85 9.86-9.85 5.43 0 9.85 4.42 9.85 9.85 0 5.43-4.42 9.85-9.85 9.85z"
        />
      </svg>
    </a>
  );
}
