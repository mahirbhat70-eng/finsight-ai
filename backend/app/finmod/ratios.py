"""Ratio engine (Playbook P2.1) — growth, margins, returns (incl. DuPont and
ROIC), leverage, liquidity, earnings quality, and working-capital efficiency.

Pure functions over {canonical_key: [values aligned to periods]}.
No DB, no LLM, no rounding inside computations.

Note on the total-assets proxy: the canonical 26-key taxonomy has no
total_assets / ppe / dtl keys, so assets are proxied as
    total_equity + current_liabilities + lt_debt
(= assets minus spontaneous non-current liabilities such as DTL). On the
NovaTech fixture this is within ~1.2% of the true generated assets. With a
richer taxonomy, swap the proxy for the real total_assets series.
"""

from app.finmod.lineage import FinancialResult, ResultTable

ASSETS_PROXY_FORMULA = "total_equity + current_liabilities + lt_debt"


def _v(series: dict[str, list[float]], key: str, t: int) -> float | None:
    row = series.get(key)
    if row is None or t >= len(row):
        return None
    return row[t]


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_metrics(series: dict[str, list[float]], periods: list[str]) -> ResultTable:
    table = ResultTable()
    n = len(periods)

    def add(key: str, label: str, value: float | None, unit: str,
            formula: str, inputs: dict[str, float], t: int,
            lineage: list[str]) -> None:
        table.add(FinancialResult(
            key=key, label=label, value=value, unit=unit, formula=formula,
            inputs=inputs, period=periods[t], lineage=lineage))

    assets_proxy = [
        (_v(series, "total_equity", t) or 0)
        + (_v(series, "current_liabilities", t) or 0)
        + (_v(series, "lt_debt", t) or 0)
        for t in range(n)
    ]

    for t in range(n):
        rev = _v(series, "revenue", t)
        gp = _v(series, "gross_profit", t)
        ebitda = _v(series, "ebitda", t)
        ebit = _v(series, "ebit", t)
        pat = _v(series, "pat", t)
        fcf = _v(series, "fcf", t)
        ocf = _v(series, "ocf", t)
        debt = _v(series, "total_debt", t)
        equity = _v(series, "total_equity", t)
        cash = _v(series, "cash", t)
        interest = _v(series, "interest_expense", t)
        ca = _v(series, "current_assets", t)
        cl = _v(series, "current_liabilities", t)
        inv = _v(series, "inventory", t)
        ar = _v(series, "trade_receivables", t)
        ap = _v(series, "trade_payables", t)
        cogs = _v(series, "cogs", t)
        pbt = _v(series, "pbt", t)
        tax = _v(series, "tax_expense", t)

        # --- Growth -------------------------------------------------------
        if t > 0:
            prev_rev = _v(series, "revenue", t - 1)
            growth = _div((rev or 0) - (prev_rev or 0), prev_rev)
            add("revenue_growth", "Revenue growth YoY", growth, "percent",
                "revenue_t / revenue_t-1 - 1",
                {"revenue": rev or 0, "revenue_prev": prev_rev or 0}, t,
                ["revenue"])
        if rev is not None and t >= 3:
            rev0 = _v(series, "revenue", t - 3)
            cagr = _div(rev, rev0)
            if cagr is not None:
                add("revenue_cagr_3y", "Revenue CAGR 3y",
                    cagr ** (1 / 3) - 1 if rev0 else None, "percent",
                    "(revenue_t / revenue_t-3)^(1/3) - 1",
                    {"revenue": rev, "revenue_t3": rev0}, t, ["revenue"])

        # --- Margins ------------------------------------------------------
        for key, label, num in (
                ("gross_margin", "Gross margin", gp),
                ("ebitda_margin", "EBITDA margin", ebitda),
                ("ebit_margin", "EBIT margin", ebit),
                ("pat_margin", "Net margin", pat),
                ("fcf_margin", "FCF margin", fcf)):
            add(key, label, _div(num, rev), "percent",
                f"{key.split('_')[0]} / revenue",
                {"numerator": num or 0, "revenue": rev or 0}, t, ["revenue"])

        # --- Returns ------------------------------------------------------
        add("roe", "Return on equity", _div(pat, equity), "percent",
            "pat / total_equity", {"pat": pat or 0, "equity": equity or 0},
            t, ["pat", "total_equity"])
        add("roa", "Return on assets", _div(pat, assets_proxy[t]), "percent",
            "pat / assets_proxy", {"pat": pat or 0, "assets_proxy": assets_proxy[t]},
            t, ["pat"])
        eff_tax = _div(tax, pbt)
        nopat = None if ebit is None else ebit * (1 - (eff_tax or 0))
        ic = None if debt is None or equity is None or cash is None \
            else debt + equity - cash
        add("roic", "ROIC", _div(nopat, ic), "percent",
            "ebit x (1 - effective tax) / (debt + equity - cash)",
            {"nopat": nopat or 0, "invested_capital": ic or 0}, t,
            ["ebit", "tax_expense", "total_debt", "total_equity", "cash"])

        # --- Leverage -----------------------------------------------------
        nd = None if debt is None or cash is None else debt - cash
        add("debt_to_equity", "Debt / equity", _div(debt, equity), "x",
            "total_debt / total_equity", {"debt": debt or 0, "equity": equity or 0},
            t, ["total_debt", "total_equity"])
        add("net_debt_to_ebitda", "Net debt / EBITDA", _div(nd, ebitda), "x",
            "(total_debt - cash) / ebitda", {"net_debt": nd or 0, "ebitda": ebitda or 0},
            t, ["total_debt", "cash", "ebitda"])
        add("interest_cover", "Interest coverage", _div(ebit, interest), "x",
            "ebit / interest_expense", {"ebit": ebit or 0, "interest": interest or 0},
            t, ["ebit", "interest_expense"])

        # --- Liquidity ----------------------------------------------------
        add("current_ratio", "Current ratio", _div(ca, cl), "x",
            "current_assets / current_liabilities",
            {"current_assets": ca or 0, "current_liabilities": cl or 0}, t,
            ["current_assets", "current_liabilities"])
        quick = None if ca is None or inv is None or cl is None \
            else (ca - inv) / cl if cl else None
        add("quick_ratio", "Quick ratio", quick, "x",
            "(current_assets - inventory) / current_liabilities",
            {"current_assets": ca or 0, "inventory": inv or 0,
             "current_liabilities": cl or 0}, t, ["current_assets", "inventory"])

        # --- Earnings quality ---------------------------------------------
        add("ocf_ebitda", "OCF / EBITDA", _div(ocf, ebitda), "x",
            "ocf / ebitda", {"ocf": ocf or 0, "ebitda": ebitda or 0}, t,
            ["ocf", "ebitda"])
        add("fcf_conversion", "FCF conversion (FCF/PAT)", _div(fcf, pat), "x",
            "fcf / pat", {"fcf": fcf or 0, "pat": pat or 0}, t, ["fcf", "pat"])

        # --- Working capital -----------------------------------------------
        dso = _div((ar or 0) * 365, rev)
        dio = _div((inv or 0) * 365, cogs)
        dpo = _div((ap or 0) * 365, cogs)
        add("dso", "Days sales outstanding", dso, "days", "AR / revenue x 365",
            {"trade_receivables": ar or 0, "revenue": rev or 0}, t,
            ["trade_receivables", "revenue"])
        add("dio", "Days inventory outstanding", dio, "days",
            "inventory / cogs x 365", {"inventory": inv or 0, "cogs": cogs or 0}, t,
            ["inventory", "cogs"])
        add("dpo", "Days payables outstanding", dpo, "days",
            "trade_payables / cogs x 365", {"trade_payables": ap or 0, "cogs": cogs or 0},
            t, ["trade_payables", "cogs"])
        if dso is not None and dio is not None and dpo is not None:
            add("ccc", "Cash conversion cycle", dso + dio - dpo, "days",
                "dso + dio - dpo", {"dso": dso, "dio": dio, "dpo": dpo}, t,
                ["dso", "dio", "dpo"])

        # --- DuPont --------------------------------------------------------
        npm = _div(pat, rev)
        turnover = _div(rev, assets_proxy[t])
        multiplier = _div(assets_proxy[t], equity)
        if npm is not None and turnover is not None and multiplier is not None:
            add("dupont_roe", "DuPont ROE (NPM x turnover x multiplier)",
                npm * turnover * multiplier, "percent",
                "pat/revenue x revenue/assets x assets/equity",
                {"npm": npm, "asset_turnover": turnover,
                 "equity_multiplier": multiplier}, t, ["pat", "revenue", "total_equity"])

    return table
