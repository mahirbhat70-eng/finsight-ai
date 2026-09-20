"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ValuationReport } from "@/lib/api";
import { formatInr, formatSharePrice } from "@/lib/format";
import { Button, Card, Chip, StateViews } from "@/components/ui";
import { BridgeWaterfall, SensitivityHeatmap, TornadoChart } from "@/components/charts";

/** Valuation studio (P5.4): assumption sliders -> debounced 400ms POST,
 * in-flight requests aborted (AbortController), results re-render. */

const DEFAULT_ASSUMPTIONS = {
  rf: 7.0, beta: 1.15, market_risk_premium: 6.5, size_premium: 0.0,
  cost_of_debt_pre_tax: 9.2, tax_rate: 25.17, mid_year: true,
  terminal_growth: 5.0, exit_multiple: 9.0, current_price: 150.0,
};

const DEFAULT_FORECAST = {
  revenue_growth: [11.0, 10.5, 9.5, 8.5, 7.5],
  ebitda_margin: [21.3, 21.6, 22.0, 22.3, 22.5],
  dna_pct_revenue: 4.2,
  capex_pct_revenue: [9.0, 9.0, 6.5, 6.5, 6.5],
};

interface SliderSpec {
  key: keyof typeof DEFAULT_ASSUMPTIONS;
  label: string;
  min: number; max: number; step: number; unit: string;
}

const SLIDERS: SliderSpec[] = [
  { key: "rf", label: "Risk-free rate", min: 4, max: 10, step: 0.1, unit: "%" },
  { key: "beta", label: "Beta", min: 0.4, max: 2, step: 0.05, unit: "x" },
  { key: "market_risk_premium", label: "Equity risk premium", min: 3, max: 10, step: 0.1, unit: "%" },
  { key: "cost_of_debt_pre_tax", label: "Pre-tax cost of debt", min: 5, max: 14, step: 0.1, unit: "%" },
  { key: "tax_rate", label: "Tax rate", min: 5, max: 45, step: 0.1, unit: "%" },
  { key: "terminal_growth", label: "Terminal growth g", min: 1, max: 8, step: 0.1, unit: "%" },
  { key: "exit_multiple", label: "Exit EV/EBITDA", min: 4, max: 15, step: 0.5, unit: "x" },
  { key: "current_price", label: "Current price", min: 20, max: 500, step: 1, unit: "Rs" },
];

export default function ValuationPage() {
  const { id } = useParams<{ id: string }>();
  const [assumptions, setAssumptions] = useState(DEFAULT_ASSUMPTIONS);
  const [forecast, setForecast] = useState(DEFAULT_FORECAST);
  const [report, setReport] = useState<ValuationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
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
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [id, assumptions, forecast]);

  const vsCurrent = useMemo(() => {
    if (!report) return null;
    const fair = report.dcf.bridge.per_share_inr;
    const price = assumptions.current_price;
    return (fair / price - 1) * 100;
  }, [report, assumptions.current_price]);

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <div className="space-y-4">
        <Card title="Assumptions">
          <div className="space-y-4">
            {SLIDERS.map((s) => (
              <Slider key={s.key} spec={s} value={assumptions[s.key] as number}
                onChange={(v) => setAssumptions((a) => ({ ...a, [s.key]: v }))} />
            ))}
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={assumptions.mid_year}
                onChange={(e) => setAssumptions((a) => ({ ...a, mid_year: e.target.checked }))} />
              mid-year discounting convention
            </label>
          </div>
        </Card>

        <Card title="Forecast drivers">
          <YearList label="Revenue growth" unit="%" values={forecast.revenue_growth}
            min={-5} max={25} step={0.5}
            onChange={(values) => setForecast((f) => ({ ...f, revenue_growth: values }))} />
          <YearList label="EBITDA margin" unit="%" values={forecast.ebitda_margin}
            min={5} max={35} step={0.1}
            onChange={(values) => setForecast((f) => ({ ...f, ebitda_margin: values }))} />
          <YearList label="Capex % revenue" unit="%" values={forecast.capex_pct_revenue}
            min={1} max={15} step={0.5}
            onChange={(values) => setForecast((f) => ({ ...f, capex_pct_revenue: values }))} />
          <div className="mt-2 flex justify-end">
            <Button tone="ghost" onClick={() => {
              setAssumptions(DEFAULT_ASSUMPTIONS);
              setForecast(DEFAULT_FORECAST);
            }}>Reset to base case</Button>
          </div>
        </Card>
      </div>

      <div className="space-y-4">
        {error && <div className="panel border-rose-500/40 p-4 text-rose-300">{error}</div>}

        <StateViews data={report} error={null} isLoading={pending && !report}
          isEmpty={() => report === null}>
          {(r) => (
            <>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <Kpi label="Fair value / share" value={formatSharePrice(r.dcf.bridge.per_share_inr)} />
                <Kpi label="vs current price"
                  value={vsCurrent === null ? "—" : `${vsCurrent >= 0 ? "+" : ""}${vsCurrent.toFixed(0)}%`}
                  tone={vsCurrent !== null && vsCurrent >= 0 ? "text-emerald-400" : "text-rose-400"} />
                <Kpi label="WACC" value={`${(r.wacc * 100).toFixed(2)}%`} />
                <Kpi label="Enterprise value" value={formatInr(r.dcf.bridge.enterprise_value, 0)} />
              </div>

              <Card title="EV bridge">
                <BridgeWaterfall bridge={r.dcf.bridge} />
              </Card>

              <div className="grid gap-4 lg:grid-cols-3">
                {Object.entries(r.scenarios).map(([name, s]) => (
                  <div key={name} className="panel p-4">
                    <div className="text-xs uppercase tracking-wide text-slate-400">{name}</div>
                    <div className="mt-1 text-xl font-semibold">{formatSharePrice(s.per_share_inr)}</div>
                    <div className="text-xs text-slate-500">equity {formatInr(s.equity_value, 0)}</div>
                  </div>
                ))}
              </div>

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
                <p className="mt-2 text-xs text-slate-500">{r.dcf.checks.tv_share_of_ev.detail}</p>
              </Card>

              <Card title="Forecast rows">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-400">
                      {["yr", "revenue", "EBITDA", "NOPAT", "capex", "FCFF", "DF", "PV"].map((h) => (
                        <th key={h} className="p-1.5 text-right">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {r.dcf.rows.map((row) => (
                      <tr key={row.year} className="border-t border-slate-800">
                        <td className="p-1.5 text-right">{row.year}</td>
                        <td className="p-1.5 text-right">{row.revenue.toFixed(0)}</td>
                        <td className="p-1.5 text-right">{row.ebitda.toFixed(0)}</td>
                        <td className="p-1.5 text-right">{row.nopat.toFixed(0)}</td>
                        <td className="p-1.5 text-right">{row.capex.toFixed(0)}</td>
                        <td className="p-1.5 text-right">{row.fcff.toFixed(0)}</td>
                        <td className="p-1.5 text-right">{row.discount_factor.toFixed(3)}</td>
                        <td className="p-1.5 text-right">{row.pv.toFixed(0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </StateViews>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="panel p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>{value}</div>
    </div>
  );
}

function Slider({ spec, value, onChange }: {
  spec: SliderSpec; value: number; onChange: (v: number) => void;
}) {
  return (
    <label className="block text-sm">
      <div className="flex justify-between text-slate-300">
        <span>{spec.label}</span>
        <span className="font-mono text-sky-300">{value}{spec.unit}</span>
      </div>
      <input type="range" className="mt-1 w-full" min={spec.min} max={spec.max}
        step={spec.step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))} />
    </label>
  );
}

function YearList({ label, unit, values, min, max, step, onChange }: {
  label: string; unit: string; values: number[]; min: number; max: number;
  step: number; onChange: (values: number[]) => void;
}) {
  return (
    <div className="mb-3 text-sm">
      <div className="text-slate-300">{label} ({unit}, Y1..Y5)</div>
      <div className="mt-1 grid grid-cols-5 gap-1">
        {values.map((v, i) => (
          <input key={i} type="number" className="rounded bg-slate-800 p-1 text-right text-xs"
            value={v} min={min} max={max} step={step}
            onChange={(e) => {
              const next = [...values];
              next[i] = parseFloat(e.target.value) || 0;
              onChange(next);
            }} />
        ))}
      </div>
    </div>
  );
}
