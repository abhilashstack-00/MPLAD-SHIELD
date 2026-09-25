"""
Combines the detectors into the 0-100 score and writes the explanation.

The combination is a plain weighted sum. That is a deliberate choice over a
learned combiner: with no fraud labels there is nothing honest to train a
combiner on, and a weighted sum can be decomposed exactly, so "82/100" can
always be broken back down into the points each detector contributed.

Nothing here concludes that a work is fraudulent. The output is a statement
about how unusual a work looks relative to its peers, which is a prompt for a
human to look, and the wording of every explanation is chosen to keep that
distinction intact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import INDICATOR_LABELS, THRESHOLDS, WEIGHTS

INDICATORS = list(WEIGHTS.as_dict())


def _reason_text(indicator: str, row: pd.Series) -> str:
    """Explain one indicator in the terms an officer would use."""
    if indicator == "cost_deviation":
        pct = row.get("peer_cost_percentile", float("nan"))
        median = row.get("peer_median_cost", float("nan"))
        if np.isfinite(median):
            return (
                f"Sanctioned at Rs {row['effective_cost']:,.0f} against a peer median of "
                f"Rs {median:,.0f} ({pct:.0f}th percentile for {row['work_category']} "
                f"in {row['state']})"
            )
        return "Cost is high relative to similar works"

    if indicator == "delay":
        return (
            f"{int(row['overrun_days'])} days beyond the "
            f"{int(row['expected_duration_days'])}-day norm for this category, "
            f"at {row['physical_progress_pct']:.0f}% physical progress"
            if np.isfinite(row.get("overrun_days", np.nan))
            else "Running behind the expected timeline"
        )

    if indicator == "expenditure_mismatch":
        return (
            f"{row['expenditure_ratio_pct']:.0f}% of funds drawn against "
            f"{row['physical_progress_pct']:.0f}% physical progress"
        )

    if indicator == "duplicate":
        partner = row.get("duplicate_match_id", "")
        if partner:
            return (
                f"Closely resembles {partner}, a {row['work_category']} sanctioned "
                f"nearby in {row['district']}"
            )
        return "Description closely resembles another nearby work"

    if indicator == "compliance":
        return row.get("compliance_reasons", "") or "Guideline check failed"

    if indicator == "multivariate":
        drivers = row.get("multivariate_drivers", "")
        if drivers:
            return f"Combination of indicators is unusual for this peer group ({drivers})"
        return "Combination of indicators is unusual for this peer group"

    return INDICATOR_LABELS.get(indicator, indicator)


def _band(score: float) -> str:
    if score >= THRESHOLDS.band_high:
        return "High"
    if score >= THRESHOLDS.band_medium:
        return "Medium"
    return "Low"


def score(df: pd.DataFrame, attributions: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Produce the final score and explanation for every work.

    `df` must already carry one column per indicator in `INDICATORS`, each in
    [0, 1]. `attributions` is the optional SHAP frame from the multivariate
    detector, used to name the features driving the unsupervised component.
    """
    out = df.copy()
    caps = WEIGHTS.as_dict()

    # Indicators are combined as independent evidence rather than averaged.
    #
    # Each indicator is read as "the chance this dimension alone would justify a
    # look", capped at `caps[i]`. Independent evidence combines as a noisy-OR:
    #
    #     risk = 1 - product over i of (1 - cap_i * x_i)
    #
    # so one saturated indicator reaches its own cap regardless of how quiet the
    # others are, and several moderate ones compound. Working in log space makes
    # that product a sum, which keeps the result exactly decomposable: each
    # detector's share of the total log-evidence is its share of the final
    # score, so "82/100" can still be broken back into points per indicator.
    evidence = pd.DataFrame(index=out.index)
    for indicator, cap in caps.items():
        # Clip below 1 so a saturated indicator stays finite in log space.
        x = out[indicator].fillna(0.0).clip(lower=0.0, upper=0.999)
        evidence[indicator] = -np.log1p(-cap * x)

    total_evidence = evidence.sum(axis=1)
    risk = (1 - np.exp(-total_evidence)) * 100

    safe_total = total_evidence.replace(0.0, np.nan)
    for indicator in INDICATORS:
        share = (evidence[indicator] / safe_total).fillna(0.0)
        out[f"points_{indicator}"] = (share * risk).round(2)

    out["risk_score"] = risk.round(1)
    out["risk_band"] = out["risk_score"].apply(_band)

    # Confidence reflects how much of the record was actually observed, and
    # whether the peer group was large enough for comparison to mean anything.
    peer_adequacy = (
        out["peer_size"] / THRESHOLDS.min_peer_group
    ).clip(upper=1.0).fillna(0.0)
    out["confidence"] = (
        0.7 * out["data_completeness"].fillna(0.0) + 0.3 * peer_adequacy
    ).round(3)

    # Name the features behind the multivariate component, where SHAP ran.
    if attributions is not None and len(attributions) == len(out):
        top_features = attributions.apply(
            lambda r: ", ".join(
                r.sort_values(ascending=False).head(2).index.str.replace("_", " ")
            ),
            axis=1,
        )
        out["multivariate_drivers"] = top_features.to_numpy()
    else:
        out["multivariate_drivers"] = ""

    # ------------------------------------------------------ explanations
    explanations, primaries = [], []
    for _, row in out.iterrows():
        contributions = sorted(
            ((i, row[f"points_{i}"]) for i in INDICATORS),
            key=lambda pair: pair[1],
            reverse=True,
        )
        material = [(i, pts) for i, pts in contributions if pts >= 3.0]
        if not material:
            explanations.append([])
            primaries.append("No material risk indicator")
            continue

        explanations.append(
            [
                {
                    "indicator": INDICATOR_LABELS[i],
                    "points": round(pts, 1),
                    "share_pct": round(100 * pts / max(row["risk_score"], 1e-9), 1),
                    "detail": _reason_text(i, row),
                }
                for i, pts in material[:3]
            ]
        )
        primaries.append(INDICATOR_LABELS[material[0][0]])

    out["explanation"] = explanations
    out["primary_reason"] = primaries
    out["review_status"] = np.where(
        out["risk_band"] == "High", "Pending review", "Not queued"
    )
    out["assessment"] = (
        "Unusual pattern identified for human review. This score does not "
        "establish irregularity or fraud."
    )

    return out


def priority_queue(scored: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """
    The ranked shortlist a reviewer actually works through.

    Ordering is by score, then by confidence: between two works scoring alike,
    the one whose record is more complete is the better use of an inspection
    visit.
    """
    columns = [
        "project_id",
        "district",
        "state",
        "work_category",
        "implementing_agency",
        "effective_cost",
        "risk_score",
        "risk_band",
        "confidence",
        "primary_reason",
        "review_status",
    ]
    available = [c for c in columns if c in scored.columns]
    return (
        scored.sort_values(["risk_score", "confidence"], ascending=[False, False])
        .head(top_n)[available]
        .reset_index(drop=True)
    )


def agency_rollup(scored: pd.DataFrame, min_works: int = 5) -> pd.DataFrame:
    """
    Cross-project view: Project -> Agency -> District.

    An individually unremarkable agency can still be carrying a caseload that is
    unusual in aggregate. This is the relationship analysis the deck describes,
    and it is the layer that per-project monitoring cannot produce.
    """
    grouped = (
        scored.groupby(["district", "implementing_agency"], dropna=False)
        .agg(
            works=("project_id", "size"),
            total_cost=("effective_cost", "sum"),
            mean_risk=("risk_score", "mean"),
            high_risk_works=("risk_band", lambda s: int((s == "High").sum())),
        )
        .reset_index()
    )
    grouped = grouped[grouped["works"] >= min_works].copy()
    grouped["high_risk_rate"] = (
        grouped["high_risk_works"] / grouped["works"]
    ).round(3)
    grouped["mean_risk"] = grouped["mean_risk"].round(1)
    return grouped.sort_values("mean_risk", ascending=False).reset_index(drop=True)
