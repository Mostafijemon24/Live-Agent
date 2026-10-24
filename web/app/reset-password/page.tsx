import type { Metadata } from "next";
import { Suspense } from "react";
import { ResetPasswordScreen } from "@/features/auth/ResetPasswordScreen";

export const metadata: Metadata = { title: "Choose a new password — Steward" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordScreen />
    </Suspense>
  );
}
