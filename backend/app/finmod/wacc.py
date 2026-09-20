"""WACC (Playbook P2.2): CAPM cost of equity, after-tax cost of debt,
book-or-market weights from the latest balance sheet.

Indian defaults: rf 7.0% (10Y G-Sec), MRP 6.5%, CoD 9.2% pre-tax, tax 25.17%.
Weights default to book (market value proxy = book per the playbook); pass
market_value_equity to weight at market.
"""

from pydantic import BaseModel, Field, model_validator

from app.finmod.lineage import FinancialResult, ResultTable

# Playbook guardrails: beta <= 0, tax >= 0.7, negative rf all raise.


class AssumptionSet(BaseModel):
    rf: float = Field(7.0, description="Risk-free rate, % (10Y G-Sec)")
    beta: float = Field(1.15, gt=0, description="Levered beta")
    market_risk_premium: float = Field(6.5, gt=0, description="Equity risk premium, %")
    size_premium: float = Field(0.0, ge=0, description="Small-cap premium, %")
    cost_of_debt_pre_tax: float = Field(9.2, gt=0, description="Pre-tax cost of debt, %")
    tax_rate: float = Field(25.17, gt=0, lt=50, description="Tax rate, %")
    market_value_equity: float | None = Field(
        None, description="Optional market cap (INR cr); None -> book equity proxy")
    mid_year: bool = Field(True, description="Mid-year discounting convention")
    terminal_growth: float = Field(5.0, description="Gordon terminal growth, %")
    exit_multiple: float = Field(9.0, description="EV/EBITDA exit multiple (cross-check)")
    current_price: float | None = Field(
        None, description="Current market price per share for % vs fair value")

    @model_validator(mode="after")
    def _sanity(self) -> "AssumptionSet":
        if self.rf < 0:
            raise ValueError("risk-free rate cannot be negative")
        if self.terminal_growth >= 20:
            raise ValueError("terminal growth looks like a typo (>= 20%)")
        return self


def compute_wacc(assumptions: AssumptionSet,
                 series: dict[str, list[float]],
                 periods: list[str]) -> tuple[float, ResultTable]:
    """Return (wacc_decimal, lineage table). Latest balance sheet drives weights."""
    t = len(periods) - 1

    def latest(key: str) -> float:
        return series[key][t]

    equity = (assumptions.market_value_equity if assumptions.market_value_equity
              else latest("total_equity"))
    debt = latest("total_debt")
    v = equity + debt
    if v <= 0:
        raise ValueError("equity + debt must be positive to weight WACC")

    ke = (assumptions.rf + assumptions.beta * assumptions.market_risk_premium
          + assumptions.size_premium) / 100.0
    kd_at = (assumptions.cost_of_debt_pre_tax
             * (1 - assumptions.tax_rate / 100.0)) / 100.0
    w_e, w_d = equity / v, debt / v
    wacc = w_e * ke + w_d * kd_at

    table = ResultTable()
    table.add(FinancialResult(
        key="cost_of_equity", label="Cost of equity (CAPM)", value=ke,
        unit="percent", formula="rf + beta x MRP + size premium",
        inputs={"rf": assumptions.rf, "beta": assumptions.beta,
                "mrp": assumptions.market_risk_premium,
                "size_premium": assumptions.size_premium},
        period="latest", lineage=["assumptions"]))
    table.add(FinancialResult(
        key="cost_of_debt_at", label="After-tax cost of debt", value=kd_at,
        unit="percent", formula="cost_of_debt x (1 - tax)",
        inputs={"cost_of_debt": assumptions.cost_of_debt_pre_tax,
                "tax": assumptions.tax_rate},
        period="latest", lineage=["assumptions"]))
    table.add(FinancialResult(
        key="wacc", label="WACC", value=wacc, unit="percent",
        formula="E/V x Ke + D/V x Kd_at",
        inputs={"equity": equity, "debt": debt, "w_e": w_e, "w_d": w_d,
                "ke": ke, "kd_at": kd_at},
        period="latest", lineage=["cost_of_equity", "cost_of_debt_at",
                                  "total_equity", "total_debt"]))
    return wacc, table
