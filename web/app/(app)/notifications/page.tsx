import type { Metadata } from "next";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";

export const metadata: Metadata = { title: "Notifications — Steward" };

export default function Page() {
  return <NotificationsPage />;
}
