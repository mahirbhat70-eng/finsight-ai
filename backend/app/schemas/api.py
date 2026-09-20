"""API request/response contracts (Pydantic). Reuse finmod's AssumptionSet
and Forecast as the wire format so the LLM, the API, and the engine agree
on one schema."""

from pydantic import BaseModel

from app.finmod.dcf import Forecast
from app.finmod.wacc import AssumptionSet

__all__ = ["ValuationRequest", "CompanyIn", "OverviewOut"]


class ValuationRequest(BaseModel):
    assumptions: AssumptionSet = AssumptionSet()
    forecast: Forecast = Forecast()
    persist: bool = True


class CompanyIn(BaseModel):
    name: str
    sector: str = ""
    currency: str = "INR"
    fiscal_year_end: str = "March"


class OverviewOut(BaseModel):
    company_id: str
    name: str
    periods: list[str]
    latest: dict
    risk: dict
