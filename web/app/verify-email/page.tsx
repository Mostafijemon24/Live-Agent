import type { Metadata } from "next";
import { Suspense } from "react";
import { VerifyEmailScreen } from "@/features/auth/VerifyEmailScreen";

export const metadata: Metadata = { title: "Verify your email — Steward" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailScreen />
    </Suspense>
  );
}
