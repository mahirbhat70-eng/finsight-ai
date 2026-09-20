"""OpenAI-compatible provider (Playbook P4.1) — works with OpenAI, Groq,
Together, vLLM, or any {base_url}/chat/completions endpoint.
"""

import json
import time
from collections.abc import AsyncIterator

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from app.core.settings import get_settings
from app.llm.base import LLMError, approx_tokens, record_llm_call, with_retries

logger = structlog.get_logger("llm.openai")


class OpenAIProvider:
    name = "openai"
    model: str

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY not set")
        self.base_url = (settings.openai_base_url or "https://api.openai.com/v1"
                         ).rstrip("/")
        self.model = settings.llm_model
        self._headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    async def _chat(self, messages: list[dict], temperature: float,
                    max_tokens: int, json_mode: bool) -> dict:
        @with_retries
        async def _call() -> dict:
            timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = {"model": self.model, "messages": messages,
                           "temperature": temperature, "max_tokens": max_tokens}
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                response = await client.post(f"{self.base_url}/chat/completions",
                                             json=payload, headers=self._headers)
                if response.status_code in (429, 500, 502, 503):
                    raise ConnectionError(f"provider {response.status_code}")
                response.raise_for_status()
                return response.json()

        return await _call()

    async def complete(self, prompt: str, *, system: str | None = None,
                       temperature: float = 0.2, max_tokens: int = 4096) -> str:
        started = time.monotonic()
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}]
        data = await self._chat(messages, temperature, max_tokens, json_mode=False)
        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {})
        record_llm_call(self.name, self.model,
                        usage.get("prompt_tokens", approx_tokens(prompt)),
                        usage.get("completion_tokens", approx_tokens(text)),
                        int((time.monotonic() - started) * 1000))
        return text

    async def complete_json(self, prompt: str, schema: type[BaseModel], *,
                            system: str | None = None,
                            temperature: float = 0.1) -> BaseModel:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        full_prompt = (f"{system or ''}\n{prompt}\n\n"
                       "Respond ONLY with a JSON object matching this schema:\n"
                       f"{schema_json}")
        attempt_prompt = full_prompt
        for _ in (1, 2):
            raw = await self.complete(attempt_prompt, system=system,
                                      temperature=temperature)
            try:
                return schema.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning("openai_json_retry", error=str(exc))
                attempt_prompt = (f"{full_prompt}\n\nPrevious output invalid: "
                                  f"{exc}. Return ONLY corrected JSON.")
        raise LLMError("openai-compatible provider failed schema validation")

    async def stream(self, prompt: str, *, system: str | None = None,
                     temperature: float = 0.2) -> AsyncIterator[str]:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}]
        timeout = httpx.Timeout(60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                    "POST", f"{self.base_url}/chat/completions",
                    json={"model": self.model, "messages": messages,
                          "temperature": temperature, "stream": True},
                    headers=self._headers) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: ") or line.endswith("[DONE]"):
                        continue
                    delta = json.loads(line[6:])
                    content = (delta.get("choices", [{}])[0]
                               .get("delta", {}).get("content"))
                    if content:
                        yield content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        @with_retries
        async def _call(batch: list[str]):
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": "text-embedding-3-small", "input": batch},
                    headers=self._headers)
                response.raise_for_status()
                return [item["embedding"] for item in response.json()["data"]]

        vectors: list[list[float]] = []
        for start in range(0, len(texts), 64):
            vectors.extend(await _call(texts[start:start + 64]))
        return vectors
