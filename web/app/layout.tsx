import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import AppShell from "./components/AppShell";
import PostHogProvider from "./providers/PostHogProvider";

export const metadata: Metadata = {
  title: "Scrivi",
  description: "Turn YouTube videos into illustrated essays, delivered to your inbox.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-stone-50 text-stone-900 antialiased">
        <Suspense fallback={null}>
          <PostHogProvider>
            <AppShell>{children}</AppShell>
          </PostHogProvider>
        </Suspense>
      </body>
    </html>
  );
}
