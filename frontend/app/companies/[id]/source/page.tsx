"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

/** Source viewer (P5.5): native PDF viewer anchored to the cited page.
 * The browser's built-in viewer honors #page=N; upgrade path is pdf.js
 * for in-page highlight of the exact line-item row. */

function SourceInner() {
  const params = useSearchParams();
  const page = params.get("page") ?? "1";
  const filingId = params.get("filing");

  if (!filingId) {
    return (
      <div className="panel p-8 text-center text-slate-400">
        No filing selected. Open a citation from the copilot to jump here.
      </div>
    );
  }
  const url = `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1"}/filings/${filingId}/file#page=${page}`;
  return (
    <div className="space-y-3">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Source document — page {page}</h1>
        <a href={url} target="_blank" rel="noreferrer" className="text-sm text-sky-400 underline">
          open in new tab
        </a>
      </header>
      <iframe src={url} title="filing source" className="h-[80vh] w-full rounded-lg border border-slate-700" />
    </div>
  );
}

export default function SourcePage() {
  return (
    <Suspense fallback={<div className="panel animate-pulse p-8 text-center text-slate-400">Loading…</div>}>
      <SourceInner />
    </Suspense>
  );
}
