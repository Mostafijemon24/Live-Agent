import type { Metadata } from "next";
import { Suspense } from "react";
import { OnboardingScreen } from "@/features/onboarding/OnboardingScreen";

export const metadata: Metadata = { title: "Set up your workspace — Steward" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <OnboardingScreen />
    </Suspense>
  );
}
