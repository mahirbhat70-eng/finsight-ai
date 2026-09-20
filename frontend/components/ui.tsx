"use client";

import { ReactNode } from "react";

/** Design system primitives — premium dark theme with glow accents. */

export function Card({ title, children, actions, className = "", glow = false }: {
  title?: string; children: ReactNode; actions?: ReactNode;
  className?: string; glow?: boolean;
}) {
  return (
    <section className={`panel p-4 ${glow ? "panel-glow" : ""} ${className}`}>
      {title && (
        <header className="mb-4 flex items-center justify-between">
          <h2 className="text-xs font-semibold tracking-widest text-[#4a6f94] uppercase">
            {title}
          </h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function KpiCard({ label, value, delta, sparkline, accent = false }: {
  label: string; value: string; delta?: string;
  sparkline?: (number | null)[];
  accent?: boolean;
}) {
  const up = delta?.startsWith("+");
  return (
    <div className={`panel panel-hover relative overflow-hidden p-4 transition-all duration-200 ${accent ? "panel-glow" : ""}`}>
      {/* subtle top gradient line */}
      <div className={`absolute inset-x-0 top-0 h-px ${accent ? "bg-gradient-to-r from-transparent via-sky-400 to-transparent" : "bg-gradient-to-r from-transparent via-[#1e3a5f] to-transparent"}`} />
      <div className="text-[10px] font-semibold uppercase tracking-widest text-[#4a6f94]">{label}</div>
      <div className={`mono mt-2 text-2xl font-semibold ${accent ? "gradient-text" : "text-[#e2ecf7]"}`}>{value}</div>
      {delta && (
        <div className={`mt-1.5 flex items-center gap-1 text-xs font-medium ${up ? "text-emerald-400" : "text-rose-400"}`}>
          <span>{up ? "▲" : "▼"}</span>
          <span>{delta}</span>
        </div>
      )}
      {sparkline && sparkline.length > 1 && <Sparkline values={sparkline} accent={accent} />}
    </div>
  );
}

function Sparkline({ values, accent }: { values: (number | null)[]; accent?: boolean }) {
  const clean = values.filter((v): v is number => typeof v === "number");
  if (clean.length < 2) return null;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const span = max - min || 1;
  const w = 100;
  const h = 32;
  const pts = clean
    .map((v, i) => `${(i / (clean.length - 1)) * w},${h - 4 - ((v - min) / span) * (h - 8)}`)
    .join(" ");
  const color = accent ? "#38bdf8" : "#818cf8";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 h-8 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`sg-${accent}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

const CHIP_STYLES = {
  ok:     "bg-emerald-500/10 text-emerald-300 border-emerald-500/25 shadow-emerald-500/10",
  warn:   "bg-amber-500/10  text-amber-300  border-amber-500/25  shadow-amber-500/10",
  info:   "bg-sky-500/10    text-sky-300    border-sky-500/25    shadow-sky-500/10",
  high:   "bg-rose-500/10   text-rose-300   border-rose-500/25   shadow-rose-500/10",
  medium: "bg-amber-500/10  text-amber-300  border-amber-500/25  shadow-amber-500/10",
} as const;

export function Chip({ tone, children }: {
  tone: keyof typeof CHIP_STYLES; children: ReactNode;
}) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium shadow-sm ${CHIP_STYLES[tone]}`}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, tone = "primary", disabled, type = "button" }: {
  children: ReactNode; onClick?: () => void;
  tone?: "primary" | "ghost" | "danger"; disabled?: boolean;
  type?: "button" | "submit";
}) {
  const tones = {
    primary: "bg-gradient-to-r from-sky-600 to-sky-500 hover:from-sky-500 hover:to-sky-400 text-white shadow-lg shadow-sky-600/20 hover:shadow-sky-500/30",
    ghost:   "border border-[#1e3a5f] text-[#7a9bc0] hover:border-[#2a5080] hover:text-[#e2ecf7] hover:bg-[#0f2035]",
    danger:  "bg-rose-600/80 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/20",
  } as const;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg px-4 py-2 text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

/** Four-state wrapper: loading shimmer / error / empty / data. */
export function StateViews<T>({ data, error, isLoading, isEmpty, children }: {
  data: T | undefined | null; error: unknown; isLoading: boolean;
  isEmpty: (data: NonNullable<T>) => boolean;
  children: (data: NonNullable<T>) => ReactNode;
}) {
  if (isLoading) return <LoadingSkeleton />;
  if (error) {
    return (
      <div className="panel border-rose-500/30 bg-rose-500/5 p-8 text-center animate-fade-in">
        <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/10">
          <svg className="h-5 w-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <p className="text-sm text-rose-300">{String((error as Error)?.message ?? error)}</p>
      </div>
    );
  }
  if (!data || isEmpty(data)) {
    return (
      <div className="panel p-12 text-center animate-fade-in">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#0f2035]">
          <svg className="h-6 w-6 text-[#2a5080]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <p className="text-sm text-[#4a6f94]">No data yet — upload a filing first.</p>
      </div>
    );
  }
  return <>{children(data)}</>;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 animate-fade-in">
      {[1, 2, 3].map((i) => (
        <div key={i} className="panel h-16 animate-shimmer rounded-xl" />
      ))}
    </div>
  );
}
