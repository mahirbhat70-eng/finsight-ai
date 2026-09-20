"""MockProvider — deterministic, zero-token (Playbook P4.1).

- complete(): canned echo keyed by a [MOCK:] marker in the prompt.
- complete_json(): validates the JSON found after a "MOCK_JSON:" marker in
  the prompt against the schema — tests craft prompts that embed the exact
  object they want, keeping the suite hermetic.
- embed(): feature-hashing bag-of-words vectors — deterministic AND
  semantically meaningful (similar texts -> similar cosine), so retrieval
  tests are reproducible without network.
"""

import hashlib
import json
import re
from collections.abc import AsyncIterator

from pydantic import BaseModel, ValidationError

from app.core.settings import get_settings
from app.llm.base import LLMError, approx_tokens, record_llm_call

MOCK_JSON_RE = re.compile(r"MOCK_JSON:\s*(\{.*\})\s*$", re.DOTALL)


class MockProvider:
    name = "mock"
    model = "mock-1"

    async def complete(self, prompt: str, *, system: str | None = None,
                       temperature: float = 0.2, max_tokens: int = 4096) -> str:
        record_llm_call("mock", self.model, approx_tokens(prompt), 64, 1)
        if "MOCK_ANSWER:" in prompt:
            return prompt.split("MOCK_ANSWER:", 1)[1].strip()
        return "MOCK: " + prompt.strip()[:200]

    async def complete_json(self, prompt: str, schema: type[BaseModel], *,
                            system: str | None = None,
                            temperature: float = 0.1) -> BaseModel:
        record_llm_call("mock", self.model, approx_tokens(prompt), 128, 1)
        match = MOCK_JSON_RE.search(prompt)
        if not match:
            raise LLMError("mock complete_json requires a MOCK_JSON: block")
        try:
            payload = json.loads(match.group(1))
            return schema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError(f"mock JSON invalid: {exc}") from exc

    async def stream(self, prompt: str, *, system: str | None = None,
                     temperature: float = 0.2) -> AsyncIterator[str]:
        text = await self.complete(prompt, system=system, temperature=temperature)
        for i in range(0, len(text), 24):
            yield text[i:i + 24]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(t) for t in texts]

    @staticmethod
    def _hash_vector(text: str, dim: int | None = None) -> list[float]:
        dim = dim or get_settings().embedding_dim
        vec = [0.0] * dim
        for token in re.findall(r"[a-z0-9]{2,}", text.lower()):
            digest = hashlib.md5(token.encode()).digest()
            idx = int.from_bytes(digest[:4], "little") % dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


class MockEmbedding(MockProvider):
    name = "mock"
    embed_model = "mock-embedding"
    model = "mock-embedding"

    async def complete(self, *a, **kw):  # embeddings only
        raise LLMError("MockEmbedding does not chat")
