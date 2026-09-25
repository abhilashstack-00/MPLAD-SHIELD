"""
Measures the engine against ground truth.

This module only works on data where the answer is known -- the synthetic
register, or a historical set where audit outcomes have been recorded. On a live
register there is no label to score against, which is precisely why the
benchmark matters: it is the only place the engine's claims can be checked.

Precision@k is the headline number rather than accuracy. A reviewer works
through a queue of fixed length, so the question that matters is "of the fifty
works we will actually inspect, how many were worth inspecting" -- not how the
model scored the thousand works nobody will open.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def evaluate(scored: pd.DataFrame, k_values=(25, 50, 100)) -> dict:
    """Compare `risk_score` against the `is_anomaly` ground truth."""
    if "is_anomaly" not in scored.columns:
        return {"available": False, "reason": "No ground-truth labels in this dataset"}

    truth = scored["is_anomaly"].astype(bool).to_numpy()
    scores = scored["risk_score"].to_numpy(dtype=float)
    n_positive = int(truth.sum())

    if n_positive == 0 or n_positive == len(truth):
        return {"available": False, "reason": "Labels are single-class"}

    ranked = scored.sort_values("risk_score", ascending=False)
    ranked_truth = ranked["is_anomaly"].astype(bool).to_numpy()

    at_k = {}
    for k in k_values:
        k = min(k, len(ranked_truth))
        caught = int(ranked_truth[:k].sum())
        at_k[f"top_{k}"] = {
            "precision": round(caught / k, 3),
            "recall": round(caught / n_positive, 3),
            "caught": caught,
            "of_total_irregularities": n_positive,
        }

    # Recall by irregularity type shows which detector is carrying its weight
    # and, more usefully, which one is not.
    by_type = {}
    if "anomaly_type" in scored.columns:
        top_k = min(max(k_values), len(ranked))
        flagged_ids = set(ranked.head(top_k)["project_id"])
        for kind, block in scored[scored["is_anomaly"]].groupby("anomaly_type"):
            if not kind:
                continue
            caught = block["project_id"].isin(flagged_ids).sum()
            by_type[kind] = {
                "total": int(len(block)),
                "caught_in_top_k": int(caught),
                "recall": round(float(caught / len(block)), 3),
                "mean_risk_score": round(float(block["risk_score"].mean()), 1),
            }

    baseline = n_positive / len(truth)
    return {
        "available": True,
        "n_projects": int(len(truth)),
        "n_irregularities": n_positive,
        "base_rate": round(baseline, 4),
        "roc_auc": round(float(roc_auc_score(truth, scores)), 3),
        "average_precision": round(float(average_precision_score(truth, scores)), 3),
        "at_k": at_k,
        "by_anomaly_type": by_type,
        "lift_at_50": round(
            at_k.get("top_50", {}).get("precision", 0) / baseline, 2
        )
        if baseline > 0
        else None,
    }


def band_summary(scored: pd.DataFrame) -> pd.DataFrame:
    """How the register distributes across the risk bands."""
    summary = (
        scored.groupby("risk_band")
        .agg(
            projects=("project_id", "size"),
            mean_score=("risk_score", "mean"),
            mean_confidence=("confidence", "mean"),
        )
        .reindex(["High", "Medium", "Low"])
        .dropna(how="all")
        .reset_index()
    )
    summary["mean_score"] = summary["mean_score"].round(1)
    summary["mean_confidence"] = summary["mean_confidence"].round(3)
    summary["share_pct"] = (
        summary["projects"] / summary["projects"].sum() * 100
    ).round(1)
    return summary


def reason_summary(scored: pd.DataFrame) -> pd.DataFrame:
    """
    Counts of the primary reason works were flagged -- the "Why Projects Are
    Flagged" panel in the dashboard.
    """
    counts = (
        scored[scored["risk_band"].isin(["High", "Medium"])]["primary_reason"]
        .value_counts()
        .reset_index()
    )
    counts.columns = ["reason", "projects"]
    return counts
