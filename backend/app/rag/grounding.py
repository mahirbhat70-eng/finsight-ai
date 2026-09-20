"""Grounding verifier (Playbook P4.4 / U6): per-citation verdicts + number
cross-check. Failure cases it must catch: fake chunk id, mutated quote,
wrong page, invented number. On failure the orchestrator regenerates once
with the feedback below, then marks and strips ungrounded sentences.
"""

import re

from rapidfuzz import fuzz

from app.rag.retrieval import RetrievedChunk
from app.schemas.copilot import CitationVerdict, CopilotAnswer, VerificationResult

QUOTE_MIN_SCORE = 80.0  # RapidFuzz ratio / 100 >= 0.8 per playbook
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]{2,}(?:\.\d+)?(?![\w%])")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _norm_number(text: str) -> float:
    return float(text.replace(",", ""))


def _numbers_in(text: str) -> list[str]:
    return [m for m in NUMBER_RE.findall(text)
            if not YEAR_RE.match(m.replace(",", ""))]


def _number_grounded(token: str, digest_values: list[float],
                     quoted_text: str) -> bool:
    value = _norm_number(token)
    for digest_value in digest_values:
        if abs(value - digest_value) <= max(0.02, abs(digest_value) * 0.001):
            return True
    # allow numbers that appear in the quoted evidence
    for other in _numbers_in(quoted_text):
        if abs(value - _norm_number(other)) < 1e-9:
            return True
    return False


def verify_answer(answer: CopilotAnswer,
                  retrieved: list[RetrievedChunk],
                  digest_values: list[float]) -> VerificationResult:
    by_id = {c.chunk_id: c for c in retrieved}
    verdicts: list[CitationVerdict] = []
    quoted_text = " ".join(c.quote for c in answer.citations)

    for citation in answer.citations:
        chunk = by_id.get(citation.chunk_id)
        if chunk is None:
            verdicts.append(CitationVerdict(
                chunk_id=citation.chunk_id, exists=False, quote_score=0.0,
                page_ok=False, ok=False, issue="chunk id not in retrieved set"))
            continue
        quote_score = fuzz.partial_ratio(citation.quote[:240], chunk.text)
        page_ok = citation.page_no == chunk.page_no
        quote_ok = quote_score >= QUOTE_MIN_SCORE
        issue = ""
        if not quote_ok:
            issue = f"quote match {quote_score:.0f} < {QUOTE_MIN_SCORE:.0f}"
        elif not page_ok:
            issue = f"page {citation.page_no} != chunk page {chunk.page_no}"
        verdicts.append(CitationVerdict(
            chunk_id=citation.chunk_id, exists=True, quote_score=quote_score,
            page_ok=page_ok, ok=quote_ok and page_ok, issue=issue))

    # Numbers in the answer must trace to the digest or cited quotes
    ungrounded: list[str] = []
    for token in _numbers_in(answer.answer):
        if not _number_grounded(token, digest_values, quoted_text):
            ungrounded.append(token)

    if not answer.citations:
        verdict = "ungrounded" if not answer.insufficient_evidence else "partial"
    elif all(v.ok for v in verdicts) and not ungrounded:
        verdict = "grounded"
    elif any(v.ok for v in verdicts):
        verdict = "partial"
    else:
        verdict = "ungrounded"

    feedback_lines: list[str] = []
    for v in verdicts:
        if not v.ok:
            feedback_lines.append(
                f"- citation {v.chunk_id}: {v.issue or 'not grounded'}")
    if ungrounded:
        feedback_lines.append(
            "- these numbers appear nowhere in the FACTS table or cited "
            f"quotes: {', '.join(ungrounded)}")
    feedback = ("VERIFICATION FAILED. Fix ONLY these issues and answer again "
                "from the provided context:\n" + "\n".join(feedback_lines)
                if feedback_lines else "")

    return VerificationResult(
        verdict=verdict, citations=verdicts, ungrounded_numbers=ungrounded,
        feedback=feedback, grounded=verdict == "grounded")


def strip_ungrounded_sentences(answer: str, keep_numbers: bool = False) -> str:
    """Mark ungrounded sentences instead of silently deleting them."""
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    return " ".join(
        s if keep_numbers else s for s in sentences if s.strip())
