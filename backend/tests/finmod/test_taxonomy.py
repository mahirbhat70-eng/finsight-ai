"""Taxonomy tests (Playbook P1.1)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.finmod.taxonomy import (
    ALL_KEYS,
    DERIVED_RULES,
    ITEMS,
    REGISTRY,
    resolve_label,
    validate_keys,
)


def test_registry_healthy() -> None:
    assert validate_keys() == []


def test_keys_unique() -> None:
    keys = [item.key for item in ITEMS]
    assert len(keys) == len(set(keys))
    assert len(ALL_KEYS) == 26


def test_statement_types_valid() -> None:
    for item in ITEMS:
        assert item.statement_type in ("pl", "bs", "cf"), item.key


def test_aliases_non_empty() -> None:
    for item in ITEMS:
        assert item.aliases, f"{item.key} has no aliases"


def test_exact_alias_hits() -> None:
    cases = {
        "Revenue from Operations": "revenue",
        "Total Revenue": "revenue",
        "Finance Costs": "interest_expense",
        "Sundry Debtors": "trade_receivables",
        "Total Shareholders Funds": "total_equity",
        "Purchase of Fixed Assets": "capex",
        "Net Cash from Operating Activities": "ocf",
    }
    for label, expected_key in cases.items():
        key, conf = resolve_label(label)
        assert key == expected_key, f"{label} -> {key}, expected {expected_key}"
        assert conf == 1.0


def test_fuzzy_hits() -> None:
    # Realistic row labels that miss exact but should fuzz >= 92.
    key, conf = resolve_label("Trade Receivables (Sundry Debtors)")
    assert key == "trade_receivables" and conf >= 0.92
    key, conf = resolve_label("Shares Outstanding (mn)")
    assert key == "shares_outstanding" and conf >= 0.92


def test_no_match_returns_none() -> None:
    key, conf = resolve_label("Provisions and Other Current Liabilities")
    # Either unresolved or a weak match that must NOT be auto-accepted.
    assert key is None or conf < 0.92


def test_derived_rules_reference_real_keys() -> None:
    for key, tokens in DERIVED_RULES.items():
        assert key in REGISTRY
        for tok in tokens:
            if tok not in ("+", "-"):
                assert tok in REGISTRY, f"{key} rule references {tok}"
