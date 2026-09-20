"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, BulkResult, ReviewItem, ReviewStats } from "@/lib/api";
import { Button, Chip, StateViews } from "@/components/ui";
import Link from "next/link";

/** Review queue: bulk actions + individual approve/reject. */
export default function ReviewPage() {
  const queryClient = useQueryClient();

  const queue = useQuery({ queryKey: ["review"],      queryFn: api.reviewQueue });
  const stats = useQuery({ queryKey: ["reviewStats"], queryFn: api.reviewStats });

  const [bulkResult, setBulkResult] = useState<BulkResult | null>(null);
  const [threshold, setThreshold]   = useState(0.7);

  const bulk = useMutation({
    mutationFn: ({ action, thr }: { action: string; thr?: number }) =>
      api.reviewBulk(action, thr ?? threshold),
    onSuccess: (res) => {
      setBulkResult(res);
      queryClient.invalidateQueries({ queryKey: ["review"] });
      queryClient.invalidateQueries({ queryKey: ["reviewStats"] });
      queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
  });

  const decide = useMutation({
    mutationFn: ({ item, approve, value, key }: {
      item: ReviewItem; approve: boolean; value?: number; key?: string;
    }) => api.reviewItem(item.item_id, { approve, value, canonical_key: key }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review"] });
      queryClient.invalidateQueries({ queryKey: ["reviewStats"] });
    },
  });

  const s = stats.data;
  const total = s?.total ?? 0;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-[#4a6f94]">
            <Link href="/" className="hover:text-sky-400 transition-colors">Workspace</Link>
            <span>/</span>
            <span className="text-[#7a9bc0]">Review queue</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Review Queue</h1>
          <p className="mt-1 text-sm text-[#4a6f94]">
            Extractions below the 0.85 confidence threshold. Use bulk actions to clear the queue fast.
          </p>
        </div>
        {total > 0 && (
          <div className="flex items-center gap-3 rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3">
            <svg className="h-5 w-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-amber-500/70">Pending</div>
              <div className="text-lg font-bold text-amber-400">{total} items</div>
            </div>
          </div>
        )}
      </div>

      {/* Stats + Bulk action bar */}
      {s && total > 0 && (
        <div className="panel p-5 space-y-4">
          {/* Breakdown */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatBox label="Total pending" value={s.total} color="amber" />
            <StatBox label="High confidence (≥0.7)" value={s.high_confidence} color="emerald"
              sub="safe to bulk-approve" />
            <StatBox label="Unmapped labels" value={s.unmapped} color="rose"
              sub="ambiguous rows" />
            <StatBox label="Need manual review" value={s.manual_required} color="sky"
              sub="< 0.7 confidence" />
          </div>

          {/* Bulk action buttons */}
          <div className="border-t border-[#1e3a5f] pt-4">
            <div className="mb-3 flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-widest text-[#4a6f94]">
                Bulk actions
              </span>
              <span className="text-xs text-[#2a5080]">— resolve many items at once</span>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {/* Approve high-confidence */}
              <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5">
                <div>
                  <div className="text-xs text-emerald-300 font-medium">
                    Approve ≥ {(threshold * 100).toFixed(0)}% confidence
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="range" min={0.5} max={0.84} step={0.01}
                      value={threshold}
                      onChange={(e) => setThreshold(parseFloat(e.target.value))}
                      className="w-28"
                    />
                    <span className="mono text-xs text-emerald-400">{s.high_confidence} items</span>
                  </div>
                </div>
                <Button onClick={() => bulk.mutate({ action: "approve_above", thr: threshold })}
                  disabled={bulk.isPending || s.high_confidence === 0}>
                  <span className="flex items-center gap-1.5">
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Approve {s.high_confidence}
                  </span>
                </Button>
              </div>

              {/* Reject unmapped */}
              {s.unmapped > 0 && (
                <div className="flex items-center gap-2 rounded-xl border border-rose-500/20 bg-rose-500/5 px-4 py-2.5">
                  <div>
                    <div className="text-xs text-rose-300 font-medium">Reject all unmapped</div>
                    <div className="text-xs text-[#4a6f94]">Ambiguous rows with no canonical key</div>
                  </div>
                  <Button tone="danger"
                    onClick={() => bulk.mutate({ action: "reject_unmapped" })}
                    disabled={bulk.isPending}>
                    <span className="flex items-center gap-1.5">
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      Reject {s.unmapped}
                    </span>
                  </Button>
                </div>
              )}

              {/* Approve all */}
              <div className="flex items-center gap-2 rounded-xl border border-[#1e3a5f] bg-[#0f2035] px-4 py-2.5">
                <div>
                  <div className="text-xs text-[#7a9bc0] font-medium">Approve everything</div>
                  <div className="text-xs text-[#4a6f94]">Trust the extractor for all {s.total} items</div>
                </div>
                <Button tone="ghost"
                  onClick={() => bulk.mutate({ action: "approve_all" })}
                  disabled={bulk.isPending}>
                  Approve all {s.total}
                </Button>
              </div>
            </div>

            {bulk.isPending && (
              <div className="mt-3 flex items-center gap-2 text-xs text-sky-400">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-sky-400/30 border-t-sky-400" />
                Processing bulk action…
              </div>
            )}
          </div>

          {/* Bulk result toast */}
          {bulkResult && (
            <div className="mt-2 flex items-center justify-between rounded-lg border border-emerald-500/25 bg-emerald-500/8 px-4 py-2.5 animate-fade-in">
              <div className="text-sm text-emerald-300">
                <span className="font-semibold">{bulkResult.action}</span>
                {bulkResult.approved > 0 && ` · ${bulkResult.approved} approved`}
                {bulkResult.rejected > 0 && ` · ${bulkResult.rejected} rejected`}
                {bulkResult.filings_resumed.length > 0 &&
                  ` · ${bulkResult.filings_resumed.length} filing(s) resumed`}
              </div>
              <button onClick={() => setBulkResult(null)}
                className="text-[#4a6f94] hover:text-white transition-colors text-xs">
                Dismiss
              </button>
            </div>
          )}
        </div>
      )}

      {/* Individual queue */}
      <StateViews
        data={queue.data}
        error={queue.error}
        isLoading={queue.isLoading}
        isEmpty={(d) => d.length === 0}
      >
        {(items) => {
          // Group by confidence tier for scannable display.
          const manual = items.filter(i => i.confidence < threshold && !i.canonical_key.startsWith("unmapped:"));
          const unmapped = items.filter(i => i.canonical_key.startsWith("unmapped:"));
          const high = items.filter(i => i.confidence >= threshold);

          return (
            <div className="space-y-6">
              {high.length > 0 && (
                <ItemGroup label={`High confidence (${high.length})`} color="emerald"
                  hint="These can be bulk-approved above.">
                  {high.map((item, i) => (
                    <ReviewRow key={item.item_id} item={item} index={i}
                      onDecide={(a, v, k) => decide.mutate({ item, approve: a, value: v, key: k })} />
                  ))}
                </ItemGroup>
              )}

              {manual.length > 0 && (
                <ItemGroup label={`Manual review required (${manual.length})`} color="sky"
                  hint="Confidence < 70% — check the value and label before approving.">
                  {manual.map((item, i) => (
                    <ReviewRow key={item.item_id} item={item} index={i}
                      onDecide={(a, v, k) => decide.mutate({ item, approve: a, value: v, key: k })} />
                  ))}
                </ItemGroup>
              )}

              {unmapped.length > 0 && (
                <ItemGroup label={`Unmapped labels (${unmapped.length})`} color="rose"
                  hint="No canonical key found — reject or reassign manually.">
                  {unmapped.map((item, i) => (
                    <ReviewRow key={item.item_id} item={item} index={i}
                      onDecide={(a, v, k) => decide.mutate({ item, approve: a, value: v, key: k })} />
                  ))}
                </ItemGroup>
              )}
            </div>
          );
        }}
      </StateViews>
    </div>
  );
}

function StatBox({ label, value, color, sub }: {
  label: string; value: number; color: string; sub?: string;
}) {
  const colors: Record<string, string> = {
    amber:   "text-amber-400 bg-amber-500/8 border-amber-500/20",
    emerald: "text-emerald-400 bg-emerald-500/8 border-emerald-500/20",
    rose:    "text-rose-400 bg-rose-500/8 border-rose-500/20",
    sky:     "text-sky-400 bg-sky-500/8 border-sky-500/20",
  };
  return (
    <div className={`rounded-xl border p-3 ${colors[color] ?? colors.sky}`}>
      <div className="text-[10px] uppercase tracking-wide opacity-70">{label}</div>
      <div className={`mono mt-1 text-2xl font-bold`}>{value}</div>
      {sub && <div className="mt-0.5 text-[10px] opacity-60">{sub}</div>}
    </div>
  );
}

function ItemGroup({ label, color, hint, children }: {
  label: string; color: string; hint: string; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const borderColors: Record<string, string> = {
    emerald: "border-emerald-500/30",
    sky:     "border-sky-500/30",
    rose:    "border-rose-500/30",
  };
  const textColors: Record<string, string> = {
    emerald: "text-emerald-400",
    sky:     "text-sky-400",
    rose:    "text-rose-400",
  };
  return (
    <div className={`rounded-xl border ${borderColors[color] ?? "border-[#1e3a5f]"} overflow-hidden`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between bg-[#0d1929] px-5 py-3 hover:bg-[#0f2035] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className={`text-sm font-semibold ${textColors[color] ?? "text-white"}`}>{label}</span>
          <span className="text-xs text-[#4a6f94]">{hint}</span>
        </div>
        <svg className={`h-4 w-4 text-[#4a6f94] transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="divide-y divide-[#1e3a5f]">
          {children}
        </div>
      )}
    </div>
  );
}

function ReviewRow({ item, index, onDecide }: {
  item: ReviewItem;
  index: number;
  onDecide: (approve: boolean, value?: number, key?: string) => void;
}) {
  const [value, setValue] = useState(item.value);
  const [key,   setKey]   = useState(item.canonical_key);
  const isAmbiguous = item.canonical_key.startsWith("unmapped:");
  const conf = item.confidence;
  const confColor = conf >= 0.8 ? "#34d399" : conf >= 0.6 ? "#f59e0b" : "#f43f5e";

  return (
    <div className="flex flex-wrap items-center gap-4 bg-[#0f2035]/50 px-5 py-3.5
                    hover:bg-[#0f2035] transition-colors animate-slide-up"
         style={{ animationDelay: `${index * 20}ms` }}>

      {/* Confidence ring */}
      <ConfidenceRing value={conf} color={confColor} />

      {/* Raw label + period */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-white truncate">{item.raw_label}</span>
          <span className="rounded-full bg-[#0d1929] border border-[#1e3a5f] px-2 py-0.5 text-[10px] text-[#4a6f94]">
            {item.period} · {item.statement_type.toUpperCase()} · p{item.page_no ?? "?"}
          </span>
          {isAmbiguous && <Chip tone="warn">Unmapped</Chip>}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-[#2a5080]">Key:</span>
            <input
              className="mono rounded border border-[#1e3a5f] bg-[#060d1a] px-2 py-0.5 text-xs text-[#e2ecf7] focus:border-sky-500/50 focus:outline-none w-44"
              defaultValue={key}
              onBlur={(e) => setKey(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-[#2a5080]">Value:</span>
            <input
              type="number"
              className="mono rounded border border-[#1e3a5f] bg-[#060d1a] px-2 py-0.5 text-right text-xs text-[#e2ecf7] focus:border-sky-500/50 focus:outline-none w-24"
              defaultValue={value}
              onBlur={(e) => setValue(parseFloat(e.target.value))}
            />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-1.5 shrink-0">
        <button
          onClick={() => onDecide(true,
            value !== item.value ? value : undefined,
            key   !== item.canonical_key ? key : undefined,
          )}
          className="flex items-center gap-1 rounded-lg bg-emerald-500/10 border border-emerald-500/25 px-3 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-colors"
        >
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          OK
        </button>
        <button
          onClick={() => onDecide(false)}
          className="flex items-center gap-1 rounded-lg bg-rose-500/10 border border-rose-500/25 px-3 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/20 transition-colors"
        >
          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
          Skip
        </button>
      </div>
    </div>
  );
}

function ConfidenceRing({ value, color }: { value: number; color: string }) {
  const r = 14, cx = 16, cy = 16;
  const circ = 2 * Math.PI * r;
  const dash = circ * value;
  return (
    <svg width={32} height={32} viewBox="0 0 32 32" className="shrink-0">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1e3a5f" strokeWidth={2.5} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={2.5}
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ * 0.25}
        style={{ transition: "stroke-dasharray 0.4s ease" }} />
      <text x={cx} y={cy + 4} textAnchor="middle" fontSize="7" fill={color} fontFamily="monospace">
        {Math.round(value * 100)}
      </text>
    </svg>
  );
}
