"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatInr, formatPercent, formatX } from "@/lib/format";
import { Chip, KpiCard, StateViews } from "@/components/ui";
import { FcfVsEbitda, TrendChart } from "@/components/charts";

/** Company overview: KPI row, trend charts, risk matrix. */

const RISK_ROWS = [
  ["Leverage",        ["lev_de", "lev_nd_ebitda"]],
  ["Liquidity",       ["liq_current", "liq_quick"]],
  ["Earnings quality",["eq_ocf_ebitda", "eq_fcf_negative"]],
  ["Profitability",   ["prof_margin_trend"]],
  ["Coverage",        ["cov_interest"]],
  ["Value creation",  ["vc_roic_wacc"]],
  ["Concentration",   ["conc_customer"]],
] as const;

const TABS = ["Overview", "Risk matrix"] as const;
type Tab = typeof TABS[number];

export default function CompanyPage() {
  const { id } = useParams<{ id: string }>();
  const metrics = useQuery({ queryKey: ["metrics", id], queryFn: () => api.metrics(id) });
  const risk    = useQuery({ queryKey: ["risk",    id], queryFn: () => api.risk(id) });
  const [tab, setTab] = useState<Tab>("Overview");

  const flagCount  = risk.data?.flags.length ?? 0;
  const highFlags  = risk.data?.flags.filter(f => f.severity === "high").length ?? 0;
  const score      = risk.data?.composite_score;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-[#4a6f94]">
            <Link href="/" className="hover:text-sky-400 transition-colors">Workspace</Link>
            <span>/</span>
            <span className="text-[#7a9bc0]">Company overview</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Company overview</h1>
        </div>
        <div className="flex gap-2">
          <NavBtn href={`/companies/${id}/valuation`} icon="chart">Valuation studio</NavBtn>
          <NavBtn href={`/companies/${id}/copilot`}   icon="chat" >Copilot</NavBtn>
        </div>
      </div>

      {/* KPI row */}
      <StateViews
        data={metrics.data}
        error={metrics.error}
        isLoading={metrics.isLoading}
        isEmpty={(d) => Object.keys(d.series).length === 0}
      >
        {(data) => {
          const series = data.series;
          const latest = (key: string) => series[key]?.at(-1) ?? null;
          const metric = (key: string) => {
            const row = data.metrics[key];
            return row ? Object.values(row).at(-1)?.value ?? null : null;
          };

          const kpis = [
            { label: "Revenue",        value: formatInr(latest("revenue"), 0),          key: "revenue", accent: true  },
            { label: "EBITDA margin",  value: formatPercent(metric("ebitda_margin")),    key: "ebitda",  accent: false },
            { label: "PAT",            value: formatInr(latest("pat"), 0),               key: "pat",     accent: false },
            { label: "FCF",            value: formatInr(latest("fcf"), 0),               key: "fcf",     accent: false },
            { label: "Net debt/EBITDA",value: formatX(metric("net_debt_to_ebitda")),     key: "ebitda",  accent: false },
          ];

          return (
            <div className="space-y-6">
              {/* KPIs */}
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                {kpis.map((k, i) => (
                  <div key={k.label} className="animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
                    <KpiCard
                      label={k.label}
                      value={k.value}
                      sparkline={series[k.key] ?? undefined}
                      accent={k.accent}
                    />
                  </div>
                ))}
              </div>

              {/* Tab bar */}
              <div className="flex items-center gap-1 border-b border-[#1e3a5f]">
                {TABS.map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                      tab === t
                        ? "border-sky-400 text-sky-400"
                        : "border-transparent text-[#4a6f94] hover:text-[#7a9bc0]"
                    }`}
                  >
                    {t}
                    {t === "Risk matrix" && flagCount > 0 && (
                      <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${highFlags > 0 ? "bg-rose-500/20 text-rose-400" : "bg-amber-500/20 text-amber-400"}`}>
                        {flagCount}
                      </span>
                    )}
                  </button>
                ))}
                <div className="ml-auto flex items-center gap-2 pb-1.5">
                  {score !== undefined && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#4a6f94]">Risk score</span>
                      <RiskGauge score={score} />
                    </div>
                  )}
                </div>
              </div>

              {/* Tab content */}
              {tab === "Overview" && (
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="panel p-5">
                    <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-[#4a6f94]">
                      Revenue &amp; EBITDA trend
                    </h2>
                    <TrendChart
                      periods={data.periods}
                      series={[
                        { key: "revenue", values: series.revenue ?? [] },
                        { key: "ebitda",  values: series.ebitda  ?? [] },
                      ]}
                    />
                  </div>
                  <div className="panel p-5">
                    <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-[#4a6f94]">
                      Earnings quality: FCF vs EBITDA
                    </h2>
                    <FcfVsEbitda
                      periods={data.periods}
                      fcf={series.fcf ?? []}
                      ebitda={series.ebitda ?? []}
                    />
                  </div>
                </div>
              )}

              {tab === "Risk matrix" && (
                <RiskMatrix risk={risk} />
              )}
            </div>
          );
        }}
      </StateViews>
    </div>
  );
}

function RiskGauge({ score }: { score: number }) {
  const color = score < 40 ? "#34d399" : score < 70 ? "#f59e0b" : "#f43f5e";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-[#0d1929]">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score}%`, background: color }}
        />
      </div>
      <span className="mono text-sm font-semibold" style={{ color }}>{score}</span>
    </div>
  );
}

function RiskMatrix({ risk }: { risk: ReturnType<typeof useQuery<Awaited<ReturnType<typeof api.risk>>>> }) {
  if (risk.isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[1,2,3,4,5,6].map((i) => (
          <div key={i} className="panel h-24 animate-shimmer" />
        ))}
      </div>
    );
  }
  if (!risk.data?.flags.length) {
    return (
      <div className="panel p-10 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10">
          <svg className="h-6 w-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p className="text-sm text-[#4a6f94]">No flags on the current thresholds.</p>
      </div>
    );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {risk.data.flags.map((flag, i) => (
        <div
          key={flag.rule_id}
          className={`panel panel-hover animate-slide-up p-4 transition-all ${
            flag.severity === "high"
              ? "border-rose-500/30 bg-rose-500/5"
              : "border-amber-500/20 bg-amber-500/5"
          }`}
          style={{ animationDelay: `${i * 40}ms` }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-widest text-[#4a6f94]">{flag.category}</span>
            <Chip tone={flag.severity === "high" ? "high" : "medium"}>{flag.severity}</Chip>
          </div>
          <p className="mt-2.5 text-sm leading-relaxed text-[#c5d8eb]">{flag.rationale}</p>
          <p className="mt-1.5 font-mono text-[10px] text-[#2a5080]">{flag.rule_id}</p>
        </div>
      ))}
    </div>
  );
}

function NavBtn({ href, icon, children }: {
  href: string; icon: "chart" | "chat"; children: React.ReactNode;
}) {
  const icons = {
    chart: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
    chat:  "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z",
  };
  return (
    <Link
      href={href}
      className="flex items-center gap-1.5 rounded-lg border border-[#1e3a5f] bg-[#0f2035] px-3 py-2 text-xs font-medium text-[#7a9bc0] transition-all hover:border-sky-500/40 hover:text-sky-400"
    >
      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d={icons[icon]} />
      </svg>
      {children}
    </Link>
  );
}
