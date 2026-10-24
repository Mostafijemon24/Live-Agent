import type { Metadata } from "next";
import { Suspense } from "react";
import { ForgotPasswordScreen } from "@/features/auth/ForgotPasswordScreen";

export const metadata: Metadata = { title: "Reset your password — Steward" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ForgotPasswordScreen />
    </Suspense>
  );
}
