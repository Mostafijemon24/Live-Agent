import type { Metadata } from "next";
import { HelpPage } from "@/features/help/HelpPage";

export const metadata: Metadata = { title: "Help & Getting Started — Steward" };

export default function Page() {
  return <HelpPage />;
}
