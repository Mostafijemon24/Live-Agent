import type { Metadata, Viewport } from "next";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";
import { Providers } from "@/lib/session";
import { StatusStrip } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "Steward — AI agent workspace",
  description: "Describe a task, review the plan, approve every sensitive action.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="min-h-screen bg-page text-sm leading-[1.5] text-ink">
            <StatusStrip />
            {children}
          </div>
        </Providers>
      </body>
    </html>
  );
}
