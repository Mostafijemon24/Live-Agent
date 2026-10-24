import type { Metadata } from "next";
import { Suspense } from "react";
import { RegisterScreen } from "@/features/auth/RegisterScreen";

export const metadata: Metadata = { title: "Create your workspace — Steward" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <RegisterScreen />
    </Suspense>
  );
}
