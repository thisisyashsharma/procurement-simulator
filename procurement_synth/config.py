"""Generator configuration: scale presets, business-rule thresholds and calibration knobs.

Every number that shapes the data lives here so that the starter and full datasets are
produced by exactly the same code path with different `Scale` presets.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 20261022
FISCAL_YEAR = 2026
BASE_CURRENCY = "USD"
PERIOD_START = date(2026, 1, 5)          # first business Monday of FY2026
AS_OF = datetime(2026, 10, 30, 18, 0)    # snapshot: everything after this is "not yet happened"
FY_START = date(2026, 1, 1)
FY_END = date(2026, 12, 31)


@dataclass(frozen=True)
class Scale:
    name: str
    requesters: int
    suppliers: int
    requests: int      # purchase requests, including injected duplicates / split purchases
    rfqs: int          # exact: one RFQ per request in the competitive band
    quotes: int        # exact: supplier responses are allocated to hit this total
    pos: int           # calibration target; actual count is a rule outcome and is reported
    anomaly_factor: float


SCALES = {
    "full": Scale("full", 300, 120, 1200, 500, 1500, 900, 1.0),
    "starter": Scale("starter", 60, 36, 120, 50, 150, 90, 0.2),
}

# ---------------------------------------------------------------- business rules
COMPETITIVE_THRESHOLD_USD = 10_000      # >= this estimated value -> RFQ with >= 3 quotes
MIN_COMPETITIVE_QUOTES = 3
# (upper bound exclusive, tier). Tier decides which approval levels are required.
APPROVAL_TIERS = ((5_000, 1), (25_000, 2), (100_000, 3), (float("inf"), 4))
TIER_LEVELS = {
    1: ("MANAGER",),
    2: ("MANAGER", "DIRECTOR"),
    3: ("MANAGER", "DIRECTOR", "VP"),
    4: ("MANAGER", "DIRECTOR", "VP", "CFO"),
}
TIER_RULE_IDS = {1: "APR-T1", 2: "APR-T2", 3: "APR-T3", 4: "APR-T4"}
ROLE_RANK = {"STAFF": 1, "BUYER": 1, "FINANCE_CONTROLLER": 1, "MANAGER": 2,
             "DIRECTOR": 3, "VP": 4, "CFO": 5, "CEO": 6}
APPROVAL_LIMITS_USD = {"MANAGER": 5_000, "DIRECTOR": 25_000, "VP": 100_000, "CFO": 1_000_000,
                       "CEO": 5_000_000}
# Budget exception: cumulative transfers into a budget may not exceed this share of the
# original allocation, by request priority. LOW priority is never funded over budget.
BUDGET_EXCEPTION_CAP = {"CRITICAL": 0.15, "HIGH": 0.15, "MEDIUM": 0.05, "LOW": 0.0}
CFO_DEFER_THRESHOLD_USD = 250_000       # CFO defers MEDIUM-priority spend at or above this
AWARD_DELIVERY_PREMIUM_MAX = 0.15       # pay up to +15% to meet the need-by date
AWARD_RISK_PREMIUM_MAX = 0.03           # pay up to +3% to avoid a MEDIUM-risk supplier
DUPLICATE_WINDOW_DAYS = 10              # same requester+category+lines within N days
SPLIT_WINDOW_DAYS = 7                   # split-purchase look-back window
PO_CONSOLIDATION_WEEKDAYS = (2,)        # weekly direct-buy PO run, Wednesday 15:00


@dataclass(frozen=True)
class Params:
    """Behavioural knobs (input distributions). Outcomes are still produced by the rules."""
    priority_weights: tuple = (("LOW", 0.14), ("MEDIUM", 0.55), ("HIGH", 0.25), ("CRITICAL", 0.06))
    missing_justification_rate: float = 0.045
    cancel_rate_direct: float = 0.05
    cancel_rate_rfq: float = 0.035
    sole_source_item_rate: float = 0.07      # competitive PRs that need an OEM-only item
    emergency_need_days: int = 10            # CRITICAL + need-by inside this -> single source
    insufficient_bids_rate: float = 0.03     # competitive RFQs that only attract 2 bids
    delayed_evaluation_rate: float = 0.10    # evaluation slips 10-30 days (quotes may expire)
    foreign_local_currency_rate: float = 0.6 # foreign suppliers quoting in local currency
    partial_delivery_rate_scale: float = 1.0
    staff_attrition_rate: float = 0.05
    staff_new_hire_rate: float = 0.06
    supplier_deactivation_rate: float = 0.09
    supplier_suspension_rate: float = 0.04
    supplier_risk_flag_rate: float = 0.28


# Anomaly quotas at full scale (scaled by Scale.anomaly_factor, minimum 2 each).
ANOMALY_QUOTAS = {
    "PO_WITHOUT_APPROVAL": 10,
    "QUOTE_EXPIRED_AT_AWARD": 8,
    "NON_LOWEST_AWARD_NO_RATIONALE": 10,
    "INACTIVE_SUPPLIER": 6,
    "BUDGET_OVERRUN": 6,
    "DUPLICATE_REQUEST": 14,
    "QUOTE_CURRENCY_MISMATCH": 6,
    "SPLIT_PURCHASE": 5,        # groups of 2-3 requests
}


@dataclass(frozen=True)
class RunConfig:
    seed: int = DEFAULT_SEED
    scale: Scale = SCALES["full"]
    params: Params = Params()
    inject_anomalies: bool = True

    def with_(self, **kw) -> "RunConfig":
        return replace(self, **kw)

    def anomaly_quota(self, name: str) -> int:
        if not self.inject_anomalies:
            return 0
        return max(2, round(ANOMALY_QUOTAS[name] * self.scale.anomaly_factor))


def tier_for(amount_usd: float) -> int:
    for bound, tier in APPROVAL_TIERS:
        if amount_usd < bound:
            return tier
    return 4
