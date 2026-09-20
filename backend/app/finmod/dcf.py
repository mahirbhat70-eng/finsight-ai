"""DCF (Playbook P2.3): forecast -> FCFF -> mid-year discounting -> Gordon
terminal + exit-multiple cross-check -> EV bridge -> per share.

Guardrails:
- g >= WACC raises (Gordon denominator flips — economically meaningless).
- TV share of EV > 75% warns ("your DCF is mostly an assumption").
- Discount factors must be monotone decreasing.
- Negative equity flags.
- g above the long-run nominal cap (playbook: 3.5% for India) is an
  INFO-level check — deliberately kept at the playbook's conservative level
  even though the base case (g=5.0%) trips it; the fired check is itself a
  demo artifact.
"""

from pydantic import BaseModel, Field, model_validator

from app.finmod.wacc import AssumptionSet, compute_wacc

DCF_CHECKS = {
    "tv_share_warn": 0.75,
    "g_longrun_info_cap": 0.035,
    "equity_multiple_band": (3.0, 25.0),  # implied EV/EBITDA sanity band
}


class Forecast(BaseModel):
    revenue_growth: list[float] = Field(
        [11.0, 10.5, 9.5, 8.5, 7.5], description="Revenue growth per forecast year, %")
    ebitda_margin: list[float] = Field(
        [21.3, 21.6, 22.0, 22.3, 22.5], description="EBITDA margin per year, %")
    dna_pct_revenue: float = Field(4.2, description="D&A as % of revenue")
    capex_pct_revenue: list[float] = Field(
        [9.0, 9.0, 6.5, 6.5, 6.5],
        description="Capex % of revenue; FY26-27 elevated for the expansion")
    nwc_days: float | None = Field(
        None, description="NWC days on revenue; None -> derived from latest BS")
    tax_rate: float | None = Field(
        None, description="Tax rate %, None -> effective rate from statements")
    terminal_growth: float | None = Field(
        None, description="%, None -> assumptions.terminal_growth")
    exit_multiple: float | None = Field(
        None, description="EV/EBITDA exit multiple, None -> assumptions.exit_multiple")

    @model_validator(mode="after")
    def _lengths(self) -> "Forecast":
        if not (len(self.revenue_growth) == len(self.ebitda_margin)
                == len(self.capex_pct_revenue)):
            raise ValueError("growth / margin / capex lists must match in length")
        if not 1 <= len(self.revenue_growth) <= 10:
            raise ValueError("forecast horizon must be 1-10 years")
        return self


def _nwc(series: dict[str, list[float]], t: int) -> float | None:
    """Net working capital from canonical keys.

    NWC = AR + INV + OCA - AP - OCL, with
    OCA = current_assets - cash - AR - INV and OCL = current_liabilities - st - AP
    which algebraically collapses to
    NWC = current_assets - cash - current_liabilities + st_borrowings.
    """
    def v(key: str) -> float | None:
        row = series.get(key)
        return None if row is None or t >= len(row) else row[t]

    ca, cash, cl, st = (v("current_assets"), v("cash"), v("current_liabilities"),
                        v("st_borrowings"))
    if None in (ca, cash, cl, st):
        return None
    return ca - cash - cl + st  # type: ignore[operator]


def run_dcf(series: dict[str, list[float]], periods: list[str],
            assumptions: AssumptionSet, forecast: Forecast,
            wacc_override: float | None = None) -> dict:
    """Full DCF. Returns a JSON-able dict (rows, bridge, checks)."""
    t0 = len(periods) - 1
    n = len(forecast.revenue_growth)

    wacc, wacc_table = compute_wacc(assumptions, series, periods)
    if wacc_override is not None:
        wacc = wacc_override

    g = (forecast.terminal_growth
         if forecast.terminal_growth is not None else assumptions.terminal_growth) / 100.0
    exit_multiple = (forecast.exit_multiple if forecast.exit_multiple is not None
                     else assumptions.exit_multiple)
    if g >= wacc:
        raise ValueError(
            f"terminal growth ({g:.2%}) must be below WACC ({wacc:.2%}) — "
            "the Gordon denominator flips sign otherwise")

    tax_rate = (forecast.tax_rate if forecast.tax_rate is not None
                else assumptions.tax_rate) / 100.0

    base_revenue = series["revenue"][t0]
    ebitda_latest = series["ebitda"][t0]
    nwc_base = _nwc(series, t0)
    nwc_days = (forecast.nwc_days if forecast.nwc_days is not None
                else (nwc_base / base_revenue * 365.0 if nwc_base is not None else 45.0))

    rows: list[dict] = []
    prev_rev, prev_nwc = base_revenue, nwc_base
    pv_explicit = 0.0
    for i in range(n):
        year = i + 1
        rev = prev_rev * (1 + forecast.revenue_growth[i] / 100.0)
        ebitda = rev * forecast.ebitda_margin[i] / 100.0
        dna = rev * forecast.dna_pct_revenue / 100.0
        ebit = ebitda - dna
        nopat = ebit * (1 - tax_rate)
        capex = rev * forecast.capex_pct_revenue[i] / 100.0
        nwc = rev * nwc_days / 365.0
        delta_nwc = nwc - (prev_nwc if prev_nwc is not None else nwc)
        fcff = nopat + dna - capex - delta_nwc
        exponent = year - 0.5 if assumptions.mid_year else year
        df = (1 + wacc) ** -exponent
        pv = fcff * df
        pv_explicit += pv
        rows.append({
            "year": year, "revenue": rev, "ebitda": ebitda, "dna": dna,
            "ebit": ebit, "nopat": nopat, "capex": capex, "nwc": nwc,
            "delta_nwc": delta_nwc, "fcff": fcff, "discount_factor": df,
            "mid_year": assumptions.mid_year, "pv": pv,
        })
        prev_rev, prev_nwc = rev, nwc

    # Terminal value — Gordon (primary) + exit multiple (cross-check).
    # TV is discounted at the full year-n factor (perpetuity cash flows are
    # year-end by construction) even when explicit FCFFs use mid-year.
    last_fcff = rows[-1]["fcff"]
    terminal_exponent = n
    tv_gordon = last_fcff * (1 + g) / (wacc - g)
    pv_tv = tv_gordon * (1 + wacc) ** -terminal_exponent

    ebitda_final = rows[-1]["ebitda"]
    tv_exit = exit_multiple * ebitda_final
    pv_tv_exit = tv_exit * (1 + wacc) ** -terminal_exponent
    ev_exit = pv_explicit + pv_tv_exit

    ev = pv_explicit + pv_tv
    net_debt = series["total_debt"][t0] - series["cash"][t0]
    equity_value = ev - net_debt
    shares = series.get("shares_outstanding", [None] * (t0 + 1))[t0]
    # equity in INR crore / shares in millions -> INR per share = x 10
    per_share = (equity_value * 10.0 / shares) if shares else None

    # --- Checks ------------------------------------------------------------
    checks: dict[str, dict] = {}
    tv_share = pv_tv / ev if ev else None
    checks["tv_share_of_ev"] = {
        "value": tv_share,
        "severity": "warn" if (tv_share or 0) > DCF_CHECKS["tv_share_warn"] else "ok",
        "detail": f"PV(terminal) is {tv_share:.1%} of EV" if tv_share else "",
    }
    dfs = [r["discount_factor"] for r in rows]
    monotone = all(dfs[i] > dfs[i + 1] for i in range(len(dfs) - 1))
    checks["df_continuity"] = {
        "value": monotone, "severity": "ok" if monotone else "warn",
        "detail": "discount factors must decrease monotonically",
    }
    checks["negative_equity"] = {
        "value": equity_value < 0,
        "severity": "warn" if equity_value < 0 else "ok",
        "detail": ("equity value is negative — model output is not meaningful"
                   if equity_value < 0 else "equity value positive"),
    }
    implied_ev_ebitda = ev / ebitda_latest if ebitda_latest else None
    band = DCF_CHECKS["equity_multiple_band"]
    checks["implied_ev_ebitda"] = {
        "value": implied_ev_ebitda,
        "severity": ("info" if implied_ev_ebitda and not (band[0] <= implied_ev_ebitda
                                                          <= band[1]) else "ok"),
        "detail": f"implied EV/EBITDA {implied_ev_ebitda:.1f}x on latest actuals",
    }
    checks["g_longrun_cap"] = {
        "value": g,
        "severity": "info" if g > DCF_CHECKS["g_longrun_info_cap"] else "ok",
        "detail": ("terminal growth above the conservative long-run nominal cap "
                   f"({DCF_CHECKS['g_longrun_info_cap']:.1%})"),
    }

    bridge = {
        "pv_explicit": pv_explicit, "pv_terminal_gordon": pv_tv,
        "enterprise_value": ev, "net_debt": net_debt,
        "equity_value": equity_value, "shares_mn": shares,
        "per_share_inr": per_share,
        "tv_exit_crosscheck": {
            "exit_multiple": exit_multiple, "pv_terminal_exit": pv_tv_exit,
            "ev_exit_method": ev_exit,
            "spread_vs_gordon": (ev_exit - ev) / ev if ev else None,
        },
    }
    return {
        "periods_analyzed": periods,
        "wacc": wacc, "terminal_growth": g, "tax_rate": tax_rate,
        "nwc_days": nwc_days, "mid_year": assumptions.mid_year,
        "rows": rows, "bridge": bridge, "checks": checks,
        "wacc_lineage": wacc_table.to_json(),
    }
