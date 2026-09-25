"""
Configuration for the V2 risk engine.

Every value is a design choice, and each is tagged with how much authority it
carries. Nothing here is quoted from an MPLADS guideline document, because none
of the supplied exports establishes one.

  verified      confirmed against an official source            (currently none)
  configurable  an administrative threshold a district can set
  heuristic     an analytical screening choice made by us
  data_quality  a check on the record rather than the work
"""

from dataclasses import dataclass, field

ENGINE_VERSION = "v2.0"
CONFIG_VERSION = "risk-v2-1"

INDICATORS = [
    "cost_deviation",
    "timeline",
    "expenditure_consistency",
    "similarity",
    "compliance",
    "multivariate",
]

INDICATOR_LABELS = {
    "cost_deviation": "Cost deviation from peers",
    "timeline": "Timeline indicator",
    "expenditure_consistency": "Expenditure consistency",
    "similarity": "Potentially similar work",
    "compliance": "Rule-based indicator",
    "multivariate": "Unusual combination of indicators",
}

# Maximum points (of 100) a single indicator can contribute on its own. These
# are caps under a noisy-OR combination, not shares of a weighted average, so
# they deliberately do not sum to 1.
CAPS = {
    "cost_deviation": 0.55,
    "timeline": 0.30,
    "expenditure_consistency": 0.50,
    "similarity": 0.45,
    "compliance": 0.60,
    "multivariate": 0.30,
}

# How much authority a rule tier carries. A data-quality flag and a financial
# inconsistency are not the same kind of statement, and weighting them equally
# is what pushed a quarter of the register into the High band on the first run:
# 4,269 works are "completed with no payment record", which is overwhelmingly a
# records gap rather than a finding about the work.
RULE_TIER_WEIGHT = {
    "verified": 1.00,
    "financial_consistency": 0.90,
    "configurable": 0.75,
    "heuristic": 0.45,
    "data_quality": 0.30,
}


@dataclass
class Thresholds:
    # --- peer grouping -----------------------------------------------------
    # A peer group smaller than this cannot support a comparison. 8 is a
    # heuristic: below it the median and MAD are dominated by a few records.
    min_peer_group: int = 8

    # --- cost --------------------------------------------------------------
    # Robust z-score, computed in log space because sanction amounts are
    # right-skewed by orders of magnitude. Only the upper tail is scored: a
    # work costing far less than its peers is a saving or a data problem, not
    # the pattern this system exists to surface.
    cost_z_saturate: float = 4.0

    # --- timeline ----------------------------------------------------------
    # Expressed as a multiple of the peer group's own median duration, because
    # no official category deadline exists in any supplied file. Anything based
    # on a fixed day count would be invented.
    duration_tolerance_ratio: float = 1.5
    duration_saturate_ratio: float = 4.0
    # Calibrated from the supplied register rather than guessed: the median
    # recommendation-to-sanction lag is 70 days and the 90th percentile is 257,
    # so a 180-day "tolerance" was scoring ordinary administrative timing.
    lag_tolerance_percentile: float = 0.90
    lag_saturate_percentile: float = 0.99

    # --- expenditure -------------------------------------------------------
    # Nothing in the supplied data disburses above sanction, so over-spend is
    # not the signal here. Under-disbursement against a completed work is.
    # 25% of completed works sit at exactly 1.00 and the 10th percentile is
    # 0.994, so a shortfall only becomes notable below about 0.85.
    underspend_tolerance: float = 0.85
    underspend_saturate: float = 0.40
    # 95th percentile of payment count is 3 and the 99th is 13; fragmentation
    # starts above the 95th rather than at an arbitrary 3.
    payment_count_percentile: float = 0.95
    payment_count_saturate: int = 20

    # --- recommendation against sanction -----------------------------------
    # A sanction above the recommended amount is ordinary within a small
    # margin -- estimates are refined between recommendation and sanction.
    # Beyond it, the gap is worth a reviewer's attention.
    max_sanction_uplift_pct: float = 15.0
    uplift_saturate_pct: float = 100.0

    # --- similarity --------------------------------------------------------
    similarity_floor: float = 0.62
    similarity_block_max: int = 900

    # --- bands -------------------------------------------------------------
    # Chosen so the High band is a queue a district team could actually work
    # through, not a quarter of the register. Reviewed against the real score
    # distribution and recorded in the export.
    band_high: float = 70.0
    band_medium: float = 50.0


# How much a cost comparison can be trusted, by the peer level it fell back to.
# Half the register lands on "category + state", where the category is 97%
# "Normal/Others" and the comparison puts a road beside a classroom. A score
# built on that is not as trustworthy as one built on a work-type peer group,
# and confidence is where that difference has to show up.
PEER_LEVEL_STRENGTH = {
    "work_type + state": 1.00,
    "work_type": 0.85,
    "category + state": 0.45,
    "state": 0.25,
    "insufficient": 0.00,
}


@dataclass
class ModelParams:
    isolation_forest_estimators: int = 300
    contamination: float = 0.06
    dbscan_eps: float = 1.2
    dbscan_min_samples: int = 10
    random_state: int = 42
    multivariate_percentile_floor: float = 0.85
    min_rows_to_fit: int = 200


# ---------------------------------------------------------------- rules

@dataclass
class Rule:
    rule_id: str
    name: str
    rule_type: str
    source: str
    required_fields: list
    severity: float
    explanation: str
    enabled: bool = True


RULES = [
    Rule("FIN_001", "Total expenditure exceeds sanctioned amount", "financial_consistency",
         "Prototype analytical rule", ["total_expenditure", "sanction_amount"], 0.8,
         "Recorded disbursement is larger than the sanctioned amount."),
    Rule("FIN_002", "Single payment exceeds sanctioned amount", "financial_consistency",
         "Prototype analytical rule", ["max_single_payment", "sanction_amount"], 0.7,
         "One payment alone is larger than the amount sanctioned for the work."),
    Rule("FIN_003", "Completed work with no recorded expenditure", "data_quality",
         "Prototype analytical rule", ["completion_date", "total_expenditure"], 0.45,
         "The work is recorded as completed but carries no payment record."),
    Rule("DATE_001", "First payment precedes the sanction date", "financial_consistency",
         "Prototype analytical rule", ["first_payment_date", "sanction_date"], 0.7,
         "A payment is dated before the work was sanctioned."),
    Rule("DATE_002", "Completion precedes sanction", "data_quality",
         "Prototype analytical rule", ["completion_date", "sanction_date"], 0.6,
         "The completion date is earlier than the sanction date."),
    Rule("DATE_003", "Long delay between recommendation and sanction", "heuristic",
         "Configurable screening threshold", ["days_recommendation_to_sanction"], 0.35,
         "An unusually long gap between the MP's recommendation and sanction."),
    Rule("CEIL_001", "Sanctioned amount above the configured single-work ceiling",
         "configurable", "Administrative threshold, NOT verified against a guideline edition",
         ["sanction_amount"], 0.5,
         "The sanctioned amount exceeds the ceiling configured for a single work."),
    Rule("DUP_001", "Identical description to another work in the same district",
         "heuristic", "Prototype analytical rule", ["description_normalised", "district"], 0.5,
         "Another work in the same district carries an identical description."),
    # Retained deliberately so the interface can report them as unevaluated
    # rather than as passed. Neither field exists in any supplied export.
    Rule("COMP_001", "Work falls in an inadmissible category", "configurable",
         "Requires a verified guideline category list", ["inadmissible_category"], 1.0,
         "The work category is not admissible under the scheme."),
    # Previously dead: it required a revised-cost field that no export carries.
    # The recommendation register supplies what the MP originally recommended,
    # which makes the same question answerable from real data.
    Rule("COST_002", "Sanctioned materially above the amount recommended",
         "financial_consistency", "Recommendation register compared against sanction",
         ["sanction_uplift_pct"], 0.55,
         "The sanctioned amount exceeds what the Member of Parliament recommended "
         "by more than the configured margin."),
]


@dataclass
class RiskConfig:
    thresholds: Thresholds = field(default_factory=Thresholds)
    model: ModelParams = field(default_factory=ModelParams)
    rules: list = field(default_factory=lambda: list(RULES))
    # Prototype value. 106 of the supplied works exceed it. It is NOT taken
    # from a guideline document and must be confirmed before real use.
    single_work_ceiling: float = 1_00_00_000
    caps: dict = field(default_factory=lambda: dict(CAPS))
    engine_version: str = ENGINE_VERSION
    config_version: str = CONFIG_VERSION
