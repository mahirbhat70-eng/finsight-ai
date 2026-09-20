"""Mapper tests (Playbook P3.3): mapping coverage vs ground truth, review
queue population, duplicate aggregation, derived fcf."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.mapper import map_document
from app.ingestion.parser import parse_pdf

def find_fixtures() -> Path:
    """data/fixtures in the merged repo OR inside a phase folder."""
    for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        cand = parent / "data" / "fixtures"
        if (cand / "novatech_annual_report.pdf").exists():
            return cand
    raise FileNotFoundError("data/fixtures not found above tests/")


FIXTURES = find_fixtures()


@pytest.fixture(scope="module")
def mapped():
    parsed = parse_pdf(str(FIXTURES / "novatech_annual_report.pdf"))
    return asyncio.run(map_document(parsed, llm_assist=False))


@pytest.fixture(scope="module")
def ground_truth() -> dict:
    return json.loads((FIXTURES / "novatech_ground_truth.json").read_text())


def test_mapping_coverage(mapped, ground_truth) -> None:
    gt = {(f["key"], f["period"]): f["value"] for f in ground_truth["facts"]}
    hit = miss = 0
    for item in mapped.items:
        expected = gt.get((item.canonical_key, item.period))
        if expected is None:
            continue
        if abs(item.value - expected) <= abs(expected) * 0.005 + 0.02:
            hit += 1
        else:
            miss += 1
    assert hit >= 20, "expect >= 20 canonical items mapped (playbook P3.3)"
    assert miss / max(1, hit + miss) <= 0.05, ">= 95% within 0.5% tolerance"


def test_distinct_canonical_keys(mapped) -> None:
    keys = {i.canonical_key for i in mapped.items
            if not i.canonical_key.startswith("unmapped:")}
    assert len(keys) >= 20


def test_review_queue_gets_ambiguous_rows(mapped) -> None:
    review = mapped.review_items
    assert 0 < len(review) <= 12, "deliberately ambiguous rows must surface"
    assert all(i.method == "unmapped" for i in review)
    assert all(i.raw_label for i in review)


def test_duplicates_aggregated(mapped) -> None:
    seen: set[tuple[str, str]] = set()
    for item in mapped.items:
        key = (item.canonical_key, item.period)
        assert key not in seen, f"duplicate not aggregated: {key}"
        seen.add(key)


def test_fcf_from_pdf_and_derived_path(mapped) -> None:
    fcf = [i for i in mapped.items if i.canonical_key == "fcf"]
    assert fcf, "fcf must be mapped (PDF row) or derived"
    # FY2024 fcf = ocf - capex = 729 - 2140 = deeply negative
    fy24 = next(i for i in fcf if i.period == "FY2024")
    assert fy24.value < -1000

    # Derived path fires when the row is absent from the source
    from app.ingestion.mapper import MapResult, MappedItem, _derive_missing

    result = MapResult(items=[
        MappedItem("ocf", "FY2025", 800.0, "INR_cr", 1, "ocf", 1.0, "alias"),
        MappedItem("capex", "FY2025", 300.0, "INR_cr", 1, "capex", 1.0, "alias"),
    ])
    _derive_missing(result)
    derived = [i for i in result.items if i.canonical_key == "fcf"]
    assert derived and derived[0].method == "derived"
    assert derived[0].value == 500.0
