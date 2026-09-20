"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Company, JobState } from "@/lib/api";
import { Button, KpiCard, StateViews } from "@/components/ui";

/** Workspace: company cards + upload modal with SSE job progress. */

export default function WorkspacePage() {
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const [uploadFor, setUploadFor] = useState<Company | null>(null);

  const totalCompanies = companies.data?.length ?? 0;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Hero section */}
      <div className="relative overflow-hidden rounded-2xl border border-[#1e3a5f] bg-gradient-to-br from-[#0d1929] to-[#060d1a] p-8">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-sky-500/5 blur-3xl" />
        <div className="absolute -bottom-10 -left-10 h-48 w-48 rounded-full bg-indigo-500/5 blur-3xl" />
        <div className="relative">
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded-full bg-sky-500/10 px-2.5 py-0.5 text-xs font-medium text-sky-400 border border-sky-500/20">
              Due Diligence
            </span>
            <span className="text-xs text-[#4a6f94]">v2.5 · Gemini powered</span>
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-white">
            Investment <span className="gradient-text">Workspace</span>
          </h1>
          <p className="mt-2 max-w-xl text-sm text-[#7a9bc0]">
            Upload annual report filings for deterministic valuation, risk flagging,
            and grounded Q&amp;A. Every number is citation-checked.
          </p>
          <div className="mt-6 flex flex-wrap gap-4">
            <StatPill icon="building" label="Companies" value={String(totalCompanies)} />
            <StatPill icon="shield"   label="Risk engine" value="Active" ok />
            <StatPill icon="sparkle"  label="LLM"        value="Gemini 2.5 Flash" ok />
          </div>
        </div>
      </div>

      {/* Company grid */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[#7a9bc0] uppercase tracking-widest">Companies</h2>
          <Link href="/review" className="flex items-center gap-1.5 text-xs text-sky-400 hover:text-sky-300 transition-colors">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            Review queue
          </Link>
        </div>

        <StateViews
          data={companies.data}
          error={companies.error}
          isLoading={companies.isLoading}
          isEmpty={(d) => d.length === 0}
        >
          {(data) => (
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {data.map((c, i) => (
                <div key={c.id} className="animate-slide-up" style={{ animationDelay: `${i * 60}ms` }}>
                  <CompanyCard company={c} onUpload={() => setUploadFor(c)} />
                </div>
              ))}
            </div>
          )}
        </StateViews>
      </div>

      {uploadFor && <UploadModal company={uploadFor} onClose={() => setUploadFor(null)} />}
    </div>
  );
}

function StatPill({ icon, label, value, ok }: {
  icon: string; label: string; value: string; ok?: boolean;
}) {
  const icons: Record<string, string> = {
    building: "M3 21h18M6 21V7l6-4 6 4v14M9 21V11h6v10",
    shield:   "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
    sparkle:  "M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z",
  };
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-[#1e3a5f] bg-[#0f2035]/60 px-4 py-2.5">
      <svg className={`h-4 w-4 ${ok ? "text-emerald-400" : "text-sky-400"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d={icons[icon]} />
      </svg>
      <div>
        <div className="text-[10px] text-[#4a6f94] uppercase tracking-wide">{label}</div>
        <div className="text-sm font-semibold text-[#e2ecf7]">{value}</div>
      </div>
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
  const revenue     = latest("revenue");
  const ebitda      = latest("ebitda");
  const ebitdaMargin = metrics.data?.metrics.ebitda_margin
    ? Object.values(metrics.data.metrics.ebitda_margin).at(-1)?.value
    : null;

  return (
    <div className="panel panel-hover group flex flex-col gap-4 p-5 transition-all duration-200">
      {/* Header */}
      <div>
        <Link
          href={`/companies/${company.id}`}
          className="text-base font-semibold text-white group-hover:text-sky-300 transition-colors"
        >
          {company.name}
        </Link>
        <div className="mt-0.5 flex items-center gap-2">
          <span className="rounded-full bg-[#0d1929] px-2 py-0.5 text-[10px] text-[#4a6f94] border border-[#1e3a5f]">
            {company.sector}
          </span>
          <span className="text-[10px] text-[#2a5080]">FY {company.fiscal_year_end}</span>
        </div>
      </div>

      {/* KPI mini-grid */}
      <div className="grid grid-cols-3 gap-2">
        <MiniKpi label="Revenue" value={revenue ? `Rs${(revenue / 1000).toFixed(1)}k Cr` : "—"} />
        <MiniKpi label="EBITDA" value={ebitdaMargin ? `${(ebitdaMargin * 100).toFixed(1)}%` : "—"} accent />
        <MiniKpi label="Filings" value={metrics.data ? "1" : "—"} />
      </div>

      {/* Sparkline if data */}
      {series.revenue && series.revenue.length > 1 && (
        <div className="border-t border-[#1e3a5f] pt-3">
          <div className="mb-1 text-[10px] text-[#2a5080] uppercase tracking-wide">Revenue trend</div>
          <SparkBar values={series.revenue} />
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between border-t border-[#1e3a5f] pt-3">
        <div className="flex gap-3">
          <NavChip href={`/companies/${company.id}/valuation`} label="Valuation" />
          <NavChip href={`/companies/${company.id}/copilot`}   label="Copilot"   />
        </div>
        <Button tone="ghost" onClick={onUpload}>
          <span className="flex items-center gap-1.5">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Upload
          </span>
        </Button>
      </div>
    </div>
  );
}

function MiniKpi({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg bg-[#060d1a] border border-[#1e3a5f] p-2">
      <div className="text-[9px] uppercase tracking-widest text-[#2a5080]">{label}</div>
      <div className={`mono mt-0.5 text-sm font-semibold ${accent ? "text-sky-300" : "text-[#e2ecf7]"}`}>{value}</div>
    </div>
  );
}

function SparkBar({ values }: { values: (number | null)[] }) {
  const clean = values.filter((v): v is number => typeof v === "number");
  if (clean.length < 2) return null;
  const max = Math.max(...clean);
  return (
    <div className="flex items-end gap-0.5 h-8">
      {clean.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm bg-sky-500/30 transition-all"
          style={{ height: `${(v / max) * 100}%`, background: i === clean.length - 1 ? "#38bdf8" : undefined }}
        />
      ))}
    </div>
  );
}

function NavChip({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="rounded-md px-2.5 py-1 text-xs font-medium text-sky-400 border border-sky-500/20 bg-sky-500/5 hover:bg-sky-500/15 transition-colors"
    >
      {label}
    </Link>
  );
}

function UploadModal({ company, onClose }: { company: Company; onClose: () => void }) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [job, setJob] = useState<JobState | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const { job_id } = await api.uploadFiling(company.id, file);
      while (true) {
        const state = await api.job(job_id);
        setJob(state);
        if (["ready", "failed", "awaiting_review"].includes(state.state)) return state;
        await new Promise((r) => setTimeout(r, 800));
      }
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const isTerminal = job && ["ready", "failed", "awaiting_review"].includes(job.state);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="panel w-full max-w-md animate-slide-up p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Upload filing</h2>
            <p className="text-xs text-[#4a6f94]">{company.name}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-[#4a6f94] hover:bg-[#152845] hover:text-white transition-colors">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Drop zone */}
        <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-[#1e3a5f] bg-[#060d1a] p-8 transition-colors hover:border-sky-500/50 hover:bg-sky-500/5">
          <svg className="h-8 w-8 text-[#2a5080]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          <span className="mt-2 text-sm text-[#4a6f94]">
            {fileName ?? "Click or drag PDF / XLSX"}
          </span>
          <span className="mt-1 text-xs text-[#2a5080]">Max 50 MB · magic bytes verified</span>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.xlsx"
            className="hidden"
            onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)}
          />
        </label>

        {/* Progress */}
        {job && (
          <div className="mt-4 space-y-2">
            <div className="flex justify-between text-xs text-[#7a9bc0]">
              <span className="font-medium">{job.state}</span>
              <span>{job.progress}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[#0d1929]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-sky-600 to-sky-400 transition-all duration-500"
                style={{ width: `${job.progress}%` }}
              />
            </div>
            <p className="text-xs text-[#4a6f94]">{job.stage_detail}</p>
            {job.state === "awaiting_review" && (
              <Link href="/review" className="block text-center text-xs font-medium text-sky-400 hover:text-sky-300 transition-colors">
                Go to review queue →
              </Link>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="mt-5 flex justify-end gap-2">
          <Button tone="ghost" onClick={onClose}>Close</Button>
          <Button
            disabled={!fileName || upload.isPending}
            onClick={() => {
              const file = fileRef.current?.files?.[0];
              if (file) upload.mutate(file);
            }}
          >
            {upload.isPending ? (
              <span className="flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Processing…
              </span>
            ) : "Upload filing"}
          </Button>
        </div>
      </div>
    </div>
  );
}
