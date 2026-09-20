"""Copilot answer contract (strict JSON, Pydantic-validated — P4.3)."""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    chunk_id: str
    doc: str = ""
    page_no: int
    quote: str = Field(description="exact source span used, <= 240 chars")


class MetricUsed(BaseModel):
    key: str
    value: float
    period: str
    formula: str = ""


class CopilotAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    metrics_used: list[MetricUsed] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    insufficient_evidence: bool = False


class CopilotQuery(BaseModel):
    company_id: str
    question: str
    conversation_id: str | None = None


class CitationVerdict(BaseModel):
    chunk_id: str
    exists: bool
    quote_score: float
    page_ok: bool
    ok: bool
    issue: str = ""


class VerificationResult(BaseModel):
    verdict: str  # grounded | partial | ungrounded
    citations: list[CitationVerdict]
    ungrounded_numbers: list[str]
    feedback: str
    grounded: bool

    @property
    def pass_rate(self) -> float:
        if not self.citations:
            return 0.0
        return sum(1 for c in self.citations if c.ok) / len(self.citations)
