import "./globals.css";
import type { Metadata } from "next";
import { Suspense } from "react";
import ApiBanner from "@/components/ApiBanner";
import Nav from "@/components/Nav";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "Chimera",
  description: "Who to talk to this week, and why — founders, LPs, talent, and connectors.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <ApiBanner />
          <div className="app">
            <Suspense fallback={<nav className="nav" />}>
              <Nav />
            </Suspense>
            <main className="main">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
