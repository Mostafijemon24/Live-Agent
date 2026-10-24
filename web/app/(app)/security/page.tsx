import type { Metadata } from "next";
import { SecurityPage } from "@/features/security/SecurityPage";

export const metadata: Metadata = { title: "Security & Privacy — Steward" };

export default function Page() {
  return <SecurityPage />;
}
