"""Engine entry point (Playbook P2 constraint): a pure function
engine.run_company(stats) that composes ratios -> WACC -> DCF -> scenarios
-> grid -> tornado -> risk. No DB, no LLM, no I/O.
"""

from app.finmod.dcf import Forecast, run_dcf
from app.finmod.lineage import ResultTable
from app.finmod.ratios import compute_metrics
from app.finmod.risk_rules import RuleEngine
from app.finmod.scenarios import run_scenarios, sensitivity_grid, tornado
from app.finmod.wacc import AssumptionSet, compute_wacc


def run_company(series: dict[str, list[float]], periods: list[str],
                assumptions: AssumptionSet | None = None,
                forecast: Forecast | None = None,
                context: dict | None = None) -> dict:
    assumptions = assumptions or AssumptionSet()
    forecast = forecast or Forecast()

    metrics = compute_metrics(series, periods)
    wacc, wacc_table = compute_wacc(assumptions, series, periods)
    dcf = run_dcf(series, periods, assumptions, forecast)

    fcf_series = [(p, v) for p, v in zip(periods, series.get("fcf", []))
                  if v is not None]
    ebitda_series = [v for v in series.get("ebitda", []) if v is not None]
    ctx = {
        "wacc": wacc, "fcf_series": fcf_series, "ebitda_series": ebitda_series,
        **(context or {}),
    }
    risk = RuleEngine().assess(metrics, periods, ctx)

    return {
        "periods": periods,
        "metrics": metrics.to_json(),
        "wacc": wacc,
        "wacc_lineage": wacc_table.to_json(),
        "dcf": dcf,
        "scenarios": run_scenarios(series, periods, assumptions, forecast),
        "sensitivity": sensitivity_grid(series, periods, assumptions, forecast),
        "tornado": tornado(series, periods, assumptions, forecast),
        "risk": risk,
    }


def load_series_from_fixture(json_path: str) -> tuple[dict[str, list[float]],
                                                       list[str]]:
    """Convenience for scripts/tests: canonical fixtures JSON -> (series, periods)."""
    import json
    from pathlib import Path

    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return payload["items"], payload["periods"]


__all__ = ["run_company", "load_series_from_fixture", "ResultTable"]
