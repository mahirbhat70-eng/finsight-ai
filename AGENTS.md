# FinSight AI — Agent Rules (repo-wide, read by every agent)

## Identity
You are one of seven agents building FinSight AI: an investment due-diligence
and valuation platform. Deterministic math is the product; the LLM assists,
it never computes.

## Hard rules
1. **finmod/ is pure Python.** No imports from app/models, app/db, or any
   LLM provider. It takes plain dicts/dataclasses and returns FinancialResult
   objects with lineage.
2. **The LLM never computes numbers.** It proposes label mappings (capped
   confidence 0.75) and writes answers from provided context only.
3. **Money is Numeric(18,2) in INR crore.** Never float in the DB, never
   crore/lakh mixing without an explicit unit field.
4. **Approved statements only** feed metrics, valuation, exports, and the
   copilot digest. Draft extractions live behind the review queue.
5. **Every API change ships with a test**; every phase ends with its
   acceptance gate green before commit.
6. **No new dependencies without a one-line justification** in the PR.
7. Log with structlog; every request carries request_id.
8. Don't fix a test by weakening it — fix the root cause.

## Workflow per phase
Read BUILD_STATE.md first. Mission prompt → checkpoints → acceptance gate →
commit prompt (merge phase branch, update BUILD_STATE.md). Report outputs in
your final message, not just "done".
