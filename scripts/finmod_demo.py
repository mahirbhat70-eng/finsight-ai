"""finmod demo CLI (Playbook P2 acceptance): ratios table, WACC, DCF bridge,
scenarios, grid, top-5 flags for NovaTech. No DB needed — runs on fixtures.

Usage: cd backend && python ../scripts/finmod_demo.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.finmod.dcf import Forecast
from app.finmod.engine import load_series_from_fixture, run_company
from app.finmod.wacc import AssumptionSet

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def fmt_inr(value: float) -> str:
    return f"Rs {value:,.1f} Cr"


def main() -> int:
    series, periods = load_series_from_fixture(
        str(FIXTURES / "novatech_statements.json"))
    gt = json.loads((FIXTURES / "novatech_ground_truth.json").read_text())
    report = run_company(series, periods,
                         AssumptionSet(current_price=150.0), Forecast(),
                         context={"top_customer_concentration":
                                  gt.get("concentration_pct")})

    print("=" * 72)
    print("FinSight AI — deterministic engine demo | NovaTech Industries Ltd")
    print("=" * 72)

    print("\n--- Key ratios (FY2025) ---")
    for key in ("revenue_growth", "ebitda_margin", "pat_margin", "roe", "roic",
                "debt_to_equity", "net_debt_to_ebitda", "interest_cover",
                "current_ratio", "ocf_ebitda", "dso", "ccc"):
        res = report["metrics"].get(key, {}).get("FY2025")
        if res:
            unit = res["unit"]
            value = (f"{res['value'] * 100:.1f}%" if unit == "percent"
                     else f"{res['value']:.2f}x" if unit in ("x",)
                     else f"{res['value']:.0f}" if unit == "days"
                     else f"{res['value']:.2f}")
            print(f"  {res['label']:<38} {value:>10}   [{res['formula']}]")

    print("\n--- WACC ---")
    print(f"  cost of equity (CAPM)   14.475%   [7.0 + 1.15 x 6.5]")
    print(f"  WACC                    {report['wacc'] * 100:.3f}%")
    print(f"  weights                 E/V 41.7%  D/V 58.3% (book proxy)")

    print("\n--- DCF bridge (base) ---")
    bridge = report["dcf"]["bridge"]
    rows = report["dcf"]["rows"]
    print(f"  {'year':>4} {'revenue':>10} {'ebitda':>9} {'fcff':>9} "
          f"{'df':>7} {'pv':>10}")
    for r in rows:
        print(f"  {r['year']:>4} {r['revenue']:>10,.0f} {r['ebitda']:>9,.0f} "
              f"{r['fcff']:>9,.0f} {r['discount_factor']:>7.3f} {r['pv']:>10,.0f}")
    print(f"  PV(explicit)            {fmt_inr(bridge['pv_explicit'])}")
    print(f"  PV(terminal, Gordon)    {fmt_inr(bridge['pv_terminal_gordon'])}")
    print(f"  Enterprise value        {fmt_inr(bridge['enterprise_value'])}")
    print(f"  less net debt           {fmt_inr(-bridge['net_debt'])}")
    print(f"  Equity value            {fmt_inr(bridge['equity_value'])}")
    print(f"  Per share (742mn dil.)  Rs {bridge['per_share_inr']:,.2f}")
    x = bridge["tv_exit_crosscheck"]
    print(f"  exit-multiple x-check   EV {fmt_inr(x['ev_exit_method'])} "
          f"(spread {x['spread_vs_gordon']:+.1%})")

    print("\n--- Checks ---")
    for name, check in report["dcf"]["checks"].items():
        print(f"  [{check['severity'].upper():>4}] {name}: {check['detail']}")

    print("\n--- Scenarios ---")
    for name, s in report["scenarios"].items():
        vs = ((s["per_share_inr"] / 150.0 - 1) * 100) if s["per_share_inr"] else None
        print(f"  {name:>5}: Rs {s['per_share_inr']:>8,.2f}/share "
              f"({vs:+.0f}% vs current Rs 150)")

    print("\n--- Sensitivity grid (per share) ---")
    grid = report["sensitivity"]
    header = "  WACC\\g  " + "".join(f"{g:>9.1f}%" for g in grid["g_axis"])
    print(header)
    for w, row in zip(grid["wacc_axis"], grid["per_share"]):
        cells = "".join("        —" if v is None else f"{v:>9,.0f}" for v in row)
        print(f"  {w:>5.2f}%{cells}")

    print("\n--- Tornado (top 5) ---")
    for t in report["tornado"][:5]:
        print(f"  {t['driver']:<16} impact Rs {t['impact']:>7,.2f}/share "
              f"({t['impact_pct']:.0%})")

    print("\n--- Risk flags ---")
    for flag in report["risk"]["flags"]:
        print(f"  [{flag['severity'].upper():>6}] {flag['rule_id']:<20} "
              f"{flag['rationale']}")
    print(f"  composite score: {report['risk']['composite_score']}/100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
