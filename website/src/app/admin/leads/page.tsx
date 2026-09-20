import type { Metadata } from "next";
import { LeadsInbox } from "@/components/LeadsInbox";

export const metadata: Metadata = {
  title: "Leads inbox",
  robots: { index: false, follow: false },
};

export default function AdminLeadsPage() {
  return (
    <div className="min-h-[70vh] bg-[var(--paper)]">
      <div className="container-site py-12 md:py-16">
        <LeadsInbox />
      </div>
    </div>
  );
}
