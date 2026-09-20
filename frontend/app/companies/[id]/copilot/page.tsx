"use client";

import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useQuery } from "@tanstack/react-query";
import { api, CopilotPayload } from "@/lib/api";
import { Button, Chip } from "@/components/ui";
import { CitationList, VerdictBadge } from "@/components/citation";

interface Turn {
  role: "user" | "assistant";
  content: string;
  payload?: CopilotPayload;
}

const SUGGESTED = [
  "What was NovaTech's revenue in FY2025?",
  "Why did EBITDA margin decline in FY2023?",
  "What is customer concentration risk?",
  "What are the major debt obligations?",
];

/** Copilot chat: SSE streaming, markdown, citation cards, verdict (P5.5). */
export default function CopilotPage() {
  const { id } = useParams<{ id: string }>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filings = useQuery({
    queryKey: ["filings", id],
    queryFn: async () => {
      const res = await fetch(`${API_BASE()}/companies/${id}/filings`);
      return res.json() as Promise<{ id: string }[]>;
    },
  });
  const filingId = filings.data?.[0]?.id;

  async function ask(q: string) {
    if (!q.trim() || streaming) return;
    setQuestion("");
    setTurns((t) => [...t, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setStreaming(true);
    try {
      const payload = await copilotStreamWrap(
        id, q,
        (delta) => setTurns((t) => {
          const copy = [...t];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content: copy[copy.length - 1].content + delta,
          };
          return copy;
        }),
      );
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = { role: "assistant", content: payload.answer, payload };
        return copy;
      });
    } catch (err) {
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          content: `Stream failed: ${(err as Error).message}`,
        };
        return copy;
      });
    } finally {
      setStreaming(false);
      scrollRef.current?.scrollTo({ top: 1e9 });
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Copilot</h1>
        <span className="text-xs text-slate-500">grounded Q&amp;A over the filed annual report</span>
      </header>

      <div ref={scrollRef} className="panel min-h-[400px] space-y-4 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">Ask about the filing — every claim is citation-checked.</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED.map((s) => (
                <button key={s} onClick={() => ask(s)}
                  className="rounded-full border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:border-sky-500">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className={turn.role === "user" ? "text-right" : ""}>
            <div className={`inline-block max-w-[90%] rounded-lg px-3 py-2 text-sm ${
              turn.role === "user" ? "bg-sky-600/20 text-sky-100" : "bg-slate-800 text-slate-100"}`}>
              {turn.role === "assistant"
                ? <ReactMarkdown>{turn.content || "…"}</ReactMarkdown>
                : turn.content}
            </div>
            {turn.payload && (
              <div className="mt-2">
                <CitationList payload={turn.payload} filingId={filingId} />
              </div>
            )}
          </div>
        ))}
      </div>

      <form className="flex gap-2" onSubmit={(e) => {
        e.preventDefault();
        ask(question);
      }}>
        <input className="flex-1 rounded-lg bg-slate-800 p-2 text-sm outline-none focus:ring-1 focus:ring-sky-500"
          placeholder="Ask a question about the filing…"
          value={question} onChange={(e) => setQuestion(e.target.value)} />
        <Button type="submit" disabled={streaming || !question.trim()}>
          {streaming ? "…" : "Ask"}
        </Button>
      </form>

      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Chip tone="info">temperature 0.1</Chip>
        <span>the copilot never computes numbers — it quotes the deterministic FACTS table</span>
      </div>
    </div>
  );
}

function API_BASE() {
  return process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
}

async function copilotStreamWrap(companyId: string, question: string,
                                 onToken: (delta: string) => void) {
  const { copilotStream } = await import("@/lib/api");
  return copilotStream(companyId, question, onToken);
}
