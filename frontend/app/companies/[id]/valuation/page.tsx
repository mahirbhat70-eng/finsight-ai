"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ValuationReport } from "@/lib/api";
import { formatInr, formatSharePrice } from "@/lib/format";
import { Button, Card, Chip, StateViews } from "@/components/ui";
import { BridgeWaterfall, SensitivityHeatmap, TornadoChart } from "@/components/charts";
import Link from "next/link";

/** Valuation studio — live sliders, debounced POST, abort on new request. */

const DEFAULT_ASSUMPTIONS = {
  rf: 7.0, beta: 1.15, market_risk_premium: 6.5, size_premium: 0.0,
  cost_of_debt_pre_tax: 9.2, tax_rate: 25.17, mid_year: true,
  terminal_growth: 5.0, exit_multiple: 9.0, current_price: 150.0,
};

const DEFAULT_FORECAST = {
  revenue_growth:    [11.0, 10.5, 9.5, 8.5, 7.5],
  ebitda_margin:     [21.3, 21.6, 22.0, 22.3, 22.5],
  dna_pct_revenue:   4.2,
  capex_pct_revenue: [9.0, 9.0, 6.5, 6.5, 6.5],
};

interface SliderSpec {
  key: keyof typeof DEFAULT_ASSUMPTIONS;
  label: string; min: number; max: number; step: number; unit: string;
}

const SLIDERS: SliderSpec[] = [
  { key: "rf",                   label: "Risk-free rate",       min: 4,  max: 10, step: 0.1, unit: "%" },
  { key: "beta",                 label: "Beta",                 min: 0.4,max: 2,  step: 0.05,unit: "x" },
  { key: "market_risk_premium",  label: "Equity risk premium",  min: 3,  max: 10, step: 0.1, unit: "%" },
  { key: "cost_of_debt_pre_tax", label: "Pre-tax cost of debt", min: 5,  max: 14, step: 0.1, unit: "%" },
  { key: "tax_rate",             label: "Tax rate",             min: 5,  max: 45, step: 0.1, unit: "%" },
  { key: "terminal_growth",      label: "Terminal growth g",    min: 1,  max: 8,  step: 0.1, unit: "%" },
  { key: "exit_multiple",        label: "Exit EV/EBITDA",       min: 4,  max: 15, step: 0.5, unit: "x" },
  { key: "current_price",        label: "Current price",        min: 20, max: 500,step: 1,   unit: "Rs" },
];

export default function ValuationPage() {
  const { id } = useParams<{ id: string }>();
  const [assumptions, setAssumptions] = useState(DEFAULT_ASSUMPTIONS);
  const [forecast,    setForecast]    = useState(DEFAULT_FORECAST);
  const [report,      setReport]      = useState<ValuationReport | null>(null);
  const [error,       setError]       = useState<string | null>(null);
  const [pending,     setPending]     = useState(false);
  const abortRef    = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setPending(true);
      setError(null);
      try {
        const result = await api.runValuation(id, assumptions, forecast, controller.signal);
        setReport(result);
      } catch (err) {
        if ((err as Error).name !== "AbortError") setError(String((err as Error).message));
      } finally {
        setPending(false);
      }
    }, 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [id, assumptions, forecast]);

  const vsCurrent = useMemo(() => {
    if (!report) return null;
    const fair  = report.dcf.bridge.per_share_inr;
    const price = assumptions.current_price;
    return (fair / price - 1) * 100;
  }, [report, assumptions.current_price]);

  const upside = vsCurrent !== null && vsCurrent >= 0;

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-[#4a6f94]">
            <Link href="/" className="hover:text-sky-400 transition-colors">Workspace</Link>
            <span>/</span>
            <Link href={`/companies/${id}`} className="hover:text-sky-400 transition-colors">Overview</Link>
            <span>/</span>
            <span className="text-[#7a9bc0]">Valuation</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Valuation <span className="gradient-text">Studio</span>
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {pending && (
            <div className="flex items-center gap-1.5 text-xs text-sky-400">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-sky-400/30 border-t-sky-400" />
              Computing…
            </div>
          )}
          <Link href={`/companies/${id}/copilot`}
            className="rounded-lg border border-[#1e3a5f] bg-[#0f2035] px-3 py-2 text-xs text-[#7a9bc0] hover:text-sky-400 transition-colors">
            Copilot →
          </Link>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* Left: controls */}
        <div className="space-y-4">
          <Card title="Assumptions">
            <div className="space-y-5">
              {SLIDERS.map((s) => (
                <PremiumSlider
                  key={s.key}
                  spec={s}
                  value={assumptions[s.key] as number}
                  onChange={(v) => setAssumptions((a) => ({ ...a, [s.key]: v }))}
                />
              ))}
              <label className="flex cursor-pointer items-center gap-2.5 text-sm text-[#7a9bc0]">
                <div className={`relative h-5 w-9 rounded-full transition-colors ${assumptions.mid_year ? "bg-sky-500" : "bg-[#1e3a5f]"}`}
                     onClick={() => setAssumptions((a) => ({ ...a, mid_year: !a.mid_year }))}>
                  <div className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${assumptions.mid_year ? "translate-x-4" : ""}`} />
                </div>
                Mid-year discounting
              </label>
            </div>
          </Card>

          <Card title="Forecast drivers">
            <div className="space-y-4">
              <YearList label="Revenue growth" unit="%" values={forecast.revenue_growth}
                min={-5} max={25} step={0.5}
                onChange={(values) => setForecast((f) => ({ ...f, revenue_growth: values }))} />
              <YearList label="EBITDA margin" unit="%" values={forecast.ebitda_margin}
                min={5} max={35} step={0.1}
                onChange={(values) => setForecast((f) => ({ ...f, ebitda_margin: values }))} />
              <YearList label="Capex % revenue" unit="%" values={forecast.capex_pct_revenue}
                min={1} max={15} step={0.5}
                onChange={(values) => setForecast((f) => ({ ...f, capex_pct_revenue: values }))} />
            </div>
            <div className="mt-4 flex justify-end border-t border-[#1e3a5f] pt-4">
              <Button tone="ghost" onClick={() => { setAssumptions(DEFAULT_ASSUMPTIONS); setForecast(DEFAULT_FORECAST); }}>
                Reset to base case
              </Button>
            </div>
          </Card>
        </div>

        {/* Right: results */}
        <div className="space-y-4">
          {error && (
            <div className="panel border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-300">
              {error}
            </div>
          )}

          <StateViews data={report} error={null} isLoading={pending && !report}
            isEmpty={() => report === null}>
            {(r) => (
              <div className="space-y-4 animate-fade-in">
                {/* Summary KPIs */}
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <ResultKpi
                    label="Fair value / share"
                    value={formatSharePrice(r.dcf.bridge.per_share_inr)}
                    accent
                  />
                  <ResultKpi
                    label="vs current price"
                    value={vsCurrent === null ? "—" : `${upside ? "+" : ""}${vsCurrent.toFixed(0)}%`}
                    color={upside ? "#34d399" : "#f43f5e"}
                    badge={upside ? "UPSIDE" : "DOWNSIDE"}
                    badgeTone={upside ? "ok" : "high"}
                  />
                  <ResultKpi label="WACC" value={`${(r.wacc * 100).toFixed(2)}%`} />
                  <ResultKpi label="Enterprise value" value={formatInr(r.dcf.bridge.enterprise_value, 0)} />
                </div>

                {/* Scenarios */}
                <div className="grid gap-3 lg:grid-cols-3">
                  {Object.entries(r.scenarios).map(([name, s]) => (
                    <div key={name} className="panel p-4 border-[#1e3a5f]">
                      <div className="mb-1 text-[10px] uppercase tracking-widest text-[#4a6f94]">{name}</div>
                      <div className="mono text-xl font-semibold text-white">{formatSharePrice(s.per_share_inr)}</div>
                      <div className="mono mt-0.5 text-xs text-[#4a6f94]">
                        equity {formatInr(s.equity_value, 0)}
                      </div>
                    </div>
                  ))}
                </div>

                <Card title="EV bridge — waterfall">
                  <BridgeWaterfall bridge={r.dcf.bridge} />
                </Card>

                <Card title="Sensitivity: WACC x terminal g (fair value / share)">
                  <SensitivityHeatmap grid={r.sensitivity} />
                </Card>

                <Card title="Tornado — what moves the needle">
                  <TornadoChart tornado={r.tornado} />
                </Card>

                <Card title="Model checks">
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(r.dcf.checks).map(([name, check]) => (
                      <Chip key={name} tone={check.severity === "warn" ? "warn" : check.severity === "info" ? "info" : "ok"}>
                        {check.severity.toUpperCase()} · {name}
                      </Chip>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-[#4a6f94]">{r.dcf.checks.tv_share_of_ev.detail}</p>
                </Card>

                <Card title="Forecast rows">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-[#1e3a5f]">
                          {["yr","revenue","EBITDA","NOPAT","capex","FCFF","DF","PV"].map((h) => (
                            <th key={h} className="p-2 text-right font-medium text-[#4a6f94] uppercase tracking-wide">
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="mono">
                        {r.dcf.rows.map((row, i) => (
                          <tr key={row.year} className={`border-b border-[#1e3a5f] transition-colors hover:bg-[#0f2035] ${i % 2 === 0 ? "bg-[#060d1a]/30" : ""}`}>
                            <td className="p-2 text-right font-semibold text-sky-400">{row.year}</td>
                            <td className="p-2 text-right text-[#e2ecf7]">{row.revenue.toFixed(0)}</td>
                            <td className="p-2 text-right text-[#e2ecf7]">{row.ebitda.toFixed(0)}</td>
                            <td className="p-2 text-right text-[#e2ecf7]">{row.nopat.toFixed(0)}</td>
                            <td className="p-2 text-right text-rose-300">{row.capex.toFixed(0)}</td>
                            <td className="p-2 text-right text-emerald-300">{row.fcff.toFixed(0)}</td>
                            <td className="p-2 text-right text-[#7a9bc0]">{row.discount_factor.toFixed(3)}</td>
                            <td className="p-2 text-right text-indigo-300">{row.pv.toFixed(0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            )}
          </StateViews>
        </div>
      </div>
    </div>
  );
}

function ResultKpi({ label, value, accent, color, badge, badgeTone }: {
  label: string; value: string; accent?: boolean;
  color?: string; badge?: string; badgeTone?: "ok" | "high";
}) {
  return (
    <div className={`panel relative overflow-hidden p-4 ${accent ? "panel-glow" : ""}`}>
      <div className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent ${accent ? "via-sky-400" : "via-[#1e3a5f]"} to-transparent`} />
      <div className="text-[10px] font-semibold uppercase tracking-widest text-[#4a6f94]">{label}</div>
      <div className={`mono mt-2 text-2xl font-semibold ${accent ? "gradient-text" : ""}`}
           style={color ? { color } : undefined}>
        {value}
      </div>
      {badge && badgeTone && (
        <div className="mt-1.5">
          <Chip tone={badgeTone}>{badge}</Chip>
        </div>
      )}
    </div>
  );
}

function PremiumSlider({ spec, value, onChange }: {
  spec: SliderSpec; value: number; onChange: (v: number) => void;
}) {
  const pct = ((value - spec.min) / (spec.max - spec.min)) * 100;
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-[#7a9bc0]">{spec.label}</span>
        <span className="mono text-xs font-medium text-sky-300">
          {value}{spec.unit}
        </span>
      </div>
      <div className="relative mt-2">
        <input
          type="range"
          className="w-full"
          min={spec.min} max={spec.max} step={spec.step} value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          style={{
            background: `linear-gradient(to right, #38bdf8 ${pct}%, #1e3a5f ${pct}%)`
          }}
        />
      </div>
    </div>
  );
}

function YearList({ label, unit, values, min, max, step, onChange }: {
  label: string; unit: string; values: number[];
  min: number; max: number; step: number;
  onChange: (values: number[]) => void;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-xs text-[#7a9bc0]">
        <span>{label}</span>
        <span className="rounded bg-[#0d1929] px-1.5 py-0.5 text-[10px] text-[#4a6f94]">{unit} · Y1–Y5</span>
      </div>
      <div className="grid grid-cols-5 gap-1">
        {values.map((v, i) => (
          <div key={i} className="relative">
            <span className="absolute -top-4 left-0 right-0 text-center text-[9px] text-[#2a5080]">Y{i+1}</span>
            <input
              type="number"
              className="mono w-full rounded-lg border border-[#1e3a5f] bg-[#060d1a] p-1.5 text-right text-xs text-[#e2ecf7] focus:border-sky-500/50 focus:outline-none focus:ring-1 focus:ring-sky-500/30 transition-colors"
              value={v} min={min} max={max} step={step}
              onChange={(e) => {
                const next = [...values];
                next[i] = parseFloat(e.target.value) || 0;
                onChange(next);
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
