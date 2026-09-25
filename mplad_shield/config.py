"""
Domain constants and tunable parameters for the MPLAD-SHIELD risk engine.

Every threshold here is a policy choice, not a discovered fact. They are kept in
one place so a district authority can tune them without touching detector code.
Values marked CONFIGURABLE are illustrative defaults chosen to be plausible for
MPLADS; they should be replaced with the figures in the guideline edition that
actually applies before the system is used on real sanctions.
"""

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Scheme constants
# --------------------------------------------------------------------------

# Annual entitlement per MP, released in two instalments (CONFIGURABLE).
ANNUAL_ENTITLEMENT = 5_00_00_000  # Rs 5 crore

# Ceiling on a single sanctioned work (CONFIGURABLE).
SINGLE_WORK_CEILING = 1_00_00_000  # Rs 1 crore

# Cost escalation tolerated before a work needs re-sanction (CONFIGURABLE).
MAX_COST_ESCALATION_PCT = 10.0

# Mandated minimum shares of annual entitlement (CONFIGURABLE).
MIN_SHARE_SC_AREAS = 0.15
MIN_SHARE_ST_AREAS = 0.075

# Work categories that MPLADS guidelines do not admit. Kept as a list so new
# exclusions can be added without a code change.
INADMISSIBLE_CATEGORIES = [
    "Office building for government department",
    "Memorial or statue",
    "Place of worship",
    "Purchase of land",
    "Asset for commercial organisation",
    "Grant or loan to individual",
]

# Expected sanction-to-completion duration in days, by work category.
# Used by the delay detector as the baseline a work is measured against.
EXPECTED_DURATION_DAYS = {
    "CC road": 180,
    "Drainage": 150,
    "School building": 365,
    "Community hall": 300,
    "Solar street light": 90,
    "Drinking water": 120,
    "Toilet block": 120,
    "Anganwadi centre": 240,
    "Health sub-centre": 365,
    "Culvert / bridge": 300,
    "Playground": 180,
    "Library": 270,
}

SECTORS = {
    "CC road": "Transport",
    "Culvert / bridge": "Transport",
    "Drainage": "Sanitation",
    "Toilet block": "Sanitation",
    "Drinking water": "Water",
    "School building": "Education",
    "Library": "Education",
    "Anganwadi centre": "Education",
    "Health sub-centre": "Health",
    "Community hall": "Community",
    "Playground": "Community",
    "Solar street light": "Energy",
}


# --------------------------------------------------------------------------
# Detector weights
# --------------------------------------------------------------------------


@dataclass
class Weights:
    """
    Maximum number of points (as a fraction of 100) that each indicator can
    contribute on its own.

    These are caps, not shares, and they deliberately do not sum to 1. Under a
    plain weighted average an indicator can never contribute more than its
    weight, so a work that is flagrant on exactly one dimension -- an
    inadmissible category, or funds fully drawn against no progress -- scores
    low simply because the other five detectors are quiet. That is the opposite
    of what a reviewer needs.

    Indicators are combined as independent evidence instead (see
    `scoring.score`), so one saturated indicator alone reaches its cap here, and
    several together compound toward but never past 100.
    """

    cost_deviation: float = 0.55
    delay: float = 0.45
    expenditure_mismatch: float = 0.60
    duplicate: float = 0.65
    compliance: float = 0.75
    multivariate: float = 0.40

    def as_dict(self) -> dict:
        return {
            "cost_deviation": self.cost_deviation,
            "delay": self.delay,
            "expenditure_mismatch": self.expenditure_mismatch,
            "duplicate": self.duplicate,
            "compliance": self.compliance,
            "multivariate": self.multivariate,
        }

    def validate(self) -> None:
        for name, value in self.as_dict().items():
            if not 0.0 < value < 1.0:
                raise ValueError(
                    f"Indicator cap '{name}' must lie in (0, 1), got {value}"
                )


# --------------------------------------------------------------------------
# Detector thresholds
# --------------------------------------------------------------------------


@dataclass
class Thresholds:
    # Cost deviation: robust z-score against the peer group at which a work is
    # treated as fully anomalous on the cost dimension.
    cost_z_saturate: float = 4.0
    # Minimum peer group size before peer comparison is considered meaningful.
    min_peer_group: int = 8

    # Delay: overrun as a multiple of the category's expected duration.
    # Most public works run modestly late for ordinary reasons, so a tolerance
    # band absorbs routine slippage and only the excess beyond it is scored.
    # Without this, every work in the register carries a small delay signal and
    # the genuinely stalled ones stop standing out.
    delay_tolerance_ratio: float = 0.25
    delay_ratio_saturate: float = 1.25  # 125% overrun -> full delay signal

    # Expenditure-progress mismatch: percentage points by which the share of
    # money spent may exceed physical progress before it counts as a signal.
    mismatch_tolerance_pct: float = 15.0
    mismatch_saturate_pct: float = 50.0

    # Duplicate detection.
    duplicate_similarity_floor: float = 0.55  # below this, ignore entirely
    duplicate_radius_km: float = 12.0  # only compare works within this radius

    # Risk bands applied to the final 0-100 score.
    band_high: float = 70.0
    band_medium: float = 45.0

    # Confidence: fields that must be present for a score to be fully trusted.
    confidence_fields: list = field(
        default_factory=lambda: [
            "sanctioned_cost",
            "expenditure",
            "physical_progress_pct",
            "sanction_date",
            "work_description",
            "implementing_agency",
            "latitude",
        ]
    )


    # Multivariate: only the upper tail of the unsupervised score is treated as
    # a signal. Isolation Forest returns a value for every work, so without a
    # floor the model contributes constant background evidence to the whole
    # register and inflates otherwise unremarkable works.
    multivariate_percentile_floor: float = 0.85


@dataclass
class ModelParams:
    isolation_forest_estimators: int = 300
    isolation_forest_contamination: float = 0.08
    dbscan_eps: float = 1.10
    dbscan_min_samples: int = 8
    random_state: int = 42
    multivariate_percentile_floor: float = 0.85


WEIGHTS = Weights()
THRESHOLDS = Thresholds()
MODEL_PARAMS = ModelParams()

WEIGHTS.validate()

# Human-readable labels used in reviewer-facing explanations.
INDICATOR_LABELS = {
    "cost_deviation": "Cost deviation",
    "delay": "Delay",
    "expenditure_mismatch": "Expenditure-progress mismatch",
    "duplicate": "Duplicate / similar project",
    "compliance": "Compliance rule violation",
    "multivariate": "Unusual overall pattern",
}
