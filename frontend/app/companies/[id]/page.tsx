"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatInr, formatPercent, formatX } from "@/lib/format";
import { Chip, KpiCard, StateViews } from "@/components/ui";
import { FcfVsEbitda, TrendChart } from "@/components/charts";

/** Company overview: KPI row, trend charts, risk matrix (P5.3). */

const RISK_ROWS = [
  ["Leverage", ["lev_de", "lev_nd_ebitda"]],
  ["Liquidity", ["liq_current", "liq_quick"]],
  ["Earnings quality", ["eq_ocf_ebitda", "eq_fcf_negative"]],
  ["Profitability", ["prof_margin_trend"]],
  ["Coverage", ["cov_interest"]],
  ["Value creation", ["vc_roic_wacc"]],
  ["Concentration", ["conc_customer"]],
] as const;

export default function CompanyPage() {
  const { id } = useParams<{ id: string }>();
  const metrics = useQuery({ queryKey: ["metrics", id], queryFn: () => api.metrics(id) });
  const risk = useQuery({ queryKey: ["risk", id], queryFn: () => api.risk(id) });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Company overview</h1>
        <Link href={`/companies/${id}/valuation`} className="text-sm text-sky-400 underline">valuation studio</Link>
        <Link href={`/companies/${id}/copilot`} className="text-sm text-sky-400 underline">copilot</Link>
      </header>

      <StateViews data={metrics.data} error={metrics.error} isLoading={metrics.isLoading}
        isEmpty={(d) => Object.keys(d.series).length === 0}>
        {(data) => {
          const series = data.series;
          const latest = (key: string) => series[key]?.at(-1) ?? null;
          const metric = (key: string) => {
            const row = data.metrics[key];
            return row ? Object.values(row).at(-1)?.value ?? null : null;
          };
          const kpis = [
            { label: "Revenue", value: formatInr(latest("revenue"), 0) },
            { label: "EBITDA margin", value: formatPercent(metric("ebitda_margin")) },
            { label: "PAT", value: formatInr(latest("pat"), 0) },
            { label: "FCF", value: formatInr(latest("fcf"), 0) },
            {
              label: "Net debt / EBITDA",
              value: formatX(metric("net_debt_to_ebitda")),
            },
          ];
          return (
            <>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
                {kpis.map((k) => (
                  <KpiCard key={k.label} label={k.label} value={k.value}
                    sparkline={series[k.label === "Revenue" ? "revenue" : "ebitda"] ?? undefined} />
                ))}
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="panel p-4">
                  <h2 className="mb-2 text-sm font-semibold uppercase text-slate-300">
                    Revenue &amp; EBITDA trend
                  </h2>
                  <TrendChart periods={data.periods} series={[
                    { key: "revenue", values: series.revenue ?? [] },
                    { key: "ebitda", values: series.ebitda ?? [] },
                  ]} />
                </div>
                <div className="panel p-4">
                  <h2 className="mb-2 text-sm font-semibold uppercase text-slate-300">
                    Earnings quality: FCF vs EBITDA
                  </h2>
                  <FcfVsEbitda periods={data.periods} fcf={series.fcf ?? []}
                    ebitda={series.ebitda ?? []} />
                </div>
              </div>
            </>
          );
        }}
      </StateViews>

      <div className="panel p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase text-slate-300">Risk matrix</h2>
          {risk.data && (
            <span className="text-sm text-slate-400">
              composite score <span className="font-semibold text-slate-100">{risk.data.composite_score}</span>/100
            </span>
          )}
        </div>
        {risk.isLoading && <div className="animate-pulse text-slate-400">Loading…</div>}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(risk.data?.flags ?? []).map((flag) => (
            <div key={flag.rule_id} className="panel p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-wide text-slate-400">{flag.category}</span>
                <Chip tone={flag.severity === "high" ? "high" : "medium"}>{flag.severity}</Chip>
              </div>
              <p className="mt-2 text-sm text-slate-200">{flag.rationale}</p>
            </div>
          ))}
          {!risk.isLoading && !risk.data?.flags.length && (
            <p className="text-sm text-slate-400">No flags on the current thresholds.</p>
          )}
        </div>
      </div>
    </div>
  );
}
