"""Risk rule engine (Playbook P2.5).

Declarative rules loaded from risk_thresholds.yaml (editable without code
changes). Each flag carries rule_id, category, severity, metric values,
evidence lineage, and a rendered rationale. composite_score in [0, 100].

Boundary semantics: exactly at a threshold = the LOWER severity (pinned by
tests). Metrics come from ratios.compute_metrics series.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.finmod.lineage import ResultTable

DEFAULT_YAML = Path(__file__).parent / "risk_thresholds.yaml"

SEVERITY_ORDER = {"ok": 0, "info": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class RiskFlag:
    rule_id: str
    category: str
    severity: str
    metric: str
    value: float | None
    threshold: float | None
    period: str | None
    rationale: str
    evidence: dict

    def to_json(self) -> dict:
        return {
            "rule_id": self.rule_id, "category": self.category,
            "severity": self.severity, "metric": self.metric,
            "value": self.value, "threshold": self.threshold,
            "period": self.period, "rationale": self.rationale,
            "evidence": self.evidence,
        }


def _series_of(table: ResultTable, key: str) -> list[tuple[str, float]]:
    row = table._rows.get(key, {})  # noqa: SLF001 — internal by design
    out: list[tuple[str, float]] = []
    for period in sorted(row):
        if period == "latest":
            continue
        res = row[period]
        if res.value is not None:
            out.append((period, res.value))
    return out


class RuleEngine:
    def __init__(self, yaml_path: str | Path | None = None) -> None:
        path = Path(yaml_path) if yaml_path else DEFAULT_YAML
        if path.exists():
            self.cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            self.cfg = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))

    # --- helpers -----------------------------------------------------------

    def _series_for(self, table: ResultTable, rule: dict,
                    context: dict) -> list[tuple[str, float]]:
        metric = rule["metric"]
        if metric == "top_customer_concentration":
            val = context.get("top_customer_concentration")
            return [("latest", val)] if val is not None else []
        if metric == "fcf":
            row = table._rows.get("fcf_conversion", {})  # noqa: SLF001
            # negative-FCF rule needs raw fcf; pull from context if provided
            raw = context.get("fcf_series")
            if raw:
                return [(p, v) for p, v in raw if v is not None]
        return _series_of(table, metric)

    def _breach(self, rule: dict, value: float, context: dict) -> str | None:
        """Return 'high' | 'medium' | None for one value against the rule."""
        op = rule["op"]
        if op == "gt":
            if "high" in rule and value > rule["high"]:
                return "high"
            if "medium" in rule and value > rule["medium"]:
                return "medium"
        elif op == "lt":
            if "high" in rule and value < rule["high"]:
                return "high"
            if "medium" in rule and value < rule["medium"]:
                return "medium"
        elif op == "below_wacc":
            wacc = context.get("wacc")
            if wacc is not None and value < wacc:
                return "high"
        elif op == "negative_while_ebitda_grows":
            if value < 0:
                return "medium"
        return None

    # --- main --------------------------------------------------------------

    def assess(self, table: ResultTable, periods: list[str],
               context: dict | None = None) -> dict:
        """Assess the ratio table; returns {flags, composite_score}."""
        context = context or {}
        flags: list[RiskFlag] = []

        for rule in self.cfg["rules"]:
            series = self._series_for(table, rule, context)
            if not series:
                continue
            window = rule.get("window", "latest")

            if rule["op"] == "drop_bps":
                # YoY decline in bps of the metric (percent units); scan all
                # consecutive pairs, report the largest qualifying decline.
                best = None
                for (p_prev, prev), (p_cur, cur) in zip(series, series[1:]):
                    drop_bps = (prev - cur) * 10_000  # decimal -> bps
                    if drop_bps > rule.get("medium", 150):
                        if best is None or drop_bps > best[2]:
                            best = (p_cur, cur, drop_bps, prev)
                if best:
                    period, cur, drop_bps, prev = best
                    flags.append(RiskFlag(
                        rule_id=rule["id"], category=rule["category"],
                        severity="medium", metric=rule["metric"],
                        value=drop_bps, threshold=rule["medium"],
                        period=period,
                        rationale=rule["rationale"].format(
                            value=drop_bps, threshold=rule["medium"]),
                        evidence={"prev": prev, "cur": cur, "period": period}))
                continue

            if rule["op"] == "negative_while_ebitda_grows":
                ebitda = context.get("ebitda_series") or []
                breaches = [
                    (period, v) for i, (period, v) in enumerate(series)
                    if v < 0 and i > 0 and ebitda and ebitda[i] > ebitda[i - 1]
                ]
                if breaches:  # report once, worst (latest) period
                    period, v = breaches[-1]
                    flags.append(RiskFlag(
                        rule_id=rule["id"], category=rule["category"],
                        severity="medium", metric="fcf", value=v,
                        threshold=0, period=period,
                        rationale=rule["rationale"].format(value=v, threshold=0),
                        evidence={"breaches": breaches}))
                continue

            candidates: list[tuple[str, float, str]] = []
            if window == "latest":
                period, value = series[-1]
                sev = self._breach(rule, value, context)
                if sev:
                    candidates.append((period, value, sev))
            elif window == "any":
                for period, value in series:
                    sev = self._breach(rule, value, context)
                    if sev:
                        candidates.append((period, value, sev))
            elif window == "streak2":
                run = 0
                for period, value in series:
                    sev = self._breach(rule, value, context)
                    if sev:
                        run += 1
                        if run >= 2:
                            candidates.append((period, value, sev))
                            break
                    else:
                        run = 0

            if candidates:
                # report the worst breach (highest severity, latest period)
                period, value, sev = max(
                    candidates,
                    key=lambda c: (SEVERITY_ORDER.get(c[2], 0), c[0]))
                threshold = (rule.get("high") if sev == "high"
                             else rule.get("medium"))
                flags.append(RiskFlag(
                    rule_id=rule["id"], category=rule["category"], severity=sev,
                    metric=rule["metric"], value=value,
                    threshold=threshold, period=period,
                    rationale=rule["rationale"].format(
                        value=value, threshold=threshold or 0,
                        wacc=context.get("wacc", 0.0),
                        direction="above" if rule["op"] == "gt" else "below"),
                    evidence={"window": window,
                              "breaches": [(p, v, s) for p, v, s in candidates]}))

        weights = self.cfg["category_weights"]
        penalty = self.cfg["severity_penalty"]
        capped: dict[str, int] = {}
        for flag in flags:
            cat = capped.setdefault(flag.category, 0)
            capped[flag.category] = min(
                weights.get(flag.category, 10),
                cat + penalty.get(flag.severity, 5))
        score = max(0, 100 - sum(capped.values()))
        return {
            "flags": [f.to_json() for f in
                      sorted(flags, key=lambda f: (-SEVERITY_ORDER[f.severity],
                                                   f.rule_id))],
            "composite_score": score,
        }
