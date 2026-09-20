"""Grounding verifier tests (Playbook P4.4): seeded failure cases."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.grounding import verify_answer
from app.rag.retrieval import RetrievedChunk
from app.schemas.copilot import Citation, CopilotAnswer

CHUNK_TEXT = ("Trade receivables stood at Rs 1,427.7 crore (71 days of sales) "
              "and inventories at Rs 1,124.5 crore against trade payables of "
              "Rs 1,462.3 crore. Customer concentration remains a monitoring "
              "item: Customer A represents 14.2% of revenue.")

CHUNK = RetrievedChunk(chunk_id="c1", filing_id="f1", page_no=8,
                        section="MD&A", text=CHUNK_TEXT, score=1.0,
                        sources=["vector", "lexical"])


def _answer(text: str, quote: str = "Customer A represents 14.2% of revenue",
            page: int = 8, chunk_id: str = "c1") -> CopilotAnswer:
    return CopilotAnswer(
        answer=text,
        citations=[Citation(chunk_id=chunk_id, doc="annual_report.pdf",
                            page_no=page, quote=quote)],
        confidence=0.9)


def test_correct_citation_passes() -> None:
    result = verify_answer(_answer("Customer A represents 14.2% of revenue [S1]."),
                           [CHUNK], [1427.7, 1124.5, 1462.3, 14.2])
    assert result.verdict == "grounded"
    assert result.citations[0].ok


def test_fake_chunk_id_fails() -> None:
    result = verify_answer(_answer("text [S1]", chunk_id="made-up-id"),
                           [CHUNK], [])
    assert not result.citations[0].ok
    assert not result.citations[0].exists
    assert result.verdict != "grounded"


def test_mutated_quote_fails() -> None:
    result = verify_answer(
        _answer("Customer A represents 14.2% of revenue [S1].",
                quote="completely unrelated text about something else entirely"),
        [CHUNK], [14.2])
    assert result.citations[0].quote_score < 80.0
    assert not result.citations[0].ok


def test_wrong_page_fails() -> None:
    result = verify_answer(_answer("Customer A represents 14.2% [S1].",
                                   page=42), [CHUNK], [14.2])
    assert not result.citations[0].page_ok
    assert not result.citations[0].ok


def test_invented_number_fails() -> None:
    result = verify_answer(
        _answer("Revenue was Rs 9,999.0 crore in FY2025 [S1]."),
        [CHUNK], [7340.0, 1563.4])
    assert "9,999.0" in result.ungrounded_numbers
    assert result.verdict != "grounded"


def test_number_in_digest_passes() -> None:
    result = verify_answer(_answer("Revenue was Rs 7,340.0 crore [S1]."),
                           [CHUNK], [7340.0])
    assert not result.ungrounded_numbers
    assert result.verdict == "grounded"


def test_years_are_not_flagged() -> None:
    result = verify_answer(_answer("In FY2025 the margin improved [S1]."),
                           [CHUNK], [21.3])
    assert not result.ungrounded_numbers  # 2025 is a year, not a claim


def test_feedback_text_lists_issues() -> None:
    result = verify_answer(_answer("Rs 9,999.0 [S1]", chunk_id="ghost"),
                           [CHUNK], [7340.0])
    assert result.feedback
    assert "VERIFICATION FAILED" in result.feedback
