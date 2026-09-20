# FinSight AI

**Deterministic-first investment due diligence & valuation platform**: ingest
annual-report PDFs with confidence-scored extraction and a human review loop,
run a fully deterministic DCF/risk engine, ask a citation-grounded RAG
copilot, benchmark against peers, and export a live-formula Excel model,
investment memo PDF, and committee deck.

> The LLM never computes a number. It proposes label mappings (capped at
> 0.75 confidence) and answers from retrieved context only — every number
> traces to approved statements or explicit assumption inputs.

## Architecture

```mermaid
flowchart LR
    subgraph client[Analyst]
        UI[Next.js 15 dashboard]
    end
    subgraph api[FastAPI /api/v1]
        R[routers: companies, metrics, valuation, risk, filings, review, copilot, peers, exports, auth]
    end
    subgraph engine[Deterministic core]
        F[finmod: ratios, WACC, DCF, scenarios, risk rules]
        T[taxonomy: 26 canonical keys]
    end
    subgraph pipeline[Ingestion (arq + Redis)]
        P[pdfplumber parser] --> M[mapper: alias -> RapidFuzz -> LLM assist]
        M --> RV{confidence < 0.85?}
        RV -- yes --> Q[human review queue]
        RV -- no --> C[chunker 500-800 tokens]
        C --> E[embed + HNSW + tsvector]
    end
    subgraph store[(PostgreSQL 16 + pgvector)]
    end
    G[Gemini adapter | OpenAI-compatible | Mock] --> L[(llm_calls accounting)]
    UI --> R --> F
    R --> pipeline --> store
    R --> G
    E --> H[hybrid search: cosine + websearch_to_tsquery + RRF k=60]
    H --> V[grounding verifier] --> QL[(qa_logs)]
```

## Quickstart

```bash
docker compose up -d                       # db (pgvector) + redis + backend + worker + frontend
cd backend && alembic revision --autogenerate -m initial && alembic upgrade head
python ../scripts/generate_novatech.py --all   # deterministic fixtures (seed 42)
python ../scripts/seed.py                      # company + approved statements
python ../scripts/seed_peers.py                # 3-peer benchmark fixture
curl localhost:8000/api/v1/health             # {status: ok, db: ok, redis: ok}
cd frontend && npm install && npm run dev      # dashboard on :3000
```

Mock mode (`LLM_PROVIDER=mock` in `.env`) runs the whole suite with zero
tokens. Flip to `gemini` with `GEMINI_API_KEY` for the live demo.

## Measured results (NovaTech golden fixtures, seed 42)

| Metric | Result |
|---|---|
| Ground-truth extraction mapping | 129/129 line items (100%) within 0.5% |
| Engine unit + golden tests | 45 passed (finmod, parser, mapper, grounding, excel) |
| Excel export recalc vs API | per-share matches within 0.1% (LibreOffice headless, base + flexed growth +2pp) |
| Base DCF (FY2025) | WACC 10.05%, EV Rs 18,614.7 Cr, fair value Rs 194.71/share |
| Model checks demo | TV share 82% of EV (warn fires), exit-multiple cross-check within 5% |
| Risk engine | 8 flags across leverage/liquidity/earnings-quality/coverage/concentration, composite 40/100 |

Run the numbers yourself: `make demo` (DCF bridge), `make test`,
`make eval-rag` (hit@5 ≥ 0.75, groundedness ≥ 0.90 gates).

## Repo map

```
backend/app/
  finmod/      deterministic engine (taxonomy, ratios, WACC, DCF, scenarios, risk, peers)
  ingestion/   parser, mapper, chunker, pipeline, arq worker
  rag/         embeddings+index, hybrid retrieval, orchestrator, grounding
  llm/         provider adapter (gemini | openai | mock) + token accounting
  exports/     excel_model (live formulas), memo_pdf, deck, charts
  api/v1/      thin routers; services fat
frontend/      Next.js 15 + React 19 + Tailwind + TanStack Query + Recharts
scripts/       generate_novatech, seed, seed_peers, eval_rag, load_test
docs/          architecture, deploy, demo script, interview defense
```

## Deploy

Track A (VM + compose + Caddy TLS): see `docs/deploy.md` — reproducible from
a clean Ubuntu VM in under 30 minutes, nightly eval workflow gates quality,
`pg_dump` backup cron + documented restore drill.

## Resume bullets

- Built an end-to-end investment due-diligence platform (FastAPI,
  PostgreSQL+pgvector, Next.js, Gemini via provider adapter): PDF ingestion
  with confidence-scored extraction and human review, deterministic
  DCF/scenario/risk engine, and a citation-grounded RAG copilot.
- Shipped a live-formula Excel DCF export (FAST-standard inputs) that
  recalculates to the API result within 0.1% (LibreOffice-verified), plus
  PDF memo and PPTX deck pipelines.
- Hybrid retrieval (pgvector HNSW + tsquery + RRF) with a grounding verifier
  and a 20-question golden eval: 100% ground-truth mapping accuracy on the
  synthetic benchmark corpus; nightly CI eval job guards regression.
