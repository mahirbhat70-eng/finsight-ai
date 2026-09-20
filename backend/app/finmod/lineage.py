"""Lineage: every computed number carries its formula and inputs (U2/U3).

FinancialResult is the unit of trust: value + formula + inputs + period.
ResultTable serializes stably (sorted keys) so golden tests can pin bytes.
"""

from dataclasses import dataclass, field


@dataclass
class FinancialResult:
    key: str
    label: str
    value: float | None
    unit: str  # ratio | percent | days | x | INR_cr
    formula: str = ""
    inputs: dict[str, float] = field(default_factory=dict)
    period: str | None = None
    lineage: list[str] = field(default_factory=list)  # keys of inputs

    def to_json(self) -> dict:
        return {
            "key": self.key, "label": self.label, "value": self.value,
            "unit": self.unit, "formula": self.formula,
            "inputs": self.inputs, "period": self.period,
            "lineage": self.lineage,
        }


class ResultTable:
    """key -> {period -> FinancialResult}; stable to_json for golden tests."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, FinancialResult]] = {}

    def add(self, result: FinancialResult) -> None:
        self._rows.setdefault(result.key, {})[result.period or "latest"] = result

    def get(self, key: str, period: str | None = None) -> FinancialResult | None:
        row = self._rows.get(key)
        if row is None:
            return None
        if period is None:
            # latest = last inserted period for this key
            return row.get("latest") or next(iter(reversed(row.values())))
        return row.get(period)

    def series(self, key: str) -> list[float | None]:
        row = self._rows.get(key, {})
        return [row[p].value for p in sorted(row) if p != "latest"] or \
            [row.get("latest").value] if "latest" in row else []

    def keys(self) -> list[str]:
        return sorted(self._rows)

    def to_json(self) -> dict:
        return {
            key: {period: res.to_json() for period, res in sorted(row.items())}
            for key, row in sorted(self._rows.items())
        }
