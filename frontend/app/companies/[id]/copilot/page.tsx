"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useQuery } from "@tanstack/react-query";
import { api, CopilotPayload } from "@/lib/api";
import { Button, Chip } from "@/components/ui";
import { CitationList, VerdictBadge } from "@/components/citation";
import Link from "next/link";

interface Turn {
  role: "user" | "assistant";
  content: string;
  payload?: CopilotPayload;
}

const SUGGESTED = [
  "What was revenue in FY2025?",
  "Why did EBITDA margin decline in FY2023?",
  "What is customer concentration risk?",
  "What are the major debt obligations?",
];

/** Copilot chat — streaming, citation cards, verdict badges. */
export default function CopilotPage() {
  const { id } = useParams<{ id: string }>();
  const [turns,     setTurns]     = useState<Turn[]>([]);
  const [question,  setQuestion]  = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLInputElement>(null);

  const filings = useQuery({
    queryKey: ["filings", id],
    queryFn:  async () => {
      const res = await fetch(`${API_BASE()}/companies/${id}/filings`);
      return res.json() as Promise<{ id: string }[]>;
    },
  });
  const filingId = filings.data?.[0]?.id;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

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
      inputRef.current?.focus();
    }
  }

  return (
    <div className="flex h-[calc(100vh-120px)] flex-col gap-0 animate-fade-in">
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-[#4a6f94]">
            <Link href="/" className="hover:text-sky-400 transition-colors">Workspace</Link>
            <span>/</span>
            <Link href={`/companies/${id}`} className="hover:text-sky-400 transition-colors">Overview</Link>
            <span>/</span>
            <span className="text-[#7a9bc0]">Copilot</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Copilot <span className="gradient-text">Q&amp;A</span>
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Chip tone="info">temp 0.1</Chip>
          <span className="text-xs text-[#4a6f94]">grounded · citation-checked</span>
        </div>
      </div>

      {/* Chat area */}
      <div
        ref={scrollRef}
        className="panel flex-1 space-y-4 overflow-y-auto p-5"
        style={{ scrollBehavior: "smooth" }}
      >
        {turns.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-6 animate-fade-in">
            {/* Icon */}
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500/20 to-indigo-500/20 border border-sky-500/20">
              <svg className="h-8 w-8 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-[#7a9bc0]">Ask anything about the filing</p>
              <p className="mt-1 text-xs text-[#4a6f94]">Every claim is citation-checked against the document</p>
            </div>
            {/* Suggested prompts */}
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="rounded-full border border-[#1e3a5f] bg-[#0f2035] px-4 py-2 text-xs text-[#7a9bc0] transition-all hover:border-sky-500/40 hover:bg-sky-500/5 hover:text-sky-300"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className={`flex gap-3 animate-slide-up ${turn.role === "user" ? "flex-row-reverse" : ""}`}>
            {/* Avatar */}
            <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
              turn.role === "user"
                ? "bg-sky-600 text-white"
                : "bg-gradient-to-br from-sky-500 to-indigo-500 text-white"
            }`}>
              {turn.role === "user" ? "U" : "F"}
            </div>

            <div className={`flex max-w-[85%] flex-col gap-2 ${turn.role === "user" ? "items-end" : "items-start"}`}>
              <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                turn.role === "user"
                  ? "rounded-tr-sm bg-sky-600/20 text-[#c5d8eb] border border-sky-500/20"
                  : "rounded-tl-sm bg-[#0d1929] text-[#e2ecf7] border border-[#1e3a5f]"
              }`}>
                {turn.role === "assistant" ? (
                  <div className="prose prose-sm prose-invert max-w-none">
                    {turn.content
                      ? <ReactMarkdown>{turn.content}</ReactMarkdown>
                      : <TypingIndicator />}
                  </div>
                ) : (
                  turn.content
                )}
              </div>

              {turn.payload && (
                <div className="w-full">
                  <CitationList payload={turn.payload} filingId={filingId} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Input bar */}
      <div className="mt-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => { e.preventDefault(); ask(question); }}
        >
          <input
            ref={inputRef}
            className="flex-1 rounded-xl border border-[#1e3a5f] bg-[#0d1929] px-4 py-3 text-sm text-[#e2ecf7] placeholder-[#2a5080] outline-none transition-all focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/30"
            placeholder="Ask a question about the filing…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={streaming}
          />
          <Button type="submit" disabled={streaming || !question.trim()}>
            {streaming ? (
              <span className="flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              </span>
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-sky-400"
          style={{ animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
        />
      ))}
    </div>
  );
}

function API_BASE() {
  return process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
}

async function copilotStreamWrap(
  companyId: string, question: string,
  onToken: (delta: string) => void,
) {
  const { copilotStream } = await import("@/lib/api");
  return copilotStream(companyId, question, onToken);
}
