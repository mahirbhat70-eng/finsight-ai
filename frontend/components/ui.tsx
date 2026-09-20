"use client";

import { ReactNode } from "react";

/** Design system primitives (Playbook P5.1): dark slate, one accent family. */

export function Card({ title, children, actions, className = "" }: {
  title?: string; children: ReactNode; actions?: ReactNode; className?: string;
}) {
  return (
    <section className={`panel p-4 ${className}`}>
      {title && (
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wide text-slate-300 uppercase">
            {title}
          </h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function KpiCard({ label, value, delta, sparkline }: {
  label: string; value: string; delta?: string; sparkline?: number[];
}) {
  const up = delta?.startsWith("+");
  return (
    <div className="panel p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-50">{value}</div>
      {delta && (
        <div className={`mt-1 text-xs font-medium ${up ? "text-emerald-400" : "text-rose-400"}`}>
          {delta}
        </div>
      )}
      {sparkline && sparkline.length > 1 && <Sparkline values={sparkline} />}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / span) * 24}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 30" className="mt-2 h-8 w-full" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="#38bdf8" strokeWidth="1.5" />
    </svg>
  );
}

export function Chip({ tone, children }: { tone: "ok" | "warn" | "info" | "high" | "medium"; children: ReactNode }) {
  const tones = {
    ok: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    warn: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    info: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    high: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    medium: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  } as const;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Button({ children, onClick, tone = "primary", disabled, type = "button" }: {
  children: ReactNode; onClick?: () => void; tone?: "primary" | "ghost" | "danger";
  disabled?: boolean; type?: "button" | "submit";
}) {
  const tones = {
    primary: "bg-sky-600 hover:bg-sky-500 text-white",
    ghost: "bg-transparent border border-slate-600 text-slate-300 hover:border-sky-500",
    danger: "bg-rose-600/80 hover:bg-rose-500 text-white",
  } as const;
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:opacity-40 ${tones[tone]}`}>
      {children}
    </button>
  );
}

/** Four-state wrapper (Playbook constraint: loading/empty/error/loaded). */
export function StateViews<T>({ data, error, isLoading, isEmpty, children }: {
  data: T | undefined; error: unknown; isLoading: boolean;
  isEmpty: (data: T) => boolean; children: (data: T) => ReactNode;
}) {
  if (isLoading) {
    return <div className="panel animate-pulse p-8 text-center text-slate-400">Loading…</div>;
  }
  if (error) {
    return (
      <div className="panel border-rose-500/40 p-8 text-center text-rose-300">
        Something failed: {String((error as Error)?.message ?? error)}
      </div>
    );
  }
  if (!data || isEmpty(data)) {
    return <div className="panel p-8 text-center text-slate-400">No data yet — upload a filing first.</div>;
  }
  return <>{children(data)}</>;
}
