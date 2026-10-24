import type { Metadata } from "next";
import { StatesPage } from "@/features/states/StatesPage";

export const metadata: Metadata = { title: "System states — Steward" };

export default function Page() {
  return <StatesPage />;
}
