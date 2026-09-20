"""LLM provider adapter — base protocols (Playbook P3.3/P4.1).

One interface, three implementations (gemini | openai | mock). One env flip
(LLM_PROVIDER=mock) runs the whole test suite with zero tokens.

The LLM NEVER computes numbers: it proposes label mappings (capped at 0.75
confidence) and writes answers from provided context only.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Protocol, TypeVar

import structlog
from pydantic import BaseModel

from app.core.logging import get_request_id
from app.core.settings import get_settings

logger = structlog.get_logger("llm")

T = TypeVar("T", bound=BaseModel)

RETRYABLE = (TimeoutError, ConnectionError)  # providers add their own 429/5xx


class LLMError(Exception):
    """Structured provider failure after retries."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, prompt: str, *, system: str | None = None,
                       temperature: float = 0.2, max_tokens: int = 4096) -> str: ...

    async def complete_json(self, prompt: str, schema: type[T], *,
                            system: str | None = None,
                            temperature: float = 0.1) -> T: ...

    def stream(self, prompt: str, *, system: str | None = None,
               temperature: float = 0.2) -> AsyncIterator[str]: ...


class EmbeddingProvider(Protocol):
    embed_model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


# --- Retry + accounting middleware (shared by every provider) ---------------

def with_retries(fn: Callable, attempts: int = 3, base_delay: float = 0.5):
    """Exponential backoff on 429/5xx/timeout errors."""

    async def wrapper(*args, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                return await fn(*args, **kwargs)
            except (*RETRYABLE, LLMError) as exc:  # noqa: PERF203
                last_exc = exc
                delay = base_delay * (2 ** attempt)
                logger.warning("llm_retry", provider=getattr(fn, "__name__", "?"),
                               attempt=attempt + 1, delay=delay, error=repr(exc))
                await asyncio.sleep(delay)
        raise LLMError(f"provider failed after {attempts} attempts") from last_exc

    return wrapper


_calls: list[dict] = []  # in-process accounting; copilot persists to llm_calls


def record_llm_call(provider: str, model: str, prompt_tokens: int,
                    completion_tokens: int, latency_ms: int) -> dict:
    entry = {
        "provider": provider, "model": model,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "latency_ms": latency_ms, "request_id": get_request_id(),
        "created_at": time.time(),
    }
    _calls.append(entry)
    logger.info("llm_call", **entry)
    return entry


def drain_llm_calls() -> list[dict]:
    drained, _calls[:] = _calls[:], []
    return drained


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def get_llm_provider():
    """Factory from env (cached module-level)."""
    from app.llm.mock import MockProvider

    settings = get_settings()
    name = settings.llm_provider
    if name == "gemini":
        from app.llm.gemini import GeminiProvider

        return GeminiProvider()
    if name == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "mock":
        return MockProvider()
    raise LLMError(f"unknown LLM_PROVIDER={name}")


def get_embedding_provider():
    """Embeddings follow EMBEDDING_PROVIDER (gemini | local | mock)."""
    from app.llm.mock import MockEmbedding

    settings = get_settings()
    name = settings.embedding_provider
    if name == "gemini":
        from app.llm.gemini import GeminiEmbedding

        return GeminiEmbedding()
    if name in ("local", "mock"):
        return MockEmbedding()
    raise LLMError(f"unknown EMBEDDING_PROVIDER={name}")
