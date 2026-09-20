"""finmod golden + guardrail + property tests (Playbook P2.6).

Hand-computed constants (NovaTech fixtures, seed 42):
  revenue FY2025             7,340.0 Cr      EBITDA FY2025   1,563.42 Cr
  equity FY2025              3,629.65 Cr     debt FY2025     5,077.06 Cr
  current assets FY2025      3,682.39 Cr     current liab.   2,915.08 Cr
  diluted shares FY2025      742 mn

Hand math pinned in the assertions below. If the generator changes, the
fixtures AND these constants change together (that is the point).
"""

import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from app.finmod.dcf import Forecast, run_dcf
from app.finmod.engine import run_company
from app.finmod.lineage import FinancialResult, ResultTable
from app.finmod.ratios import compute_metrics
from app.finmod.risk_rules import RuleEngine
from app.finmod.scenarios import sensitivity_grid
from app.finmod.wacc import AssumptionSet, compute_wacc

def _find_fixtures() -> Path:
    for parent in [Path(__file__).resolve()] + list(Path(__file__).resolve().parents):
        cand = parent / "data" / "fixtures"
        if (cand / "novatech_statements.json").exists():
            return cand
    return Path("/app/data/fixtures")

FIXTURES = _find_fixtures()
SERIES = json.loads((FIXTURES / "novatech_statements.json").read_text())
PERIODS = SERIES["periods"]
SER = SERIES["items"]

# Hand math: 7,340 / 6,610 - 1 = 0.110439
REV_GROWTH_FY25 = 7340.0 / 6610.0 - 1
# 1,563.42 / 7,340 = 0.213
EBITDA_MARGIN_FY25 = 0.213
# (910 + 1,427.73 + 1,124.46 + 220.2) / (1,462.31 + 183.5 + 1,269.27) = 1.2634
CURRENT_RATIO_FY25 = 3682.39 / 2915.08
# 5,077.06 / 3,629.65 = 1.3988
DE_FY25 = 5077.06 / 3629.65
# Ke = 7.0 + 1.15 x 6.5 = 14.475%
KE = 0.14475
# WACC = (3,629.65 x 0.14475 + 5,077.06 x 0.0688436) / 8,706.71 = 10.0487%
WACC = 0.100487
# equity 14,447.6 Cr / 742 mn shares x 10 = Rs 194.71
PER_SHARE = 194.71


# --- Ratios ---------------------------------------------------------------

def test_ratios_hand_computed() -> None:
    table = compute_metrics(SER, PERIODS)

    def latest(key: str) -> float:
        return table.get(key, "FY2025").value

    assert latest("revenue_growth") == pytest.approx(REV_GROWTH_FY25, rel=1e-4)
    assert latest("ebitda_margin") == pytest.approx(EBITDA_MARGIN_FY25, rel=1e-3)
    assert latest("current_ratio") == pytest.approx(CURRENT_RATIO_FY25, rel=1e-3)
    assert latest("debt_to_equity") == pytest.approx(DE_FY25, rel=1e-3)
    # DSO: 1,427.73 / 7,340 x 365 = 71.0 days
    assert latest("dso") == pytest.approx(71.0, abs=0.05)
    # CCC: 71 + 80 - 104 = 47 days
    assert latest("ccc") == pytest.approx(47.0, abs=0.05)
    # Interest cover: 1,255.1 / 439.2 = 2.86x
    assert latest("interest_cover") == pytest.approx(2.86, abs=0.01)
    # DuPont must tie to plain ROE exactly (identity, not coincidence)
    assert latest("dupont_roe") == pytest.approx(latest("roe"), abs=1e-9)


def test_lineage_present() -> None:
    table = compute_metrics(SER, PERIODS)
    res = table.get("roic", "FY2025")
    assert res is not None and res.formula
    assert "invested_capital" in res.inputs
    assert "ebit" in res.lineage


# --- WACC -------------------------------------------------------------------

def test_wacc_hand_computed() -> None:
    assumptions = AssumptionSet()
    wacc, table = compute_wacc(assumptions, SER, PERIODS)
    # Ke = 7 + 1.15 x 6.5 = 14.475%
    assert table.get("cost_of_equity").value == pytest.approx(KE, abs=1e-6)
    # Kd_at = 9.2 x (1 - 0.2517) = 6.884%
    assert table.get("cost_of_debt_at").value == pytest.approx(0.0688436, abs=1e-6)
    # weights: E/V 41.69%, D/V 58.31% (book proxy)
    assert wacc == pytest.approx(WACC, abs=2e-4)


@pytest.mark.parametrize("bad", [
    {"beta": 0.0}, {"tax_rate": 70.0}, {"rf": -1.0},
    {"market_risk_premium": 0.0}, {"cost_of_debt_pre_tax": -2.0},
])
def test_wacc_guardrails(bad: dict) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AssumptionSet(**bad)


# --- DCF --------------------------------------------------------------------

def test_dcf_bridge_ties() -> None:
    report = run_dcf(SER, PERIODS, AssumptionSet(), Forecast())
    bridge = report["bridge"]

    assert len(report["rows"]) == 5
    # PV(explicit) + PV(terminal) == EV (identity)
    assert bridge["pv_explicit"] + bridge["pv_terminal_gordon"] == \
        pytest.approx(bridge["enterprise_value"], abs=1e-6)
    # EV - net debt == equity (identity)
    assert bridge["enterprise_value"] - bridge["net_debt"] == \
        pytest.approx(bridge["equity_value"], abs=1e-6)
    # equity 14,447.6 Cr / 742 mn shares x 10 = Rs 194.71
    assert bridge["per_share_inr"] == pytest.approx(PER_SHARE, rel=1e-3)
    # mid-year: first discount factor = (1 + WACC)^-0.5
    w = report["wacc"]
    assert report["rows"][0]["discount_factor"] == \
        pytest.approx((1 + w) ** -0.5, abs=1e-12)
    # factors strictly decreasing
    dfs = [r["discount_factor"] for r in report["rows"]]
    assert all(dfs[i] > dfs[i + 1] for i in range(len(dfs) - 1))
    # TV share > 75% fires the warn check on the base case
    assert report["checks"]["tv_share_of_ev"]["severity"] == "warn"
    assert report["checks"]["tv_share_of_ev"]["value"] == pytest.approx(0.8216, rel=1e-3)
    # NWC days derived from the latest balance sheet: 56.05
    assert report["nwc_days"] == pytest.approx(56.0494, rel=1e-3)


def test_dcf_gordon_guardrail() -> None:
    # g >= WACC must raise (Gordon denominator flips sign)
    with pytest.raises(ValueError, match="terminal growth"):
        run_dcf(SER, PERIODS, AssumptionSet(terminal_growth=15.0), Forecast())


def test_dcf_year_end_vs_mid_year() -> None:
    mid = run_dcf(SER, PERIODS, AssumptionSet(mid_year=True), Forecast())
    end = run_dcf(SER, PERIODS, AssumptionSet(mid_year=False), Forecast())
    # year-end discounting undervalues: mid-year EV strictly higher
    assert mid["bridge"]["enterprise_value"] > end["bridge"]["enterprise_value"]


# --- Scenarios / grid / tornado ---------------------------------------------

def test_scenario_ordering() -> None:
    report = run_company(SER, PERIODS)
    sc = report["scenarios"]
    assert sc["bear"]["per_share_inr"] < sc["base"]["per_share_inr"] \
        < sc["bull"]["per_share_inr"]
    # pinned golden values (seed 42 fixtures)
    assert sc["bear"]["per_share_inr"] == pytest.approx(83.36, rel=1e-2)
    assert sc["bull"]["per_share_inr"] == pytest.approx(540.33, rel=1e-2)


def test_grid_center_equals_base_and_monotone() -> None:
    report = run_company(SER, PERIODS)
    grid = report["sensitivity"]
    base_ps = report["dcf"]["bridge"]["per_share_inr"]
    assert grid["per_share"][2][2] == pytest.approx(base_ps, abs=1e-6)
    rows = grid["per_share"]
    # per-share decreases as WACC rises (down each row)...
    for col in range(5):
        col_vals = [rows[r][col] for r in range(5)]
        assert all(a > b for a, b in zip(col_vals, col_vals[1:]) if a and b)
    # ...and increases as g rises (across each row)
    for row in rows:
        vals = [v for v in row if v is not None]
        assert all(a < b for a, b in zip(vals, vals[1:]))


def test_tornado_sorted_and_reasonable() -> None:
    report = run_company(SER, PERIODS)
    impacts = [t["impact"] for t in report["tornado"]]
    assert impacts == sorted(impacts, reverse=True)
    assert {"WACC", "Terminal g", "EBITDA margin"} <= \
        {t["driver"] for t in report["tornado"]}


# --- Risk engine --------------------------------------------------------------

def _table_with(current_ratios: list[float], de_ratios: list[float]) -> ResultTable:
    table = ResultTable()
    for i, (cr, de) in enumerate(zip(current_ratios, de_ratios)):
        table.add(FinancialResult("current_ratio", "Current ratio", cr, "x",
                                  period=f"FY{i + 2021}"))
        table.add(FinancialResult("debt_to_equity", "Debt / equity", de, "x",
                                  period=f"FY{i + 2021}"))
    return table


def test_risk_boundary_at_threshold_is_lower_severity() -> None:
    # current ratio exactly 1.0 -> high band requires strictly < 1.0,
    # so this is MEDIUM; exactly 1.3 -> no flag at all.
    table = _table_with([1.0, 1.05], [0.5, 0.6])
    out = RuleEngine().assess(table, ["FY2021", "FY2022"], {})
    liq = [f for f in out["flags"] if f["rule_id"] == "liq_current"]
    assert len(liq) == 1 and liq[0]["severity"] == "medium"

    table = _table_with([1.3, 1.31], [0.5, 0.6])
    out = RuleEngine().assess(table, ["FY2021", "FY2022"], {})
    assert not [f for f in out["flags"] if f["rule_id"] == "liq_current"]

    # D/E exactly 2.0 -> medium (high requires strictly > 2.0)
    table = _table_with([1.5, 1.5], [2.0, 1.9])
    out = RuleEngine().assess(table, ["FY2021", "FY2022"], {})
    lev = [f for f in out["flags"] if f["rule_id"] == "lev_de"]
    assert len(lev) == 1 and lev[0]["severity"] == "medium"


def test_risk_yaml_reload_changes_behavior(tmp_path: Path) -> None:
    table = _table_with([1.5, 1.5], [1.4, 1.4])
    baseline = RuleEngine().assess(table, ["FY2021", "FY2022"], {})
    assert [f for f in baseline["flags"] if f["rule_id"] == "lev_de"]

    yaml_text = (Path(__file__).resolve().parents[2] / "app" / "finmod"
                 / "risk_thresholds.yaml").read_text()
    tweaked = yaml_text.replace(
        "    medium: 1.0\n    high: 2.0", "    medium: 5.0\n    high: 6.0", 1)
    custom = tmp_path / "custom.yaml"
    custom.write_text(tweaked)
    relaxed = RuleEngine(yaml_path=custom).assess(table, ["FY2021", "FY2022"], {})
    assert not [f for f in relaxed["flags"] if f["rule_id"] == "lev_de"]


def test_novatech_risk_flags() -> None:
    report = run_company(SER, PERIODS, context={"top_customer_concentration": 14.2})
    ids = {f["rule_id"] for f in report["risk"]["flags"]}
    # The receivables-drag story we built into the fixtures must fire:
    assert {"eq_ocf_ebitda", "eq_fcf_negative", "cov_interest",
            "lev_de", "prof_margin_trend"} <= ids
    assert 0 <= report["risk"]["composite_score"] <= 100


# --- Property tests (seeded, dependency-free; hypothesis variant in playbook) --

def test_property_ev_identity_and_ordering() -> None:
    rng = random.Random(42)
    for _ in range(25):
        growth = [rng.uniform(2, 18) for _ in range(5)]
        margin = [rng.uniform(12, 30) for _ in range(5)]
        capex = [rng.uniform(3, 12) for _ in range(5)]
        forecast = Forecast(revenue_growth=growth, ebitda_margin=margin,
                            capex_pct_revenue=capex)
        report = run_dcf(SER, PERIODS, AssumptionSet(), forecast)
        bridge = report["bridge"]
        assert bridge["pv_explicit"] + bridge["pv_terminal_gordon"] == \
            pytest.approx(bridge["enterprise_value"], abs=1e-6)
        dfs = [r["discount_factor"] for r in report["rows"]]
        assert all(dfs[i] > dfs[i + 1] for i in range(len(dfs) - 1))
        full = run_company(SER, PERIODS, AssumptionSet(), forecast)["scenarios"]
        base_ps = full["base"]["per_share_inr"]
        if base_ps and base_ps > 0:  # negative-FCFF models invert ordering
            assert full["bear"]["per_share_inr"] <= base_ps \
                <= full["bull"]["per_share_inr"]


def test_property_dupont_ties() -> None:
    rng = random.Random(7)
    series = {k: [v * rng.uniform(0.8, 1.25) for v in vals]
              for k, vals in SER.items()}
    series["revenue"] = SER["revenue"]
    table = compute_metrics(series, PERIODS)
    for period in PERIODS[1:]:
        roe = table.get("roe", period).value
        dupont = table.get("dupont_roe", period).value
        if roe is not None and dupont is not None:
            assert dupont == pytest.approx(roe, rel=1e-9)


def test_golden_byte_stability() -> None:
    a = run_company(SER, PERIODS)
    b = run_company(SER, PERIODS)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
