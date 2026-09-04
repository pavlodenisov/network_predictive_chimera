import "./globals.css";
import type { Metadata } from "next";
import ApiBanner from "@/components/ApiBanner";
import Nav from "@/components/Nav";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "Chimera Network Intelligence",
  description: "Structured, auditable intelligence on founders, LPs, talent, and connectors.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <ApiBanner />
          <div className="app">
            <Nav />
            <main className="main">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
