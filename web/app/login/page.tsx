import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginScreen } from "@/features/auth/LoginScreen";

export const metadata: Metadata = { title: "Sign in — Steward" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <LoginScreen />
    </Suspense>
  );
}
