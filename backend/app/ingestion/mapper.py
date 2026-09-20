"""Mapper (Playbook P3.3): raw labels -> canonical keys.

Cascade: exact alias (conf 1.0) -> RapidFuzz partial_ratio >= 92 (conf =
score/100) -> LLM assist for the remainder ONLY to propose
(key, confidence, reason) triplets in strict JSON — never values
(conf capped at 0.75, source="llm_hint").

Duplicate aggregation: same (key, period) -> highest confidence wins,
conflicts logged. Derived rules auto-fill (e.g. fcf = ocf - capex,
method="derived") and cross-check reported values.
"""

import re
from dataclasses import dataclass, field

import structlog
from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.finmod.taxonomy import ALL_KEYS, DERIVED_RULES, resolve_label
from app.ingestion.parser import ParsedDoc, ParsedTable, parse_number

logger = structlog.get_logger("ingestion.mapper")


class MappingProposal(BaseModel):
    """Strict JSON contract for the LLM — proposals only, NEVER values."""

    key: str = Field(description="one of the provided canonical keys")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


@dataclass
class MappedItem:
    canonical_key: str
    period: str
    value: float
    unit: str
    page_no: int
    raw_label: str
    confidence: float
    method: str  # alias | fuzzy | llm_hint | derived
    source: str = "extracted"


@dataclass
class MapResult:
    items: list[MappedItem] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    llm_proposals: int = 0

    @property
    def review_items(self) -> list[MappedItem]:
        threshold = get_settings().confidence_review_threshold
        return [i for i in self.items if i.confidence < threshold]


async def map_document(parsed: ParsedDoc, *, llm_assist: bool = True) -> MapResult:
    import asyncio
    result = MapResult()
    provider = None
    if llm_assist:
        from app.llm.base import get_llm_provider
        provider = get_llm_provider()

    # First pass: alias + fuzzy resolution; collect labels that need LLM assist.
    _pending_llm: list[tuple[ParsedTable, list, str]] = []  # (table, row, label)
    for table in parsed.tables:
        if not table.periods or table.statement_type is None:
            continue
        await _map_table_first_pass(table, result, provider, _pending_llm)

    # Second pass: fire ALL LLM-assist calls concurrently.
    if _pending_llm and provider is not None:
        proposals = await asyncio.gather(
            *[_llm_assist(label, provider) for _, _, label in _pending_llm],
            return_exceptions=True,
        )
        for (table, row, label), proposal in zip(_pending_llm, proposals):
            if isinstance(proposal, BaseException) or proposal is None:
                result.unmapped.append(f"p{table.page_no}: {label}")
                _append_unmapped_row(table, row, result)
                continue
            key = proposal.key
            conf = min(proposal.confidence, get_settings().llm_assist_max_confidence)
            if key not in ALL_KEYS:
                result.unmapped.append(f"p{table.page_no}: {label} (bad proposal {key})")
                continue
            result.llm_proposals += 1
            _append_mapped_row(table, row, key, conf, label, "llm_hint", result)

    _dedupe(result)
    _derive_missing(result)
    return result


async def _map_table_first_pass(
    table: ParsedTable, result: MapResult, provider,
    pending_llm: list,
) -> None:
    """Resolve alias/fuzzy; queue LLM-assist rows without awaiting them."""
    from app.ingestion.parser import parse_period
    header = table.rows[0]
    period_cells = [c for c in header[1:]]
    col_periods: list[tuple[int, str]] = []
    for idx, cell in enumerate(period_cells, start=1):
        period = parse_period(cell)
        if period:
            col_periods.append((idx, period))
    if not col_periods:
        col_periods = [(idx, p) for idx, p in enumerate(table.periods, start=1)]

    for row in table.rows[1:]:
        label = row[0].strip() if row else ""
        if not label or label.lower().startswith(("rs in", "in crore", "in lakh")):
            continue
        key, conf = resolve_label(label)
        method = "alias" if conf == 1.0 else "fuzzy"

        if key is None and provider is not None and _has_value(row, col_periods):
            # Defer: collect for batched async gather.
            pending_llm.append((table, row, label))
            continue

        if key is None:
            result.unmapped.append(f"p{table.page_no}: {label}")
            _append_unmapped_row(table, row, result, col_periods=col_periods)
            continue
        if key not in ALL_KEYS:
            result.unmapped.append(f"p{table.page_no}: {label} (bad proposal {key})")
            continue

        _append_mapped_row(table, row, key, conf, label, method, result,
                           col_periods=col_periods)


def _get_col_periods(table: ParsedTable) -> list[tuple[int, str]]:
    from app.ingestion.parser import parse_period
    header = table.rows[0]
    col_periods: list[tuple[int, str]] = []
    for idx, cell in enumerate(header[1:], start=1):
        period = parse_period(cell)
        if period:
            col_periods.append((idx, period))
    if not col_periods:
        col_periods = [(idx, p) for idx, p in enumerate(table.periods, start=1)]
    return col_periods


def _append_mapped_row(
    table: ParsedTable, row: list, key: str, conf: float,
    label: str, method: str, result: MapResult, *,
    col_periods: list[tuple[int, str]] | None = None,
) -> None:
    if col_periods is None:
        col_periods = _get_col_periods(table)
    for col_idx, period in col_periods:
        if col_idx >= len(row):
            continue
        value = parse_number(row[col_idx])
        if value is None:
            continue
        result.items.append(MappedItem(
            canonical_key=key, period=period,
            value=value * table.unit_scale,
            unit="mn_shares" if key == "shares_outstanding" else "INR_cr",
            page_no=table.page_no, raw_label=label,
            confidence=conf if value else max(conf * 0.9, 0.0),
            method=method,
        ))


def _append_unmapped_row(
    table: ParsedTable, row: list, result: MapResult, *,
    col_periods: list[tuple[int, str]] | None = None,
) -> None:
    label = row[0].strip() if row else ""
    if col_periods is None:
        col_periods = _get_col_periods(table)
    for col_idx, period in col_periods:
        if col_idx >= len(row):
            continue
        value = parse_number(row[col_idx])
        if value is None:
            continue
        result.items.append(MappedItem(
            canonical_key=_unmapped_key(label), period=period,
            value=value * table.unit_scale, unit="INR_cr",
            page_no=table.page_no, raw_label=label,
            confidence=0.3, method="unmapped", source="ambiguous"))


def _has_value(row: list[str], col_periods: list[tuple[int, str]]) -> bool:
    return any(idx < len(row) and parse_number(row[idx]) is not None
               for idx, _ in col_periods)


async def _llm_assist(label: str, provider) -> MappingProposal | None:
    """Ask the provider to PROPOSE a mapping. Never sends or returns values."""
    prompt = (
        "Map this financial statement row label to exactly one canonical key.\n"
        f"Row label: {label!r}\n"
        f"Canonical keys: {', '.join(ALL_KEYS)}\n"
        "Rules: propose only a key from the list; never compute or guess "
        "values; confidence 0-1 reflecting certainty.\n"
        "Respond with JSON: {key, confidence, reason}."
    )
    try:
        proposal = await provider.complete_json(prompt, MappingProposal,
                                                temperature=0.0)
        return proposal
    except Exception as exc:  # noqa: BLE001 — provider failure is non-fatal
        logger.warning("llm_assist_failed", label=label, error=repr(exc))
        return None


def _unmapped_key(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40]
    return f"unmapped:{slug}"


def _dedupe(result: MapResult) -> None:
    """Same (key, period): highest confidence wins; conflicts logged."""
    best: dict[tuple[str, str], MappedItem] = {}
    for item in result.items:
        k = (item.canonical_key, item.period)
        current = best.get(k)
        if current is None or item.confidence > current.confidence:
            if current is not None and abs(current.value - item.value) > 1e-6:
                result.conflicts.append({
                    "canonical_key": k[0], "period": k[1],
                    "kept": item.value, "dropped": current.value,
                    "raw_labels": [item.raw_label, current.raw_label],
                })
            best[k] = item
        elif abs(current.value - item.value) > 1e-6:
            result.conflicts.append({
                "canonical_key": k[0], "period": k[1],
                "kept": current.value, "dropped": item.value,
                "raw_labels": [current.raw_label, item.raw_label],
            })
    result.items = list(best.values())


def _derive_missing(result: MapResult) -> None:
    """Auto-fill derivable keys (method='derived', confidence 0.9) and
    cross-check reported identities (confidence penalty on mismatch)."""
    by_key_period = {(i.canonical_key, i.period): i for i in result.items}

    def val(key: str, period: str) -> float | None:
        item = by_key_period.get((key, period))
        return item.value if item else None

    periods = {i.period for i in result.items}
    for period in periods:
        # fcf = ocf - capex (the taxonomy's derived flag)
        if ("fcf", period) not in by_key_period:
            ocf, capex = val("ocf", period), val("capex", period)
            if ocf is not None and capex is not None:
                page = by_key_period[("ocf", period)].page_no
                result.items.append(MappedItem(
                    canonical_key="fcf", period=period, value=ocf - capex,
                    unit="INR_cr", page_no=page, raw_label="derived",
                    confidence=0.9, method="derived", source="derived"))
                by_key_period[("fcf", period)] = result.items[-1]

        # identity cross-check: pat = pbt - tax_expense (display-rounding tolerant)
        pat, pbt, tax = (val("pat", period), val("pbt", period),
                         val("tax_expense", period))
        if None not in (pat, pbt, tax):
            tolerance = max(0.05, abs(pbt - tax) * 0.001)
            if abs(pat - (pbt - tax)) > tolerance:
                item = by_key_period[("pat", period)]
                mismatch = abs(pat - (pbt - tax)) / max(1.0, abs(pbt - tax))
                item.confidence = max(0.5, item.confidence - min(0.3, mismatch))
                logger.warning("identity_mismatch", key="pat", period=period,
                               reported=pat, computed=pbt - tax)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
