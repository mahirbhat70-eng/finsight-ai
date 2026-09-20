"""Chunk embedding + index (Playbook P3.5).

Embeds via the provider adapter, inserts chunks with vector(768) + generated
tsvector, and creates the HNSW (cosine) + GIN indexes idempotently — index
DDL on generated columns is owned here rather than in a migration.
HNSW tuning (Phase 7): m=16, ef_construction=64, ef_search=40.
"""

import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_engine
from app.ingestion.chunker import ChunkOut
from app.models import Chunk

logger = structlog.get_logger("rag.indexing")

INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
    "ON chunks USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin (tsv)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_filing ON chunks (filing_id)",
)


async def ensure_indexes(db: AsyncSession | None = None) -> None:
    if db is not None:
        for ddl in INDEX_DDL:
            await db.execute(text(ddl))
    else:
        engine = get_engine()
        async with engine.begin() as conn:
            for ddl in INDEX_DDL:
                await conn.execute(text(ddl))
    logger.info("hybrid_indexes_ready")


async def embed_and_index(db: AsyncSession, filing_id: uuid.UUID,
                          chunks: list[ChunkOut]) -> int:
    import asyncio
    from app.llm.base import get_embedding_provider

    provider = get_embedding_provider()
    batch_size = 16

    # Build all batches.
    batches = [
        [c.text[:8000] for c in chunks[start:start + batch_size]]
        for start in range(0, len(chunks), batch_size)
    ]
    chunk_batches = [
        chunks[start:start + batch_size]
        for start in range(0, len(chunks), batch_size)
    ]

    # Embed all batches concurrently.
    all_vectors = await asyncio.gather(
        *[provider.embed(b) for b in batches]
    )

    # Flatten and insert.
    inserted = 0
    for batch_chunks, vectors in zip(chunk_batches, all_vectors):
        for chunk, vector in zip(batch_chunks, vectors):
            db.add(Chunk(filing_id=filing_id, page_no=chunk.page_no,
                         section=chunk.section, chunk_idx=chunk.chunk_idx,
                         text=chunk.text, embedding=vector))
            inserted += 1
    await db.flush()
    await ensure_indexes(db)
    logger.info("chunks_indexed", filing_id=str(filing_id), count=inserted)
    return inserted
