import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { SettingsPage } from "@/features/settings/SettingsPage";

export const metadata: Metadata = { title: "Settings — Steward" };

export default function Page() {
  return (
    <Suspense fallback={<Skeleton />}>
      <SettingsPage />
    </Suspense>
  );
}
