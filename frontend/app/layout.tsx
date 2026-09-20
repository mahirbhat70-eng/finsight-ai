import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";

export const metadata: Metadata = {
  title: "FinSight AI — Investment Due Diligence",
  description: "Deterministic-first valuation and grounded RAG copilot for filings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          <nav className="border-b border-slate-800 bg-slate-900/60 px-6 py-3 backdrop-blur">
            <span className="text-sm font-bold tracking-wide text-sky-400">FinSight AI</span>
            <span className="ml-4 text-xs text-slate-500">
              due diligence · valuation · grounded Q&amp;A
            </span>
          </nav>
          <main className="mx-auto max-w-7xl p-6">{children}</main>
        </QueryProvider>
      </body>
    </html>
  );
}
