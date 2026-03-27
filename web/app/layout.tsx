import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Video to Essay",
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
        {children}
      </body>
    </html>
  );
}
