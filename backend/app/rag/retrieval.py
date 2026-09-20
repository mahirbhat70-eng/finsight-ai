"""Hybrid retrieval (Playbook P3.5/U6): cosine top-20 (pgvector HNSW) +
websearch_to_tsquery top-20 (lexical) fused with Reciprocal Rank Fusion
(k=60). Vector fails on rare exact terms, BM25 fails on paraphrase — RRF
gets both.
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings

logger = structlog.get_logger("rag.retrieval")


@dataclass
class RetrievedChunk:
    chunk_id: str
    filing_id: str
    page_no: int
    section: str
    text: str
    score: float
    sources: list[str]  # ["vector", "lexical"] legs that retrieved it


VECTOR_SQL = text("""
    SELECT id::text, filing_id::text, page_no, section, text
    FROM chunks
    WHERE (:filing_id::uuid IS NULL OR filing_id = :filing_id::uuid)
    ORDER BY embedding <=> CAST(:qvec AS vector)
    LIMIT :k
""")

LEXICAL_SQL = text("""
    SELECT id::text, filing_id::text, page_no, section, text,
           ts_rank(tsv, websearch_to_tsquery('english', :query)) AS rank
    FROM chunks
    WHERE (:filing_id::uuid IS NULL OR filing_id = :filing_id::uuid)
      AND tsv @@ websearch_to_tsquery('english', :query)
    ORDER BY rank DESC
    LIMIT :k
""")


async def embed_query(query: str) -> list[float]:
    from app.llm.base import get_embedding_provider

    provider = get_embedding_provider()
    return (await provider.embed([query]))[0]


async def hybrid_search(db: AsyncSession, query: str, *,
                        filing_id: uuid.UUID | None = None,
                        top_k: int | None = None,
                        fetch_k: int = 20) -> list[RetrievedChunk]:
    settings = get_settings()
    top_k = top_k or settings.copilot_top_k
    rrf_k = settings.rrf_k

    vector = await embed_query(query)
    qvec = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"

    vec_rows = (await db.execute(VECTOR_SQL, {
        "qvec": qvec, "k": fetch_k, "filing_id": str(filing_id) if filing_id else None,
    })).mappings().all()
    lex_rows = (await db.execute(LEXICAL_SQL, {
        "query": query, "k": fetch_k, "filing_id": str(filing_id) if filing_id else None,
    })).mappings().all()

    fused: dict[str, dict] = {}
    for rank, row in enumerate(vec_rows, start=1):
        entry = fused.setdefault(row["id"], dict(row, sources=[], score=0.0))
        entry["score"] += 1.0 / (rrf_k + rank)
        entry["sources"].append("vector")
    for rank, row in enumerate(lex_rows, start=1):
        entry = fused.setdefault(row["id"], dict(row, sources=[], score=0.0))
        entry["score"] += 1.0 / (rrf_k + rank)
        entry["sources"].append("lexical")

    ranked = sorted(fused.values(), key=lambda e: e["score"], reverse=True)[:top_k]
    return [RetrievedChunk(
        chunk_id=e["id"], filing_id=e["filing_id"], page_no=e["page_no"],
        section=e["section"] or "", text=e["text"], score=round(e["score"], 6),
        sources=e["sources"]) for e in ranked]
