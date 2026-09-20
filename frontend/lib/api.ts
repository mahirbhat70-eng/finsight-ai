"use client";

/** Typed API client + SSE helper (Playbook P5.1). */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export interface Company {
  id: string;
  name: string;
  sector: string;
  currency: string;
  fiscal_year_end: string;
}

export interface MetricsResponse {
  company_id: string;
  periods: string[];
  series: Record<string, (number | null)[]>;
  metrics: Record<string, Record<string, MetricResult>>;
}

export interface MetricResult {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  formula: string;
  period: string;
}

export interface DcfRow {
  year: number;
  revenue: number;
  ebitda: number;
  ebit: number;
  nopat: number;
  capex: number;
  fcff: number;
  discount_factor: number;
  pv: number;
}

export interface ValuationReport {
  periods: string[];
  wacc: number;
  dcf: {
    rows: DcfRow[];
    bridge: {
      pv_explicit: number;
      pv_terminal_gordon: number;
      enterprise_value: number;
      net_debt: number;
      equity_value: number;
      per_share_inr: number;
      shares_mn: number;
      tv_exit_crosscheck: { ev_exit_method: number; spread_vs_gordon: number };
    };
    checks: Record<string, { value: unknown; severity: string; detail: string }>;
    nwc_days: number;
  };
  scenarios: Record<string, { per_share_inr: number; equity_value: number }>;
  sensitivity: {
    wacc_axis: number[];
    g_axis: number[];
    per_share: (number | null)[][];
  };
  tornado: { driver: string; low: number; high: number; base: number; impact: number }[];
  risk: { flags: RiskFlag[]; composite_score: number };
}

export interface RiskFlag {
  rule_id: string;
  category: string;
  severity: "high" | "medium" | "info";
  rationale: string;
  value: number | null;
  period: string | null;
}

export interface ReviewItem {
  item_id: string;
  company: string;
  company_id: string;
  filing_id: string;
  period: string;
  statement_type: string;
  canonical_key: string;
  raw_label: string;
  value: number;
  unit: string;
  confidence: number;
  method: string;
  page_no: number | null;
}

export interface ReviewStats {
  total: number;
  unmapped: number;
  high_confidence: number;
  manual_required: number;
}

export interface BulkResult {
  action: string;
  approved: number;
  rejected: number;
  filings_resumed: string[];
}

export interface Citation {
  chunk_id: string;
  doc?: string;
  page_no: number;
  quote: string;
}

export interface CopilotPayload {
  answer: string;
  citations: Citation[];
  insufficient_evidence: boolean;
  verification: { verdict: string; grounded: boolean };
  latency_ms: number;
}

export interface JobState {
  job_id: string;
  filing_id: string;
  state: string;
  progress: number;
  stage_detail: string;
  error: string | null;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  companies: () => fetch(`${API_BASE}/companies`).then(json<Company[]>),

  createCompany: (body: { name: string; sector?: string }) =>
    fetch(`${API_BASE}/companies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Company>),

  metrics: (companyId: string) =>
    fetch(`${API_BASE}/companies/${companyId}/metrics`).then(json<MetricsResponse>),

  risk: (companyId: string) =>
    fetch(`${API_BASE}/companies/${companyId}/risk`).then(
      json<{ flags: RiskFlag[]; composite_score: number }>),

  runValuation: (companyId: string, assumptions: object, forecast: object,
                 signal?: AbortSignal) =>
    fetch(`${API_BASE}/companies/${companyId}/valuation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assumptions, forecast, persist: false }),
      signal,
    }).then(json<ValuationReport>),

  uploadFiling: (companyId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/companies/${companyId}/filings`, {
      method: "POST",
      body: form,
    }).then(json<{ filing_id: string; job_id: string }>);
  },

  job: (jobId: string) => fetch(`${API_BASE}/jobs/${jobId}`).then(json<JobState>),

  reviewQueue: () => fetch(`${API_BASE}/review/queue`).then(json<ReviewItem[]>),

  reviewStats: () => fetch(`${API_BASE}/review/stats`).then(json<ReviewStats>),

  reviewBulk: (action: string, threshold?: number, companyId?: string) =>
    fetch(`${API_BASE}/review/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, threshold: threshold ?? 0.7, company_id: companyId ?? null }),
    }).then(json<BulkResult>),

  reviewItem: (itemId: string, decision: { approve: boolean; value?: number; canonical_key?: string }) =>
    fetch(`${API_BASE}/review/items/${itemId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    }).then(json<{ statement_status: string }>),

  copilotQuerySync: (companyId: string, question: string) =>
    fetch(`${API_BASE}/copilot/query_sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: companyId, question }),
    }).then(json<CopilotPayload>),

  filingFileUrl: (filingId: string) => `${API_BASE}/filings/${filingId}/file`,
};

/** SSE over fetch POST (EventSource cannot POST). Parses token + done events. */
export async function copilotStream(
  companyId: string,
  question: string,
  onToken: (delta: string) => void,
): Promise<CopilotPayload> {
  const res = await fetch(`${API_BASE}/copilot/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_id: companyId, question }),
  });
  if (!res.ok || !res.body) throw new Error("copilot stream failed");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: CopilotPayload | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const lines = event.split("\n");
      const type = lines.find((l) => l.startsWith("event:"))?.slice(6).trim();
      const dataLine = lines.find((l) => l.startsWith("data:"))?.slice(5).trim();
      if (!dataLine) continue;
      if (type === "token") {
        onToken(JSON.parse(dataLine).delta ?? "");
      } else if (type === "done") {
        donePayload = JSON.parse(dataLine);
      }
    }
  }
  if (!donePayload) throw new Error("stream ended without done event");
  return donePayload;
}
