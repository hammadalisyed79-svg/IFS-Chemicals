export type GtagFn = (
  command: "config" | "event" | "js",
  targetOrAction: string | Date,
  params?: Record<string, string | number | boolean>,
) => void;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: GtagFn;
  }
}

export function trackEvent(
  name: string,
  params?: Record<string, string | number | boolean>,
) {
  if (typeof window === "undefined" || typeof window.gtag !== "function") return;
  window.gtag("event", name, params);
}
