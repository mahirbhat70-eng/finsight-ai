"""NovaTech Industries Ltd — deterministic 5-year model (Playbook P1.3).

All amounts INR crore unless noted; fiscal years end March; seed 42.

Articulation design (how a bank ties three statements):
- The P&L is pinned: revenue, EBITDA/gross margin schedules, D&A % of
  revenue, capex per year (incl. the FY24 2,140 Cr capacity-expansion spike),
  25.17% tax, 20% payout.
- Working capital is driven by days schedules (DSO 58->71, DIO, DPO).
- Cash follows a pinned policy path [540, 560, 560, 350, 910] Cr on top of a
  480 Cr opening balance (playbook endpoint: cash 480 -> 910).
- DEBT is the residual plug: each year solves
      debt -> interest (9.2% on avg debt) -> PAT -> dividends -> equity -> plug
  by fixed-point iteration (converges in < 10 passes, tolerance 1e-9).
- The opening (FY2020) balance sheet is constructed to tie, with PPE_0 solved.
- Asserted every year: BS identity, equity roll, PPE roll, and
  cash_t == cash_{t-1} + CFO + CFI + CFF (double-entry proof).

Playbook endpoints honored: FY21 debt lands ~2,900 Cr, cash 480 -> 910 Cr.
The FY24 capex spike forces FY24/25 debt materially above the playbook's
illustrative "3,400" — the asserts keep the model honest rather than fudging
a number to match a narrative.
"""

from dataclasses import dataclass, field

TOL = 1e-6
PERIODS = ("FY2021", "FY2022", "FY2023", "FY2024", "FY2025")

CANONICAL_ORDER = (
    "revenue", "cogs", "gross_profit", "opex", "ebitda", "dna", "ebit",
    "interest_expense", "other_income", "pbt", "tax_expense", "pat",
    "cash", "trade_receivables", "inventory", "current_assets",
    "trade_payables", "current_liabilities", "st_borrowings", "lt_debt",
    "total_debt", "total_equity", "shares_outstanding", "ocf", "capex", "fcf",
)


@dataclass(frozen=True)
class NovaTechConfig:
    seed: int = 42
    periods: tuple[str, ...] = PERIODS

    # --- P&L pins ---------------------------------------------------------
    revenue: tuple[float, ...] = (4120.0, 4860.0, 5720.0, 6610.0, 7340.0)
    ebitda_margin: tuple[float, ...] = (0.241, 0.234, 0.216, 0.209, 0.213)
    gross_margin: tuple[float, ...] = (0.320, 0.314, 0.302, 0.296, 0.301)
    dna_pct_revenue: float = 0.042
    other_income_pct_revenue: float = 0.011
    interest_rate: float = 0.092           # average coupon of the debt schedule
    tax_rate: float = 0.2517               # India combined effective, configurable
    dividend_payout: float = 0.20

    # --- Cash flow / capex pins (FY24 spike = capacity expansion) ----------
    capex: tuple[float, ...] = (520.0, 610.0, 700.0, 2140.0, 780.0)

    # --- Working capital days ----------------------------------------------
    receivable_days: tuple[float, ...] = (58.0, 62.0, 66.0, 69.0, 71.0)
    inventory_days: tuple[float, ...] = (74.0, 76.0, 78.0, 79.0, 80.0)   # on COGS
    payable_days: tuple[float, ...] = (96.0, 98.0, 100.0, 102.0, 104.0)  # on COGS
    oca_pct_revenue: float = 0.030
    ocl_pct_revenue: float = 0.025

    # --- Balance sheet policy -----------------------------------------------
    cash_policy: tuple[float, ...] = (540.0, 560.0, 560.0, 350.0, 910.0)  # FY21..25
    st_share_of_debt: float = 0.25
    shares: tuple[float, ...] = (738.0, 739.0, 740.0, 741.0, 742.0)  # mn, diluted
    esop_price: float = 300.0                                         # INR/share
    onca_open: float = 340.0
    onca_growth: float = 0.03
    dtl_open: float = 180.0
    dtl_growth: float = 0.05

    # --- Opening balance sheet (FY2020 close) --------------------------------
    cash_open: float = 480.0
    debt_open: float = 2800.0
    equity_open: float = 1200.0
    open_gross_margin: float = 0.325
    open_receivable_days: float = 55.0
    open_inventory_days: float = 72.0
    open_payable_days: float = 94.0

    # --- Narrative pins used by the PDF / ground truth ------------------------
    customer_a_concentration: float = 0.142
    narrative: dict = field(default_factory=lambda: {
        "fy24_capex_note": "greenfield capacity expansion",
        "sector": "industrial automation & precision components",
    })


def _solve_debt(assets: float, liab_ex_debt: float, prior_equity: float,
                prior_debt: float, rate: float, tax: float, payout: float,
                esop: float, ebit: float, other_income: float) -> tuple[float, dict]:
    """Fixed point: debt -> interest -> PAT -> dividends -> equity -> plug.

    Sensitivity of the plug to debt is ~ (1 - (1-tax)*(1-payout)*rate/2) < 1,
    so plain iteration converges geometrically.
    """
    debt = prior_debt
    for _ in range(60):
        interest = rate * (prior_debt + debt) / 2.0
        pbt = ebit - interest + other_income
        pat = pbt * (1.0 - tax)
        dividends = payout * pat
        equity = prior_equity + pat - dividends + esop
        new_debt = assets - liab_ex_debt - equity
        if abs(new_debt - debt) < 1e-9:
            debt = new_debt
            break
        debt = new_debt
    interest = rate * (prior_debt + debt) / 2.0
    pbt = ebit - interest + other_income
    pat = pbt * (1.0 - tax)
    dividends = payout * pat
    equity = prior_equity + pat - dividends + esop
    return debt, {"interest": interest, "pbt": pbt, "pat": pat,
                  "dividends": dividends, "equity": equity}


def build_model(cfg: NovaTechConfig = NovaTechConfig()) -> dict:
    """Return the fully articulated NovaTech model (canonical keys -> 5y series)."""
    # --- Opening balance sheet (FY2020) ------------------------------------
    rev0 = cfg.revenue[0] / 1.18
    cogs0 = rev0 * (1.0 - cfg.open_gross_margin)
    ar0 = rev0 * cfg.open_receivable_days / 365.0
    inv0 = cogs0 * cfg.open_inventory_days / 365.0
    ap0 = cogs0 * cfg.open_payable_days / 365.0
    oca0 = rev0 * cfg.oca_pct_revenue
    ocl0 = rev0 * cfg.ocl_pct_revenue
    ppe0 = ((cfg.debt_open + ap0 + ocl0 + cfg.dtl_open + cfg.equity_open)
            - (cfg.cash_open + ar0 + inv0 + oca0 + cfg.onca_open))

    prev = {"cash": cfg.cash_open, "ar": ar0, "inv": inv0, "oca": oca0,
            "ap": ap0, "ocl": ocl0, "dtl": cfg.dtl_open, "onca": cfg.onca_open,
            "ppe": ppe0, "debt": cfg.debt_open, "equity": cfg.equity_open,
            "shares": cfg.shares[0] - 1.0, "revenue": rev0, "cogs": cogs0}

    years: list[dict] = []
    openings: list[dict] = []
    for t in range(len(cfg.periods)):
        openings.append(dict(prev))
        rev = cfg.revenue[t]
        cogs = rev * (1.0 - cfg.gross_margin[t])
        gp = rev - cogs
        ebitda = rev * cfg.ebitda_margin[t]
        opex = gp - ebitda
        dna = rev * cfg.dna_pct_revenue
        ebit = ebitda - dna
        other_income = rev * cfg.other_income_pct_revenue

        ar = rev * cfg.receivable_days[t] / 365.0
        inv = cogs * cfg.inventory_days[t] / 365.0
        ap = cogs * cfg.payable_days[t] / 365.0
        oca = rev * cfg.oca_pct_revenue
        ocl = rev * cfg.ocl_pct_revenue
        onca = cfg.onca_open * (1.0 + cfg.onca_growth) ** (t + 1)
        dtl = cfg.dtl_open * (1.0 + cfg.dtl_growth) ** (t + 1)
        ppe = prev["ppe"] + cfg.capex[t] - dna
        cash = cfg.cash_policy[t]
        esop = (cfg.shares[t] - prev["shares"]) * cfg.esop_price / 10.0  # mn*INR -> Cr

        debt, solved = _solve_debt(
            assets=cash + ar + inv + oca + onca + ppe,
            liab_ex_debt=ap + ocl + dtl,
            prior_equity=prev["equity"], prior_debt=prev["debt"],
            rate=cfg.interest_rate, tax=cfg.tax_rate, payout=cfg.dividend_payout,
            esop=esop, ebit=ebit, other_income=other_income)
        equity = solved["equity"]

        st = cfg.st_share_of_debt * debt
        current_assets = cash + ar + inv + oca
        current_liabilities = ap + ocl + st

        # Cash-flow articulation (double-entry proof)
        d_ar, d_inv, d_oca = ar - prev["ar"], inv - prev["inv"], oca - prev["oca"]
        d_ap, d_ocl, d_dtl = ap - prev["ap"], ocl - prev["ocl"], dtl - prev["dtl"]
        d_onca = onca - prev["onca"]
        cfo = solved["pat"] + dna + d_dtl + d_ap + d_ocl - d_ar - d_inv - d_oca
        cfi = -cfg.capex[t] - d_onca
        cff = (debt - prev["debt"]) + esop - solved["dividends"]
        assert abs((cash - prev["cash"]) - (cfo + cfi + cff)) < 1e-6, \
            f"cash flow does not tie in {cfg.periods[t]}"

        years.append({
            "period": cfg.periods[t], "revenue": rev, "cogs": cogs,
            "gross_profit": gp, "opex": opex, "ebitda": ebitda, "dna": dna,
            "ebit": ebit, "interest_expense": solved["interest"],
            "other_income": other_income, "pbt": solved["pbt"],
            "tax_expense": solved["pbt"] - solved["pat"], "pat": solved["pat"],
            "cash": cash, "trade_receivables": ar, "inventory": inv,
            "current_assets": current_assets, "trade_payables": ap,
            "current_liabilities": current_liabilities,
            "st_borrowings": st, "lt_debt": debt - st, "total_debt": debt,
            "total_equity": equity, "shares_outstanding": cfg.shares[t],
            "ocf": cfo, "capex": cfg.capex[t], "fcf": cfo - cfg.capex[t],
            "dividends": solved["dividends"], "esop": esop,
            "ppe": ppe, "onca": onca, "dtl": dtl, "oca": oca, "ocl": ocl,
            "dso": ar / rev * 365.0, "dio": inv / cogs * 365.0,
            "dpo": ap / cogs * 365.0, "cfo": cfo, "cfi": cfi, "cff": cff,
        })
        prev = dict(prev, cash=cash, ar=ar, inv=inv, oca=oca, ap=ap, ocl=ocl,
                    dtl=dtl, onca=onca, ppe=ppe, debt=debt, equity=equity,
                    shares=cfg.shares[t], revenue=rev, cogs=cogs)

    # --- Articulation asserts ------------------------------------------------
    for y, p in zip(years, openings):
        assets = y["current_assets"] + y["ppe"] + y["onca"]
        liabilities = y["current_liabilities"] + y["lt_debt"] + y["dtl"]
        assert abs(assets - liabilities - y["total_equity"]) < 1e-4, \
            f"BS does not tie in {y['period']}"
        assert abs(p["equity"] + y["pat"] - y["dividends"] + y["esop"]
                   - y["total_equity"]) < 1e-4, f"equity roll fails in {y['period']}"
        assert abs(p["ppe"] + y["capex"] - y["dna"] - y["ppe"]) < 1e-4, \
            f"PPE roll fails in {y['period']}"
        assert abs((y["cash"] - p["cash"])
                   - (y["cfo"] + y["cfi"] + y["cff"])) < 1e-4, \
            f"cash movement does not tie in {y['period']}"
        assert y["cash"] > 0, f"negative cash in {y['period']}"
        assert y["total_debt"] > 0, f"negative debt in {y['period']}"

    for y in years:  # P&L identities
        assert abs(y["revenue"] - y["cogs"] - y["gross_profit"]) < 1e-6
        assert abs(y["gross_profit"] - y["opex"] - y["ebitda"]) < 1e-6
        assert abs(y["ebitda"] - y["dna"] - y["ebit"]) < 1e-6
        assert abs(y["ebit"] - y["interest_expense"] + y["other_income"]
                   - y["pbt"]) < 1e-6
        assert abs(y["pbt"] - y["tax_expense"] - y["pat"]) < 1e-6

    # Endpoint sanity vs the playbook narrative
    assert abs(years[-1]["cash"] - 910.0) < 1e-9
    assert 2_700 < years[0]["total_debt"] < 3_100, "FY21 debt should land near 2,900"

    items = {key: [y[key] for y in years] for key in CANONICAL_ORDER}
    return {
        "company": "NovaTech Industries Ltd",
        "periods": list(cfg.periods),
        "currency": "INR",
        "unit": "INR_cr",
        "items": items,
        "years": years,
        "openings": openings,
        "config": cfg,
    }


def summarize(model: dict) -> str:
    """Terminal summary table (Playbook P1.3 asks for a 3-line paste)."""
    lines = ["period    revenue  ebitda%     pat    cash    debt  ND/EBITDA  OCF/EBITDA"]
    for y in model["years"]:
        nd = (y["total_debt"] - y["cash"]) / y["ebitda"]
        oq = y["ocf"] / y["ebitda"]
        lines.append(
            f"{y['period']}  {y['revenue']:>8,.0f}  {y['ebitda'] / y['revenue']:>6.1%}"
            f"  {y['pat']:>7,.0f}  {y['cash']:>6,.0f}  {y['total_debt']:>6,.0f}"
            f"  {nd:>9.2f}x  {oq:>10.2f}x")
    return "\n".join(lines)


if __name__ == "__main__":
    m = build_model()
    print(summarize(m))
    print(f"\nPPE_0 (solved opening) = {m['openings'][0]['ppe']:,.1f} Cr")
    print(f"FY2021 debt = {m['years'][0]['total_debt']:,.1f} Cr (playbook: ~2,900)")
    print(f"FY2025 debt = {m['years'][-1]['total_debt']:,.1f} Cr, "
          f"cash = {m['years'][-1]['cash']:,.1f} Cr (pinned 910)")
    print(f"FY2025 total equity = {m['years'][-1]['total_equity']:,.1f} Cr")
