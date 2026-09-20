"""GeminiProvider + GeminiEmbedding (Playbook P4.1) — google-generativeai SDK.

The SDK is synchronous; calls run in threads so FastAPI stays async.
complete_json uses JSON mime mode + one schema-error retry.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import structlog
from pydantic import BaseModel, ValidationError

from app.core.settings import get_settings
from app.llm.base import LLMError, approx_tokens, record_llm_call, with_retries

logger = structlog.get_logger("llm.gemini")


class GeminiProvider:
    name = "gemini"
    model: str

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY not set")
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self.model = settings.llm_model
        self._client = genai.GenerativeModel(settings.llm_model)

    async def complete(self, prompt: str, *, system: str | None = None,
                       temperature: float = 0.2, max_tokens: int = 4096) -> str:
        started = time.monotonic()

        @with_retries
        async def _call() -> str:
            return await asyncio.to_thread(
                self._generate, prompt, system, temperature, max_tokens, False)

        text = await _call()
        record_llm_call(self.name, self.model, approx_tokens(prompt),
                        approx_tokens(text), int((time.monotonic() - started) * 1000))
        return text

    def _generate(self, prompt: str, system: str | None, temperature: float,
                  max_tokens: int, json_mode: bool):
        config = {"temperature": temperature, "max_output_tokens": max_tokens}
        if json_mode:
            config["response_mime_type"] = "application/json"
        contents = ([{"role": "user", "parts": [{"text": prompt}]}])
        response = self._client.generate_content(
            contents=contents,
            generation_config=self._genai.GenerationConfig(**config),
        )
        self._usage = getattr(response, "usage_metadata", None)
        return response.text or ""

    async def complete_json(self, prompt: str, schema: type[BaseModel], *,
                            system: str | None = None,
                            temperature: float = 0.1) -> BaseModel:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        full_prompt = (
            f"{system or ''}\n{prompt}\n\n"
            "Respond ONLY with a JSON object matching this schema exactly:\n"
            f"{schema_json}")
        attempt_prompt = full_prompt
        for attempt in (1, 2):
            raw = await self.complete(attempt_prompt, system=system,
                                      temperature=temperature)
            try:
                return schema.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning("gemini_json_retry", attempt=attempt, error=str(exc))
                attempt_prompt = (
                    f"{full_prompt}\n\nYour previous output was invalid: {exc}\n"
                    "Return ONLY corrected JSON.")
        raise LLMError("gemini could not produce schema-valid JSON after retry")

    async def stream(self, prompt: str, *, system: str | None = None,
                     temperature: float = 0.2) -> AsyncIterator[str]:
        response = await asyncio.to_thread(
            self._client.generate_content, [prompt],
            self._genai.GenerationConfig(temperature=temperature),
            {"stream": True})
        for chunk in response:
            if chunk.text:
                yield chunk.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embedding = GeminiEmbedding()
        return await embedding.embed(texts)


class GeminiEmbedding:
    name = "gemini"
    embed_model: str

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY not set")
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self.embed_model = settings.embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        @with_retries
        async def _call(batch: list[str]) -> list[list[float]]:
            def _embed():
                response = self._genai.embed_content(
                    model=f"models/{self.embed_model}",
                    content=batch, task_type="retrieval_document")
                return response["embedding"]

            return await asyncio.to_thread(_embed)

        vectors: list[list[float]] = []
        for start in range(0, len(texts), 16):
            batch = [t[:8000] for t in texts[start:start + 16]]
            vectors.extend(await _call(batch))
        return vectors
