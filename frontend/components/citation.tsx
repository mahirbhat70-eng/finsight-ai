"use client";

import Link from "next/link";
import { Citation, CopilotPayload } from "@/lib/api";
import { Chip } from "./ui";

/** Citation card + verdict badge (Playbook P5.5). */

export function VerdictBadge({ verdict }: { verdict: string }) {
  const tone = verdict === "grounded" ? "ok" : verdict === "partial" ? "warn" : "high";
  const label = verdict === "grounded" ? "Grounded"
    : verdict === "partial" ? "Partially grounded" : "Insufficient evidence";
  return <Chip tone={tone as "ok" | "warn" | "high"}>{label}</Chip>;
}

export function CitationCard({ citation, filingId }: {
  citation: Citation; filingId?: string;
}) {
  return (
    <div className="panel p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sky-300">page {citation.page_no}</span>
        {filingId && (
          <Link className="text-sky-400 underline hover:text-sky-300"
            href={`/companies/${""}/source?page=${citation.page_no}&filing=${filingId}`}
            target="_blank">
            jump to source
          </Link>
        )}
      </div>
      <blockquote className="mt-2 border-l-2 border-sky-500/40 pl-2 italic text-slate-300">
        “{citation.quote.slice(0, 220)}{citation.quote.length > 220 ? "…" : ""}”
      </blockquote>
    </div>
  );
}

export function CitationList({ payload, filingId }: {
  payload: CopilotPayload; filingId?: string;
}) {
  if (!payload.citations.length) return null;
  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center gap-2">
        <VerdictBadge verdict={payload.verification.verdict} />
        <span className="text-xs text-slate-500">
          {payload.verification.grounded ? "every claim verified against the filing"
            : "some claims failed verification"}
        </span>
      </div>
      {payload.citations.map((c, i) => (
        <CitationCard key={`${c.chunk_id}-${i}`} citation={c} filingId={filingId} />
      ))}
    </div>
  );
}
