"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, Tooltip,
  XAxis, YAxis,
} from "recharts";
import { formatInr, formatPercent } from "@/lib/format";
import { ValuationReport } from "@/lib/api";

/** Charts (Playbook P5.1): one hue family, consistent axes. */

const ACCENT = "#38bdf8";
const ACCENT_SOFT = "#818cf8";

export function TrendChart({ periods, series }: {
  periods: string[]; series: { key: string; values: (number | null)[] }[];
}) {
  const data = periods.map((period, i) => {
    const row: Record<string, number | string> = { period };
    for (const s of series) row[s.key] = s.values[i] ?? 0;
    return row;
  });
  return (
    <AreaChart width={640} height={240} data={data}>
      <defs>
        <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={ACCENT} stopOpacity={0.5} />
          <stop offset="100%" stopColor={ACCENT} stopOpacity={0.05} />
        </linearGradient>
      </defs>
      <CartesianGrid stroke="#1e293b" />
      <XAxis dataKey="period" stroke="#64748b" fontSize={11} />
      <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
      {series.map((s, i) => (
        <Area key={s.key} type="monotone" dataKey={s.key} stroke={i ? ACCENT_SOFT : ACCENT}
          fill={i ? "none" : "url(#g1)"} strokeWidth={2} />
      ))}
    </AreaChart>
  );
}

export function BridgeWaterfall({ bridge }: {
  bridge: ValuationReport["dcf"]["bridge"];
}) {
  const data = [
    { name: "PV explicit", value: bridge.pv_explicit },
    { name: "PV terminal", value: bridge.pv_terminal_gordon },
    { name: "Enterprise", value: bridge.enterprise_value },
    { name: "Net debt", value: -bridge.net_debt },
    { name: "Equity", value: bridge.equity_value },
  ];
  return (
    <BarChart width={640} height={240} data={data}>
      <CartesianGrid stroke="#1e293b" vertical={false} />
      <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
      <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }}
        formatter={(v: number) => formatInr(v)} />
      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
        {data.map((d, i) => (
          <Cell key={i} fill={d.value < 0 ? "#f43f5e" : i >= 3 ? ACCENT_SOFT : ACCENT} />
        ))}
      </Bar>
    </BarChart>
  );
}

export function SensitivityHeatmap({ grid }: { grid: ValuationReport["sensitivity"] }) {
  const values = grid.per_share.flat().filter((v): v is number => v !== null);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const hue = (v: number) => {
    const t = (v - min) / (max - min || 1);
    return `hsl(${200 + t * 40}, ${45 + t * 30}%, ${20 + t * 22}%)`;
  };
  return (
    <div className="overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr>
            <th className="p-1.5 text-left text-slate-400">WACC \ g</th>
            {grid.g_axis.map((g) => (
              <th key={g} className="p-1.5 text-right text-slate-400">{g.toFixed(1)}%</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.per_share.map((row, i) => (
            <tr key={i}>
              <td className="p-1.5 text-slate-400">{grid.wacc_axis[i].toFixed(2)}%</td>
              {row.map((v, j) => (
                <td key={j} className="p-1.5 text-right font-mono"
                  style={v === null ? undefined : { background: hue(v), color: "#e2e8f0" }}>
                  {v === null ? "—" : v.toFixed(0)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TornadoChart({ tornado }: { tornado: ValuationReport["tornado"] }) {
  const data = tornado.slice(0, 7);
  return (
    <BarChart width={640} height={260} data={data} layout="vertical">
      <CartesianGrid stroke="#1e293b" horizontal={false} />
      <XAxis type="number" stroke="#64748b" fontSize={11} />
      <YAxis type="category" dataKey="driver" stroke="#64748b" fontSize={11} width={110} />
      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
      <Legend wrapperStyle={{ fontSize: 11 }} />
      <Bar dataKey="high" name="favorable" fill={ACCENT} radius={[0, 4, 4, 0]} />
      <Bar dataKey="low" name="unfavorable" fill="#f43f5e" radius={[0, 4, 4, 0]} />
    </BarChart>
  );
}

export function FcfVsEbitda({ periods, fcf, ebitda }: {
  periods: string[]; fcf: (number | null)[]; ebitda: (number | null)[];
}) {
  const data = periods.map((period, i) => ({
    period, fcf: fcf[i] ?? 0, ebitda: ebitda[i] ?? 0,
  }));
  return (
    <BarChart width={640} height={240} data={data}>
      <CartesianGrid stroke="#1e293b" vertical={false} />
      <XAxis dataKey="period" stroke="#64748b" fontSize={11} />
      <YAxis stroke="#64748b" fontSize={11} />
      <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }}
        formatter={(v: number) => formatInr(v)} />
      <Legend wrapperStyle={{ fontSize: 11 }} />
      <Bar dataKey="ebitda" name="EBITDA" fill={ACCENT} radius={[4, 4, 0, 0]} />
      <Bar dataKey="fcf" name="FCF" fill="#f43f5e" radius={[4, 4, 0, 0]} />
    </BarChart>
  );
}

export function MarginLine({ periods, margins }: {
  periods: string[]; margins: (number | null)[];
}) {
  const data = periods.map((period, i) => ({ period, margin: margins[i] ?? 0 }));
  return (
    <div className="flex items-center gap-2">
      <AreaChart width={280} height={80} data={data}>
        <XAxis dataKey="period" hide />
        <YAxis hide domain={[0, 0.3]} />
        <Line type="monotone" dataKey="margin" stroke={ACCENT_SOFT} strokeWidth={2} dot={false} />
      </AreaChart>
      <span className="text-xs text-slate-400">EBITDA margin {formatPercent(margins.at(-1))}</span>
    </div>
  );
}
