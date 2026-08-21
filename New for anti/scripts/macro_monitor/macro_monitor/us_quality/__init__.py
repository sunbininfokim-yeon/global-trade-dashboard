"""Point-in-time U.S. macro quality models.

The package classifies composition and evidence.  It deliberately does not
forecast CPI, payrolls, GDP, policy rates, or market prices.
"""

from .backtest import assess_lag_evidence, audit_point_in_time
from .cpi import assess_current_cpi_pathway
from .documents import build_document_index
from .employment import classify_employment_quality
from .fomc import compare_fomc_meetings
from .fed import build_fed_official_input
from .gdp import classify_gdp_quality

__all__ = [
    "assess_lag_evidence",
    "assess_current_cpi_pathway",
    "audit_point_in_time",
    "build_document_index",
    "classify_employment_quality",
    "classify_gdp_quality",
    "compare_fomc_meetings",
    "build_fed_official_input",
]
