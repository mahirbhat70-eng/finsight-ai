# BUILD_STATE.md — agent long-term memory

## Project
FinSight AI — AI investment due-diligence & valuation platform.
Stack: FastAPI (async) + PostgreSQL 16/pgvector + Redis/arq + Next.js 15 +
Gemini via provider adapter (mock for tests).

## Phase log
- [x] Phase 0 — Foundation & Rails — COMPLETE
  - compose: db (pgvector/pg16) + redis + backend + worker + frontend
  - /api/v1/health contract green: {status, db, redis, version}
  - structlog JSON + request_id middleware + error envelope in place

## Conventions
- Money: INR crore, Numeric(18,2). Periods: FY2021..FY2025 (March end).
- finmod/ pure; app/models owns persistence; app/llm adapter (gemini|openai|mock).
- Golden tests pin computed fixture values; update together with generator.

## Next
Phase 1 — Domain Model & Synthetic Data (taxonomy, models, NovaTech fixtures).
