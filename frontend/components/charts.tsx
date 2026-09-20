"use client";

import { useEffect, useRef } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { formatInr, formatPercent } from "@/lib/format";
import { ValuationReport } from "@/lib/api";

/** Charts — responsive, premium dark theme, consistent accent family. */

const C = {
  accent:  "#38bdf8",
  accent2: "#818cf8",
  accent3: "#34d399",
  danger:  "#f43f5e",
  grid:    "#1e3a5f",
  axis:    "#4a6f94",
  tooltip: { bg: "#0d1929", border: "#1e3a5f" },
};

const TOOLTIP_STYLE = {
  contentStyle: {
    background: C.tooltip.bg,
    border: `1px solid ${C.tooltip.border}`,
    borderRadius: "0.5rem",
    fontSize: "12px",
    color: "#e2ecf7",
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
  cursor: { stroke: C.accent, strokeWidth: 1, strokeDasharray: "4 4" },
};

const AXIS_PROPS = {
  stroke: "transparent",
  tick: { fill: C.axis, fontSize: 11 },
  tickLine: false,
};

export function TrendChart({ periods, series }: {
  periods: string[];
  series: { key: string; values: (number | null)[] }[];
}) {
  const data = periods.map((period, i) => {
    const row: Record<string, number | string> = { period };
    for (const s of series) row[s.key] = s.values[i] ?? 0;
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="g-accent" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={C.accent}  stopOpacity={0.3} />
            <stop offset="100%" stopColor={C.accent}  stopOpacity={0}   />
          </linearGradient>
          <linearGradient id="g-accent2" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={C.accent2} stopOpacity={0.25} />
            <stop offset="100%" stopColor={C.accent2} stopOpacity={0}    />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="period" {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} width={42} />
        <Tooltip {...TOOLTIP_STYLE} />
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            stroke={i ? C.accent2 : C.accent}
            fill={i ? "url(#g-accent2)" : "url(#g-accent)"}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: i ? C.accent2 : C.accent, strokeWidth: 0 }}
          />
        ))}
        <Legend
          wrapperStyle={{ fontSize: 11, color: C.axis, paddingTop: 8 }}
          iconType="circle"
          iconSize={8}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function BridgeWaterfall({ bridge }: {
  bridge: ValuationReport["dcf"]["bridge"];
}) {
  const data = [
    { name: "PV Explicit", value: bridge.pv_explicit,            color: C.accent },
    { name: "PV Terminal", value: bridge.pv_terminal_gordon,     color: C.accent2 },
    { name: "Enterprise",  value: bridge.enterprise_value,       color: C.accent3 },
    { name: "Net Debt",    value: -bridge.net_debt,              color: C.danger  },
    { name: "Equity",      value: bridge.equity_value,           color: C.accent  },
  ];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} width={42} />
        <Tooltip
          {...TOOLTIP_STYLE}
          formatter={(v: number) => [formatInr(v), ""]}
        />
        <Bar dataKey="value" radius={[5, 5, 0, 0]} maxBarSize={60}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.color} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SensitivityHeatmap({ grid }: { grid: ValuationReport["sensitivity"] }) {
  const values = grid.per_share.flat().filter((v): v is number => v !== null);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const hue = (v: number) => {
    const t = (v - min) / (max - min || 1);
    if (t < 0.5) return `hsl(${210 + t * 40}, 60%, ${18 + t * 14}%)`;
    return `hsl(${175 + (1 - t) * 35}, ${50 + t * 30}%, ${22 + t * 16}%)`;
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="p-2 text-left text-[#4a6f94]">WACC \ g</th>
            {grid.g_axis.map((g) => (
              <th key={g} className="p-2 text-right font-medium text-[#4a6f94]">{g.toFixed(1)}%</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.per_share.map((row, i) => (
            <tr key={i}>
              <td className="p-2 font-medium text-[#4a6f94]">{grid.wacc_axis[i].toFixed(2)}%</td>
              {row.map((v, j) => (
                <td
                  key={j}
                  className="mono p-2 text-right transition-all"
                  style={v === null ? undefined : {
                    background: hue(v),
                    color: "#e2ecf7",
                    borderRadius: "4px",
                  }}
                >
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
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" {...AXIS_PROPS} />
        <YAxis type="category" dataKey="driver" {...AXIS_PROPS} width={120} />
        <Tooltip {...TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11, color: C.axis }} iconType="circle" iconSize={8} />
        <Bar dataKey="high" name="Favorable"   fill={C.accent3} radius={[0, 5, 5, 0]} maxBarSize={20} />
        <Bar dataKey="low"  name="Unfavorable" fill={C.danger}  radius={[0, 5, 5, 0]} maxBarSize={20} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function FcfVsEbitda({ periods, fcf, ebitda }: {
  periods: string[]; fcf: (number | null)[]; ebitda: (number | null)[];
}) {
  const data = periods.map((period, i) => ({
    period, fcf: fcf[i] ?? 0, ebitda: ebitda[i] ?? 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="period" {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} width={42} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => [formatInr(v), ""]} />
        <Legend wrapperStyle={{ fontSize: 11, color: C.axis, paddingTop: 8 }} iconType="circle" iconSize={8} />
        <Bar dataKey="ebitda" name="EBITDA" fill={C.accent}  radius={[5, 5, 0, 0]} maxBarSize={32} />
        <Bar dataKey="fcf"    name="FCF"    fill={C.accent2} radius={[5, 5, 0, 0]} maxBarSize={32} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MarginLine({ periods, margins }: {
  periods: string[]; margins: (number | null)[];
}) {
  const data = periods.map((period, i) => ({ period, margin: margins[i] ?? 0 }));
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1">
        <ResponsiveContainer width="100%" height={56}>
          <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
            <defs>
              <linearGradient id="mg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={C.accent2} stopOpacity={0.3} />
                <stop offset="100%" stopColor={C.accent2} stopOpacity={0}   />
              </linearGradient>
            </defs>
            <XAxis dataKey="period" hide />
            <YAxis hide domain={[0, 0.3]} />
            <Area type="monotone" dataKey="margin" stroke={C.accent2} fill="url(#mg)" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <span className="mono text-sm text-[#7a9bc0]">
        {formatPercent(margins.at(-1))}
      </span>
    </div>
  );
}
