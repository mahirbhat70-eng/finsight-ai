import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/lib/query-provider";
import Link from "next/link";

export const metadata: Metadata = {
  title: "FinSight AI — Investment Due Diligence",
  description: "Deterministic-first valuation and grounded RAG copilot for filings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          {/* Top navigation bar */}
          <nav className="sticky top-0 z-50 border-b border-[#1e3a5f] bg-[#060d1a]/80 backdrop-blur-xl">
            <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
              {/* Logo */}
              <Link href="/" className="flex items-center gap-2.5 group">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-500 shadow-lg shadow-sky-500/20 transition-shadow group-hover:shadow-sky-500/40">
                  <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                </div>
                <span className="text-sm font-bold tracking-tight text-white">
                  FinSight <span className="gradient-text">AI</span>
                </span>
              </Link>

              {/* Nav links */}
              <div className="flex items-center gap-1 text-xs">
                <NavLink href="/" label="Workspace" />
                <NavLink href="/review" label="Review queue" />
              </div>

              {/* Spacer */}
              <div className="flex-1" />

              {/* Status pill */}
              <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                Gemini 2.5 Flash live
              </div>
            </div>
          </nav>

          <main className="mx-auto max-w-7xl p-6 pt-8">{children}</main>
        </QueryProvider>
      </body>
    </html>
  );
}

function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="rounded-md px-3 py-1.5 text-[#7a9bc0] transition-colors hover:bg-[#0f2035] hover:text-[#e2ecf7]"
    >
      {label}
    </Link>
  );
}
