"""
Feature preparation for the V2 engine.

The central problem this module solves is finding a fair comparison group. The
scheme's own `Work category` field is useless for that purpose on real data —
97.3% of the supplied works are "Normal/Others", so comparing within it puts a
road, a classroom and a set of street lights in the same bucket.

The expenditure export turned out to carry a far better field: its `Work` column
holds about 96 work types. It only covers the half of works that have payment
records, so peer assignment cascades from strongest to weakest and records which
level each work actually landed on.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RiskConfig

MAD_TO_SIGMA = 1.4826

# Strongest first. Each entry is (name, columns) and a work takes the first
# level whose group is large enough to support a comparison.
PEER_LEVELS = [
    ("work_type + state", ["work_type", "state"]),
    ("work_type", ["work_type"]),
    ("category + state", ["work_category", "state"]),
    ("state", ["state"]),
]


def _robust_z(values: pd.Series) -> pd.Series:
    """
    Deviation from the group median in MAD units.

    Median and MAD are used rather than mean and standard deviation because a
    single inflated sanction would otherwise inflate the very yardstick it is
    being measured against.
    """
    median = values.median()
    mad = (values - median).abs().median()
    if not np.isfinite(mad) or mad == 0:
        std = values.std()
        if not np.isfinite(std) or std == 0:
            return pd.Series(0.0, index=values.index)
        return (values - median) / std
    return (values - median) / (mad * MAD_TO_SIGMA)


def assign_peer_groups(works: pd.DataFrame, config: RiskConfig) -> pd.DataFrame:
    """
    Attach a peer group to every work, recording which level was used.

    Every work ends up with `peer_key`, `peer_level`, `peer_size`. A work whose
    only available group is too small is not silently compared anyway — its
    `peer_level` reads "insufficient" and the cost detector skips it.
    """
    out = works.copy()
    minimum = config.thresholds.min_peer_group

    # Object dtype from the start: initialising with NaN would make this a
    # float column that cannot then accept string keys.
    out["peer_key"] = pd.Series([None] * len(out), index=out.index, dtype=object)
    out["peer_level"] = pd.Series(["insufficient"] * len(out), index=out.index, dtype=object)

    for level_name, columns in PEER_LEVELS:
        unassigned = out["peer_key"].isna()
        if not unassigned.any():
            break

        usable = unassigned & out[columns].notna().all(axis=1)
        if not usable.any():
            continue

        candidate = out.loc[usable, columns].astype(str).agg(" | ".join, axis=1)
        sizes = candidate.map(candidate.value_counts())
        big_enough = sizes >= minimum

        accept = candidate.index[big_enough]
        out.loc[accept, "peer_key"] = level_name + " :: " + candidate.loc[accept]
        out.loc[accept, "peer_level"] = level_name

    grouped = out.groupby("peer_key", dropna=True)["work_id"]
    out["peer_size"] = grouped.transform("size").fillna(0).astype(int)
    return out


def build(works: pd.DataFrame, config: RiskConfig) -> pd.DataFrame:
    """Attach every comparison quantity the detectors need."""
    out = assign_peer_groups(works, config)

    has_peer = out["peer_key"].notna()

    # --- cost against peers -------------------------------------------------
    # Compared in log space: sanction amounts span Rs 10,000 to Rs 7.35 crore
    # and are strongly right-skewed, so a linear deviation would flag every
    # large work type rather than every unusual work.
    amount = out["sanction_amount"].where(out["sanction_amount"] > 0)
    out["log_amount"] = np.log10(amount)

    out["peer_median_cost"] = np.nan
    out["cost_robust_z"] = 0.0
    out["peer_cost_percentile"] = np.nan

    if has_peer.any():
        by_peer = out.loc[has_peer].groupby("peer_key")
        out.loc[has_peer, "peer_median_cost"] = by_peer["sanction_amount"].transform("median")
        out.loc[has_peer, "cost_robust_z"] = (
            by_peer["log_amount"].transform(_robust_z).fillna(0.0)
        )
        out.loc[has_peer, "peer_cost_percentile"] = (
            by_peer["sanction_amount"].rank(pct=True) * 100
        ).round(1)

    # --- timeline -----------------------------------------------------------
    # No supplied file states an expected duration for any category, so the
    # baseline is the peer group's own median. It is a screening reference, not
    # an official deadline, and is labelled as such everywhere it appears.
    out["peer_median_duration"] = np.nan
    if has_peer.any():
        completed = out["is_completed"]
        medians = (
            out.loc[has_peer & completed]
            .groupby("peer_key")["days_sanction_to_reference"]
            .median()
        )
        out.loc[has_peer, "peer_median_duration"] = out.loc[has_peer, "peer_key"].map(medians)

    out["duration_ratio"] = (
        out["days_sanction_to_reference"] / out["peer_median_duration"].replace(0, np.nan)
    )

    # --- expenditure --------------------------------------------------------
    # Nothing in the supplied data disburses above sanction, so the meaningful
    # direction is shortfall on a work already recorded as complete.
    out["underspend_gap"] = np.where(
        out["is_completed"] & out["has_expenditure"],
        1.0 - out["expenditure_ratio"].clip(upper=1.0),
        np.nan,
    )
    out["payments_not_successful"] = out["payments_not_successful"].fillna(0)

    # --- concentration ------------------------------------------------------
    district = out.groupby("district", dropna=False)["work_id"]
    out["district_work_count"] = district.transform("size")
    vendor_pair = out.groupby(["district", "primary_vendor"], dropna=False)["work_id"]
    out["vendor_district_share"] = (
        vendor_pair.transform("size") / out["district_work_count"]
    ).where(out["primary_vendor"].notna())

    # --- exact description repeats -----------------------------------------
    desc_pair = out.groupby(["district", "description_normalised"], dropna=False)["work_id"]
    out["identical_description_count"] = desc_pair.transform("size").where(
        out["description_normalised"].notna() & ~out["description_is_mojibake"]
    )

    return out


def model_matrix(works: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """
    Feature matrix for the unsupervised layer.

    Only scale-free quantities are included. Feeding raw rupee amounts to an
    unsupervised model teaches it that health centres cost more than street
    lights, and it then flags every health centre.
    """
    columns = [
        "cost_robust_z",
        "duration_ratio",
        "expenditure_ratio",
        "payment_count",
        "distinct_vendors",
        "vendor_district_share",
        "days_recommendation_to_sanction",
        "sanction_uplift_pct",
        "data_completeness",
    ]
    available = [c for c in columns if c in works.columns]
    matrix = works[available].copy()
    matrix = matrix.replace([np.inf, -np.inf], np.nan)
    matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
    return matrix.to_numpy(dtype=float), available
