"""RAG eval harness (Playbook P4.6): golden set from the synthetic report's
ground truth. Metrics: retrieval hit@5, groundedness (verifier pass rate),
numeric correctness, latency p50/p95, tokens per question.

Usage:
  python scripts/eval_rag.py                  # full eval (needs seeded DB)
  python scripts/eval_rag.py --retrieval-only # CI mode (mock embeddings ok)
Pass thresholds: hit@5 >= 0.75, groundedness >= 0.90.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

REPORTS = Path(__file__).resolve().parents[1] / "reports"
FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"

HIT_AT_K = 5
THRESHOLDS = {"hit@5": 0.75, "groundedness": 0.90}


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(p * len(ordered)))
    return ordered[idx]


def load_golden() -> list[dict]:
    gt = json.loads((FIXTURES / "novatech_ground_truth.json").read_text())
    return gt["qa_pairs"]


async def eval_retrieval(company_id: uuid.UUID) -> dict:
    from app.db.session import get_session_factory
    from app.rag.retrieval import hybrid_search

    golden = load_golden()
    hits = 0
    rows: list[dict] = []
    async with get_session_factory()() as db:
        for case in golden:
            started = time.monotonic()
            results = await hybrid_search(db, case["question"],
                                          top_k=HIT_AT_K)
            retrieved_pages = {r.page_no for r in results}
            expected = set(case.get("expected_pages", []))
            hit = bool(expected & retrieved_pages) if expected else None
            if hit:
                hits += 1
            rows.append({"question": case["question"], "hit": hit,
                         "pages": sorted(retrieved_pages),
                         "expected": sorted(expected),
                         "latency_ms": round((time.monotonic() - started) * 1000)})
    scored = [r for r in rows if r["hit"] is not None]
    hit_rate = hits / len(scored) if scored else 0.0
    return {"rows": rows, "hit@5": hit_rate}


async def eval_full(company_id: uuid.UUID) -> dict:
    from app.db.session import get_session_factory
    from app.rag.orchestrator import answer_question

    golden = load_golden()
    rows: list[dict] = []
    grounded = 0
    async with get_session_factory()() as db:
        for case in golden:
            result = await answer_question(db, company_id, case["question"])
            ok = result["verification"]["verdict"] == "grounded"
            if ok:
                grounded += 1
            numeric_ok = None
            if case.get("expected_metric"):
                metric = case["expected_metric"]
                try:
                    value = float(metric["value"])
                    text = result["answer"].replace(",", "")
                    numeric_ok = any(
                        abs(float(n) - value) <= max(0.02, abs(value) * 0.001)
                        for n in __import__("re").findall(r"\d+\.\d+|\d+", text))
                except ValueError:
                    numeric_ok = False
            rows.append({"question": case["question"], "grounded": ok,
                         "numeric_ok": numeric_ok,
                         "latency_ms": result["latency_ms"],
                         "tokens": result["tokens"],
                         "answer": result["answer"][:200]})
    latencies = [r["latency_ms"] for r in rows]
    return {
        "rows": rows,
        "groundedness": grounded / len(rows) if rows else 0.0,
        "latency_p50": _percentile(latencies, 0.5),
        "latency_p95": _percentile(latencies, 0.95),
        "tokens_total": sum(r["tokens"] for r in rows),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true",
                        help="CI mode: retrieval eval only (mock embeddings ok)")
    parser.add_argument("--company-name", default="NovaTech Industries Ltd")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.db.session import get_session_factory, init_models
    from app.models import Company

    await init_models()
    async with get_session_factory()() as db:
        company = (await db.execute(
            select(Company).where(Company.name == args.company_name)
        )).scalars().first()
        if company is None:
            print(f"company {args.company_name!r} not found — run `make seed` first")
            return 2
        company_id = company.id

    if args.retrieval_only:
        result = await eval_retrieval(company_id)
        summary = {"hit@5": result["hit@5"]}
    else:
        retrieval = await eval_retrieval(company_id)
        full = await eval_full(company_id)
        result = {**retrieval, **full}
        summary = {"hit@5": result["hit@5"], "groundedness": result["groundedness"],
                   "latency_p50": result["latency_p50"],
                   "latency_p95": result["latency_p95"],
                   "tokens_total": result["tokens_total"]}

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "eval_rag_report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")

    lines = ["# RAG Eval Report", ""]
    lines += [f"- **{key}**: {value:.3f}" if isinstance(value, float)
              else f"- **{key}**: {value}" for key, value in summary.items()]
    lines += ["", "| question | hit | grounded | numeric |",
              "|---|---|---|---|"]
    for row in result["rows"][:20]:
        lines.append(f"| {row['question'][:60]} | {row.get('hit', '-')} | "
                     f"{row.get('grounded', '-')} | {row.get('numeric_ok', '-')} |")
    (REPORTS / "eval_rag_report.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines[:12]))
    failed = [k for k, threshold in THRESHOLDS.items()
              if k in summary and summary[k] < threshold]
    if failed:
        print(f"\nEVAL FAILED below thresholds: {failed}")
        return 1
    print("\nEVAL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
