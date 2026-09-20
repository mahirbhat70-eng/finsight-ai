"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Company, JobState } from "@/lib/api";
import { Button, Card, KpiCard, StateViews } from "@/components/ui";

/** Workspace: company cards + upload modal with SSE job progress (P5.2). */

export default function WorkspacePage() {
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const [uploadFor, setUploadFor] = useState<Company | null>(null);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Workspace</h1>
          <p className="text-sm text-slate-400">
            Companies under due diligence. Upload filings to ingest, review, and value.
          </p>
        </div>
        <Link href="/review" className="text-sm text-sky-400 underline">Review queue</Link>
      </header>

      <StateViews data={companies.data} error={companies.error}
        isLoading={companies.isLoading} isEmpty={(d) => d.length === 0}>
        {(data) => (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.map((c) => (
              <CompanyCard key={c.id} company={c} onUpload={() => setUploadFor(c)} />
            ))}
          </div>
        )}
      </StateViews>

      {uploadFor && <UploadModal company={uploadFor} onClose={() => setUploadFor(null)} />}
    </div>
  );
}

function CompanyCard({ company, onUpload }: { company: Company; onUpload: () => void }) {
  const metrics = useQuery({
    queryKey: ["metrics", company.id],
    queryFn: () => api.metrics(company.id),
  });
  const series = metrics.data?.series ?? {};
  const latest = (key: string) => series[key]?.at(-1) ?? null;
  const revenue = latest("revenue");
  const ebitdaMargin = metrics.data?.metrics.ebitda_margin
    ? Object.values(metrics.data.metrics.ebitda_margin).at(-1)?.value : null;

  return (
    <Card className="flex flex-col justify-between">
      <div>
        <Link href={`/companies/${company.id}`} className="text-lg font-semibold text-sky-300 hover:underline">
          {company.name}
        </Link>
        <div className="text-xs text-slate-500">{company.sector} · FY end {company.fiscal_year_end}</div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
          <KpiCard label="Revenue" value={revenue ? `Rs ${(revenue / 1000).toFixed(1)}k Cr` : "—"} />
          <KpiCard label="EBITDA" value={ebitdaMargin ? `${(ebitdaMargin * 100).toFixed(1)}%` : "—"} />
          <KpiCard label="Filings" value={metrics.data ? "1" : "—"} />
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <Link href={`/companies/${company.id}/valuation`} className="text-xs text-sky-400 underline">valuation</Link>
        <Link href={`/companies/${company.id}/copilot`} className="text-xs text-sky-400 underline">copilot</Link>
        <Button tone="ghost" onClick={onUpload}>Upload filing</Button>
      </div>
    </Card>
  );
}

function UploadModal({ company, onClose }: { company: Company; onClose: () => void }) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [job, setJob] = useState<JobState | null>(null);
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const { job_id } = await api.uploadFiling(company.id, file);
      // poll job until terminal (SSE variant lives in the jobs API)
      while (true) {
        const state = await api.job(job_id);
        setJob(state);
        if (["ready", "failed", "awaiting_review"].includes(state.state)) return state;
        await new Promise((r) => setTimeout(r, 800));
      }
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/60 p-4">
      <div className="panel w-full max-w-md p-6">
        <h2 className="text-lg font-semibold">Upload filing — {company.name}</h2>
        <p className="mt-1 text-xs text-slate-400">PDF or XLSX, max 50MB. Magic bytes checked server-side.</p>
        <input ref={fileRef} type="file" accept=".pdf,.xlsx" className="mt-4 w-full text-sm" />
        {job && (
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded bg-slate-800">
              <div className="h-full bg-sky-500 transition-all"
                style={{ width: `${job.progress}%` }} />
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
              <span>{job.state} — {job.stage_detail}</span>
              <Link href="/review" className="text-sky-400 underline">review queue</Link>
            </div>
          </div>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <Button tone="ghost" onClick={onClose}>Close</Button>
          <Button disabled={!fileRef.current?.files?.[0] || upload.isPending}
            onClick={() => {
              const file = fileRef.current?.files?.[0];
              if (file) upload.mutate(file);
            }}>
            {upload.isPending ? "Uploading…" : "Upload"}
          </Button>
        </div>
      </div>
    </div>
  );
}
