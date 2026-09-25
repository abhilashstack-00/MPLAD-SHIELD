"""
Turns a raw project register into the comparable quantities the detectors need.

The central idea is the peer group. A Rs 40 lakh community hall is unremarkable;
a Rs 40 lakh toilet block is not. Nothing here judges a work against a global
average -- everything is measured against works of the same category in the same
state, which is what makes the eventual explanation defensible to the officer
whose project got flagged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import EXPECTED_DURATION_DAYS, THRESHOLDS

# Robust z-scores use the median absolute deviation. 1.4826 rescales MAD so that
# it estimates the standard deviation for normally distributed data, which keeps
# the resulting z-score interpretable on the usual scale.
MAD_TO_SIGMA = 1.4826


def _robust_z(values: pd.Series) -> pd.Series:
    """
    Deviation from the group median in MAD units.

    Mean and standard deviation are avoided deliberately: a single inflated
    sanction drags both, which is exactly the case the detector must catch.
    Median and MAD barely move, so the outlier stays visible.
    """
    median = values.median()
    mad = (values - median).abs().median()
    if not np.isfinite(mad) or mad == 0:
        # Degenerate group (identical costs, or too few distinct values).
        std = values.std()
        if not np.isfinite(std) or std == 0:
            return pd.Series(0.0, index=values.index)
        return (values - median) / std
    return (values - median) / (mad * MAD_TO_SIGMA)


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Attach engineered columns. Returns a copy; the input is not mutated."""
    out = df.copy()

    for col in ("sanction_date", "expected_completion_date", "actual_completion_date"):
        out[col] = pd.to_datetime(out[col], errors="coerce")

    out["effective_cost"] = out["revised_cost"].fillna(out["sanctioned_cost"])

    # ---------------------------------------------------------------- peers
    out["peer_group"] = out["work_category"].astype(str) + " | " + out["state"].astype(str)
    grp = out.groupby("peer_group")["effective_cost"]
    out["peer_size"] = grp.transform("size")
    out["peer_median_cost"] = grp.transform("median")
    out["cost_robust_z"] = grp.transform(_robust_z).fillna(0.0)

    # Percentile position within the peer group, for reviewer-facing context.
    out["peer_cost_percentile"] = (
        grp.rank(pct=True).fillna(0.5) * 100
    ).round(1)

    # Where the peer group is too small to say anything, damp the signal rather
    # than dropping it -- a thin group is weak evidence, not no evidence.
    thin = out["peer_size"] < THRESHOLDS.min_peer_group
    out.loc[thin, "cost_robust_z"] = out.loc[thin, "cost_robust_z"] * 0.4

    # ---------------------------------------------------------------- delay
    expected_days = out["work_category"].map(EXPECTED_DURATION_DAYS)
    # Unknown categories (including inadmissible ones) get the register median.
    expected_days = expected_days.fillna(np.median(list(EXPECTED_DURATION_DAYS.values())))
    out["expected_duration_days"] = expected_days

    reference = out["actual_completion_date"].fillna(pd.Timestamp("2026-09-01"))
    out["elapsed_days"] = (reference - out["sanction_date"]).dt.days
    out["overrun_days"] = (out["elapsed_days"] - expected_days).clip(lower=0)
    out["delay_ratio"] = (out["overrun_days"] / expected_days).fillna(0.0)

    # ------------------------------------------- expenditure vs progress
    out["expenditure_ratio_pct"] = (
        out["expenditure"] / out["effective_cost"].replace(0, np.nan) * 100
    )
    out["progress_gap_pct"] = (
        out["expenditure_ratio_pct"] - out["physical_progress_pct"]
    )

    # ---------------------------------------------------- cost escalation
    out["cost_escalation_pct"] = (
        (out["revised_cost"] - out["sanctioned_cost"])
        / out["sanctioned_cost"].replace(0, np.nan)
        * 100
    ).fillna(0.0)

    # ----------------------------------------------- agency concentration
    # Share of a district's works, and of its money, going to one agency.
    # A high share is not wrong by itself, but it is worth a reviewer knowing.
    pair = out.groupby(["district", "implementing_agency"], dropna=False)
    district = out.groupby("district")
    out["agency_work_share"] = (
        pair["project_id"].transform("size") / district["project_id"].transform("size")
    )
    out["agency_value_share"] = (
        pair["effective_cost"].transform("sum")
        / district["effective_cost"].transform("sum")
    )

    # ------------------------------------------------------- completeness
    present = pd.DataFrame(
        {c: out[c].notna() for c in THRESHOLDS.confidence_fields if c in out.columns}
    )
    out["data_completeness"] = present.mean(axis=1)

    return out


def numeric_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """
    Assemble the feature matrix handed to Isolation Forest and DBSCAN.

    Only scale-free, cross-category comparable quantities go in. Raw rupee
    amounts are excluded on purpose: an unsupervised model fed raw cost would
    simply learn that health sub-centres cost more than toilet blocks and flag
    every hospital in the register.
    """
    columns = [
        "cost_robust_z",
        "delay_ratio",
        "progress_gap_pct",
        "cost_escalation_pct",
        "physical_progress_pct",
        "expenditure_ratio_pct",
        "agency_work_share",
        "agency_value_share",
    ]
    matrix = df[columns].copy()
    # Median imputation keeps missing rows scoreable; the confidence score is
    # what tells the reviewer how much of the row was actually observed.
    matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
    return matrix.to_numpy(dtype=float), columns
