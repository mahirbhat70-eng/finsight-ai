"""API v1 routers."""

from app.api.v1 import (companies, copilot, exports, filings, metrics, peers,
                         review, risk, valuation)

ALL_ROUTERS = [companies.router, metrics.router, valuation.router, risk.router,
               filings.router, review.router, copilot.router, peers.router,
               exports.router]

__all__ = ["ALL_ROUTERS"]
