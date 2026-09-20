"""Parser tests (Playbook P3.2): number normalizer, periods, statement
detection, and real extraction from the synthetic NovaTech PDF."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.parser import (
    detect_statement_type,
    infer_unit_scale,
    parse_number,
    parse_period,
    parse_pdf,
)

def find_fixtures() -> Path:
    """data/fixtures in the merged repo OR inside a phase folder."""
    for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        cand = parent / "data" / "fixtures"
        if (cand / "novatech_annual_report.pdf").exists():
            return cand
    raise FileNotFoundError("data/fixtures not found above tests/")


FIXTURES = find_fixtures()


def test_parse_number_western_and_indian() -> None:
    assert parse_number("1,234.56") == 1234.56
    assert parse_number("12,34,567") == 1234567.0  # Indian grouping stripped
    assert parse_number("(45.2)") == -45.2
    assert parse_number("(1,411.0)") == -1411.0
    assert parse_number("\u221240") == -40.0  # unicode minus
    assert parse_number("-") is None
    assert parse_number("—") is None
    assert parse_number("NA") is None
    assert parse_number("") is None
    assert parse_number("2,922.7") == 2922.7


def test_parse_period_variants() -> None:
    assert parse_period("FY2024") == "FY2024"
    assert parse_period("FY 2024-25") == "FY2025"
    assert parse_period("2023-24") == "FY2024"
    assert parse_period("Year ended March 2023") == "FY2023"


def test_unit_inference() -> None:
    assert infer_unit_scale("Rs in crore") == 1.0
    assert infer_unit_scale("(Rs. in Lakhs)") == 0.01
    assert infer_unit_scale("INR in million") == 0.1
    assert infer_unit_scale("no unit hint here") is None


def test_statement_detection() -> None:
    assert detect_statement_type("Consolidated Balance Sheet as at 31 March")["bs"] >= 1
    assert detect_statement_type("Consolidated Statement of Profit and Loss")["pl"] >= 1
    assert detect_statement_type("Consolidated Statement of Cash Flows")["cf"] >= 1


def test_real_pdf_extraction() -> None:
    doc = parse_pdf(str(FIXTURES / "novatech_annual_report.pdf"))
    assert doc.pages and doc.tables
    statement_tables = doc.statement_tables
    assert len(statement_tables) >= 3
    # the consolidated P&L must expose FY2021..FY2025 columns
    assert any(len(t.periods) == 5 for t in statement_tables)
    # top rows of the P&L are real labels with real numbers
    pl = next(t for t in statement_tables if "Revenue from Operations" in
              " ".join(r[0] for r in t.rows if r))
    rev_row = next(r for r in pl.rows if r and r[0] == "Revenue from Operations")
    assert parse_number(rev_row[-1]) == 7340.0  # FY2025 ground truth
