"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ReviewItem } from "@/lib/api";
import { Button, StateViews } from "@/components/ui";

/** Review queue (P5.6): inline edit + approve; job resumes when clear. */
export default function ReviewPage() {
  const queryClient = useQueryClient();
  const queue = useQuery({ queryKey: ["review"], queryFn: api.reviewQueue });

  const decide = useMutation({
    mutationFn: ({ item, approve, value, key }: {
      item: ReviewItem; approve: boolean; value?: number; key?: string;
    }) => api.reviewItem(item.item_id, {
      approve, value, canonical_key: key,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["review"] }),
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Review queue</h1>
        <p className="text-sm text-slate-400">
          Low-confidence extractions below 0.85. Approve, correct the value or key,
          or reject. The ingestion job resumes once everything is resolved.
        </p>
      </header>

      <StateViews data={queue.data} error={queue.error} isLoading={queue.isLoading}
        isEmpty={(d) => d.length === 0}>
        {(items) => (
          <table className="panel w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-xs uppercase text-slate-400">
                <th className="p-3">Raw label</th>
                <th className="p-3">Suggested key</th>
                <th className="p-3">Value</th>
                <th className="p-3">Confidence</th>
                <th className="p-3">Period / page</th>
                <th className="p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <Row key={item.item_id} item={item}
                  onDecide={(approve, value, key) =>
                    decide.mutate({ item, approve, value, key })} />
              ))}
            </tbody>
          </table>
        )}
      </StateViews>
    </div>
  );
}

function Row({ item, onDecide }: {
  item: ReviewItem;
  onDecide: (approve: boolean, value?: number, key?: string) => void;
}) {
  const [value, setValue] = useState(item.value);
  const [key, setKey] = useState(item.canonical_key);
  const suggested = item.canonical_key.startsWith("unmapped:")
    ? "— (ambiguous row)" : item.canonical_key;

  return (
    <tr className="border-b border-slate-800">
      <td className="p-3">{item.raw_label}</td>
      <td className="p-3">
        <input className="w-40 rounded bg-slate-800 p-1 text-xs"
          defaultValue={key} onBlur={(e) => setKey(e.target.value)} />
        <div className="text-xs text-slate-500">suggested: {suggested}</div>
      </td>
      <td className="p-3">
        <input className="w-24 rounded bg-slate-800 p-1 text-right text-xs" type="number"
          defaultValue={value} onBlur={(e) => setValue(parseFloat(e.target.value))} />
      </td>
      <td className="p-3">
        <div className="h-2 w-24 overflow-hidden rounded bg-slate-800">
          <div className="h-full bg-amber-500" style={{ width: `${item.confidence * 100}%` }} />
        </div>
        <span className="text-xs text-slate-500">{item.confidence.toFixed(2)} ({item.method})</span>
      </td>
      <td className="p-3 text-xs text-slate-400">
        {item.period} · p{item.page_no ?? "?"}
      </td>
      <td className="space-x-2 p-3">
        <Button onClick={() => onDecide(true, value !== item.value ? value : undefined,
          key !== item.canonical_key ? key : undefined)}>Approve</Button>
        <Button tone="danger" onClick={() => onDecide(false)}>Reject</Button>
      </td>
    </tr>
  );
}
