"""Klien Spark M0.1 (Responses API, strict, berurutan, cache per hash, cost guard)."""

from .budget import Caps, Ledger, Projection, effective_caps, provider_caps
from .client import (
    BatchResult,
    CallResult,
    SparkClient,
    _quiet_sdk_loggers,
    parse_retry_after,
)
from .errors import BudgetExceeded, ConfigInvalid, NotReportable, UsageInvalid
from .gate import require_reportable
from .money import compute_cost_micros, format_usd_micros
from .runrecord import RunRecord
from .settings import load_configs

_quiet_sdk_loggers()

__all__ = [
    "BatchResult", "BudgetExceeded", "CallResult", "Caps", "ConfigInvalid", "Ledger", "NotReportable",
    "Projection", "RunRecord", "SparkClient", "UsageInvalid", "compute_cost_micros", "effective_caps",
    "provider_caps", "format_usd_micros", "load_configs", "parse_retry_after", "require_reportable",
]
