"""Scenarios, sensitivity grid, tornado (Playbook P2.4).

Delta rules (bear: growth -3pp, margin -1.5pp, WACC +150bps, g -1pp;
bull symmetric; overridable via ScenarioSpec). Grid: 5 WACC x 5 g fair
values, centered on the computed base WACC. Tornado: +/-10% swing per
driver on per-share, sorted by impact descending.
"""

from dataclasses import dataclass

from app.finmod.dcf import Forecast, run_dcf
from app.finmod.wacc import AssumptionSet, compute_wacc

BEAR_DELTAS = {"growth_pp": -3.0, "margin_pp": -1.5, "wacc_bps": 150.0, "g_pp": -1.0}


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    growth_pp: float = 0.0
    margin_pp: float = 0.0
    wacc_bps: float = 0.0
    g_pp: float = 0.0


def build_scenarios() -> dict[str, ScenarioSpec]:
    d = BEAR_DELTAS
    return {
        "bear": ScenarioSpec("bear", **d),
        "base": ScenarioSpec("base"),
        "bull": ScenarioSpec("bull", growth_pp=-d["growth_pp"],
                             margin_pp=-d["margin_pp"],
                             wacc_bps=-d["wacc_bps"], g_pp=-d["g_pp"]),
    }


def _effective_nwc_days(forecast: Forecast, series: dict[str, list[float]],
                        periods: list[str]) -> float:
    if forecast.nwc_days is not None:
        return forecast.nwc_days
    t = len(periods) - 1
    ca = series.get("current_assets", [0] * (t + 1))[t]
    cash = series.get("cash", [0] * (t + 1))[t]
    cl = series.get("current_liabilities", [0] * (t + 1))[t]
    st = series.get("st_borrowings", [0] * (t + 1))[t]
    nwc = ca - cash - cl + st
    rev = series["revenue"][t]
    return nwc / rev * 365.0


def _flexed(forecast: Forecast, assumptions: AssumptionSet,
            nwc_days_effective: float, **kw) -> Forecast:
    """Copy of the forecast with baked nwc_days and per-driver adjustments."""
    g_base = (forecast.terminal_growth if forecast.terminal_growth is not None
              else assumptions.terminal_growth)
    tax_base = (forecast.tax_rate if forecast.tax_rate is not None
                else assumptions.tax_rate)
    return forecast.model_copy(update={
        "revenue_growth": [g * kw.get("growth_mult", 1.0) + kw.get("growth_add", 0.0)
                           for g in forecast.revenue_growth],
        "ebitda_margin": [m * kw.get("margin_mult", 1.0) + kw.get("margin_add", 0.0)
                          for m in forecast.ebitda_margin],
        "capex_pct_revenue": [c * kw.get("capex_mult", 1.0)
                              for c in forecast.capex_pct_revenue],
        "nwc_days": nwc_days_effective * kw.get("nwc_mult", 1.0),
        "terminal_growth": g_base + kw.get("g_add", 0.0),
        "tax_rate": tax_base + kw.get("tax_add", 0.0),
    })


def run_scenarios(series: dict[str, list[float]], periods: list[str],
                  assumptions: AssumptionSet, forecast: Forecast) -> dict:
    base_wacc, _ = compute_wacc(assumptions, series, periods)
    nwc_days = _effective_nwc_days(forecast, series, periods)
    out: dict[str, dict] = {}
    for name, spec in build_scenarios().items():
        f = _flexed(forecast, assumptions, nwc_days,
                    growth_add=spec.growth_pp, margin_add=spec.margin_pp,
                    g_add=spec.g_pp)
        result = run_dcf(series, periods, assumptions, f,
                         wacc_override=(base_wacc + spec.wacc_bps / 10_000.0
                                        if spec.wacc_bps else None))
        out[name] = {
            "per_share_inr": result["bridge"]["per_share_inr"],
            "equity_value": result["bridge"]["equity_value"],
            "wacc": result["wacc"], "terminal_growth": result["terminal_growth"],
        }
    # Ordering bear <= base <= bull is mathematically guaranteed only when the
    # base terminal FCFF is non-negative; with negative terminal FCFF higher
    # growth makes the terminal value MORE negative and ordering inverts
    # (the negative_equity / checks panel flags such models as not meaningful).
    base = run_dcf(series, periods, assumptions, forecast)
    if base["rows"][-1]["fcff"] > 0:
        assert (out["bear"]["per_share_inr"] <= out["base"]["per_share_inr"]
                <= out["bull"]["per_share_inr"]), "scenario ordering violated"
    return out


def sensitivity_grid(series: dict[str, list[float]], periods: list[str],
                     assumptions: AssumptionSet, forecast: Forecast,
                     wacc_range: list[float] | None = None,
                     g_range: list[float] | None = None) -> dict:
    """5x5 per-share grid: WACC (%) down rows, g (%) across columns."""
    base_wacc, _ = compute_wacc(assumptions, series, periods)
    wacc_pct = base_wacc * 100
    g_base = (forecast.terminal_growth if forecast.terminal_growth is not None
              else assumptions.terminal_growth)
    wacc_range = wacc_range or [wacc_pct + off
                                for off in (-1.0, -0.5, 0.0, 0.5, 1.0)]
    g_range = g_range or [g_base + off for off in (-1.0, -0.5, 0.0, 0.5, 1.0)]

    nwc_days = _effective_nwc_days(forecast, series, periods)
    grid: list[list[float | None]] = []
    for w in wacc_range:
        row: list[float | None] = []
        for g in g_range:
            try:
                f = _flexed(forecast, assumptions, nwc_days, g_add=g - g_base)
                result = run_dcf(series, periods, assumptions, f,
                                 wacc_override=w / 100.0)
                row.append(result["bridge"]["per_share_inr"])
            except ValueError:  # g >= w cell
                row.append(None)
        grid.append(row)
    return {"wacc_axis": wacc_range, "g_axis": g_range, "per_share": grid}


def tornado(series: dict[str, list[float]], periods: list[str],
            assumptions: AssumptionSet, forecast: Forecast) -> list[dict]:
    """+/-10% per driver; 'high'/'low' are favorable/unfavorable per-share."""
    base_wacc, _ = compute_wacc(assumptions, series, periods)
    g_base = (forecast.terminal_growth if forecast.terminal_growth is not None
              else assumptions.terminal_growth)
    tax_base = (forecast.tax_rate if forecast.tax_rate is not None
                else assumptions.tax_rate)
    nwc_days = _effective_nwc_days(forecast, series, periods)

    def ps(**kw) -> float | None:
        try:
            f = _flexed(forecast, assumptions, nwc_days, **kw)
            result = run_dcf(series, periods, assumptions, f)
            return result["bridge"]["per_share_inr"]
        except ValueError:
            return None

    def ps_wacc(wacc_override: float | None, **kw) -> float | None:
        try:
            f = _flexed(forecast, assumptions, nwc_days, **kw)
            result = run_dcf(series, periods, assumptions, f,
                             wacc_override=wacc_override)
            return result["bridge"]["per_share_inr"]
        except ValueError:
            return None

    base = ps()
    if base is None:
        return []

    swings = [
        ("Revenue growth", ps(growth_mult=1.1), ps(growth_mult=0.9)),
        ("EBITDA margin", ps(margin_mult=1.1), ps(margin_mult=0.9)),
        ("Capex %", ps(capex_mult=0.9), ps(capex_mult=1.1)),
        ("NWC days", ps(nwc_mult=0.9), ps(nwc_mult=1.1)),
        ("WACC", ps_wacc(base_wacc * 0.9), ps_wacc(base_wacc * 1.1)),
        ("Terminal g", ps(g_add=+0.1 * g_base), ps(g_add=-0.1 * g_base)),
        ("Tax rate", ps(tax_add=-0.1 * tax_base), ps(tax_add=+0.1 * tax_base)),
    ]
    out: list[dict] = []
    for label, best, worst in swings:
        if best is None or worst is None:
            continue
        out.append({"driver": label, "low": min(best, worst),
                    "high": max(best, worst), "base": base,
                    "impact": abs(best - worst),
                    "impact_pct": (abs(best - worst) / base) if base else None})
    out.sort(key=lambda d: d["impact"], reverse=True)
    return out
