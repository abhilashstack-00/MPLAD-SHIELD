"""
Detectors for the V2 engine.

Every detector returns a signal in [0, 1] per work plus a status envelope. The
status matters as much as the number: a detector whose required field is absent
reports `skipped` and contributes no evidence at all. It never returns 0.0,
because a zero is indistinguishable from "checked and found nothing", and that
distinction is the difference between an honest system and a misleading one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import RULE_TIER_WEIGHT, RiskConfig


class DetectorResult:
    """Signal plus provenance for one detector across all works."""

    def __init__(
        self,
        name: str,
        signal: pd.Series | None,
        status: str,
        reason: str,
        evidence: pd.DataFrame | None = None,
        missing_fields: list[str] | None = None,
        evaluated: int = 0,
    ):
        self.name = name
        self.signal = signal
        self.status = status
        self.reason = reason
        self.evidence = evidence if evidence is not None else pd.DataFrame()
        self.missing_fields = missing_fields or []
        self.evaluated = evaluated

    def meta(self) -> dict:
        return {
            "detector": self.name,
            "status": self.status,
            "reason": self.reason,
            "records_evaluated": int(self.evaluated),
            "records_flagged": int((self.signal > 0).sum()) if self.signal is not None else 0,
            "missing_fields": self.missing_fields,
        }


def _skipped(name: str, missing: list[str], index) -> DetectorResult:
    return DetectorResult(
        name,
        pd.Series(np.nan, index=index),
        "skipped",
        "Not evaluated: required field(s) unavailable in the supplied data — "
        + ", ".join(missing),
        missing_fields=missing,
    )


def _saturate(values: pd.Series, floor: float, ceiling: float) -> pd.Series:
    """Map [floor, ceiling] onto [0, 1], with a deadband below the floor."""
    span = ceiling - floor
    if span <= 0:
        return pd.Series(0.0, index=values.index)
    return ((values - floor) / span).clip(lower=0.0, upper=1.0)


# ------------------------------------------------------------ cost


def cost_deviation(works: pd.DataFrame, config: RiskConfig) -> DetectorResult:
    """How far a sanctioned amount sits above comparable works."""
    if "cost_robust_z" not in works:
        return _skipped("cost_deviation", ["cost_robust_z"], works.index)

    usable = works["peer_key"].notna() & works["sanction_amount"].notna()
    signal = pd.Series(np.nan, index=works.index)
    signal.loc[usable] = _saturate(
        works.loc[usable, "cost_robust_z"].clip(lower=0),
        0.0,
        config.thresholds.cost_z_saturate,
    )

    return DetectorResult(
        "cost_deviation",
        signal,
        "active",
        "Sanctioned amount compared, in log space, against the median of its "
        "peer group using median absolute deviation.",
        evaluated=int(usable.sum()),
    )


# -------------------------------------------------------- timeline


def timeline(works: pd.DataFrame, config: RiskConfig) -> DetectorResult:
    """
    Duration against the peer group's own median, plus recommendation lag.

    No supplied file states an expected duration for any work category, so the
    baseline is empirical. This is a screening reference, not a deadline, and
    nothing here asserts that a work is late in any official sense.
    """
    if "days_sanction_to_reference" not in works:
        return _skipped("timeline", ["sanction_date"], works.index)

    t = config.thresholds
    usable = works["peer_median_duration"].notna() & works["days_sanction_to_reference"].notna()

    duration = pd.Series(0.0, index=works.index)
    duration.loc[usable] = _saturate(
        works.loc[usable, "duration_ratio"],
        t.duration_tolerance_ratio,
        t.duration_saturate_ratio,
    )

    # Thresholds taken from this dataset's own distribution, so "a long lag"
    # means long relative to how this register actually behaves.
    lag_days = works["days_recommendation_to_sanction"]
    lag_floor = float(lag_days.quantile(t.lag_tolerance_percentile))
    lag_ceiling = float(lag_days.quantile(t.lag_saturate_percentile))
    lag = _saturate(lag_days.fillna(0), lag_floor, max(lag_ceiling, lag_floor + 1))

    signal = pd.concat([duration, lag], axis=1).max(axis=1)
    signal.loc[~usable & works["days_recommendation_to_sanction"].isna()] = np.nan

    return DetectorResult(
        "timeline",
        signal,
        "active",
        "Duration measured against the peer group's median; recommendation-to-"
        "sanction lag measured against a configurable screening threshold.",
        evaluated=int(signal.notna().sum()),
    )


# ---------------------------------------------------- expenditure


def expenditure_consistency(works: pd.DataFrame, config: RiskConfig) -> DetectorResult:
    """
    Consistency between money recorded and work recorded.

    Note the direction. In the supplied data nothing is disbursed above its
    sanction, so overspend carries no signal at all. What does carry signal is
    a completed work whose disbursement falls short, a completed work with no
    payment record whatsoever, and unusual payment fragmentation.
    """
    if "total_expenditure" not in works:
        return _skipped("expenditure_consistency", ["total_expenditure"], works.index)

    t = config.thresholds
    signal = pd.Series(np.nan, index=works.index)

    has_money = works["has_expenditure"]
    completed = works["is_completed"]

    underspend = pd.Series(0.0, index=works.index)
    scope = has_money & completed
    underspend.loc[scope] = _saturate(
        1.0 - works.loc[scope, "expenditure_ratio"].clip(upper=1.0),
        1.0 - t.underspend_tolerance,
        1.0 - t.underspend_saturate,
    )

    # A completed work with no payment record at all is a stronger statement
    # than a small shortfall, but it is a records problem as much as a
    # financial one, so it is capped below the top of the scale.
    # Capped low on purpose. This is usually a gap in the expenditure export
    # rather than a statement about the work, and it affects 4,269 records.
    missing_payments = (completed & ~has_money).astype(float) * 0.35

    counts = works.loc[has_money, "payment_count"]
    frag_floor = float(counts.quantile(t.payment_count_percentile)) if len(counts) else 3.0
    fragmentation = _saturate(
        works["payment_count"].fillna(0), frag_floor, t.payment_count_saturate
    )

    pending = (works["payments_not_successful"].fillna(0) > 0).astype(float) * 0.25

    combined = pd.concat([underspend, missing_payments, fragmentation, pending], axis=1)
    evaluable = has_money | completed
    signal.loc[evaluable] = combined.loc[evaluable].max(axis=1)

    return DetectorResult(
        "expenditure_consistency",
        signal,
        "active",
        "Disbursement compared against the sanctioned amount for completed "
        "works, together with payment count and payment status.",
        evaluated=int(evaluable.sum()),
    )


# ------------------------------------------------------ similarity


def similarity(works: pd.DataFrame, config: RiskConfig) -> DetectorResult:
    """
    Works whose descriptions closely resemble another nearby work.

    Character n-grams rather than words: near-duplicate sanctions in this
    register differ by a transliteration or a typo, which word matching misses.

    Comparison is blocked by district so the cost stays linear-ish rather than
    quadratic across 20,000 records, and descriptions whose script was lost in
    export are excluded — left in, they would match each other on their
    question marks and manufacture findings.
    """
    if "description_normalised" not in works:
        return _skipped("similarity", ["work_description"], works.index)

    t = config.thresholds
    signal = pd.Series(np.nan, index=works.index)
    partner = pd.Series("", index=works.index, dtype=object)
    partner_score = pd.Series(np.nan, index=works.index)

    eligible = works["description_normalised"].notna() & ~works["description_is_mojibake"]
    signal.loc[eligible] = 0.0

    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True
    )

    for _, block in works.loc[eligible].groupby("district", dropna=True):
        if len(block) < 2 or len(block) > t.similarity_block_max:
            continue
        text = block["description_normalised"].astype(str)
        try:
            matrix = vectorizer.fit_transform(text)
        except ValueError:
            continue

        sim = cosine_similarity(matrix)
        np.fill_diagonal(sim, 0.0)

        best_idx = sim.argmax(axis=1)
        best = sim.max(axis=1)

        scaled = np.clip((best - t.similarity_floor) / (1.0 - t.similarity_floor), 0, 1)
        signal.loc[block.index] = scaled
        partner_score.loc[block.index] = best
        partner.loc[block.index] = np.where(
            best >= t.similarity_floor, block["work_id"].to_numpy()[best_idx], ""
        )

    evidence = pd.DataFrame(
        {"similar_work_id": partner, "similarity_score": partner_score.round(3)}
    )

    return DetectorResult(
        "similarity",
        signal,
        "active",
        "Descriptions compared within the same district using character n-gram "
        "TF-IDF. Matches indicate potential similarity requiring verification, "
        "not confirmed duplication.",
        evidence=evidence,
        evaluated=int(eligible.sum()),
    )


# --------------------------------------------------------- rules


def compliance(works: pd.DataFrame, config: RiskConfig) -> tuple[DetectorResult, list[dict]]:
    """
    The rule engine.

    A rule whose required fields are absent is reported as `not_evaluated`, not
    as passed. Two rules carried here can never fire on the supplied exports —
    inadmissible category and cost revision — and saying so plainly is more
    useful than quietly dropping them.
    """
    severity = pd.Series(0.0, index=works.index)
    reasons = pd.Series([[] for _ in range(len(works))], index=works.index, dtype=object)
    rule_report: list[dict] = []

    def fire(rule, mask: pd.Series) -> None:
        mask = mask.fillna(False)
        for idx in works.index[mask]:
            reasons.at[idx].append(f"[{rule.rule_id}] {rule.name}")
        weight = RULE_TIER_WEIGHT.get(rule.rule_type, 0.5)
        severity.loc[mask] += rule.severity * weight
        rule_report.append(
            {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "rule_type": rule.rule_type,
                "source": rule.source,
                "status": "evaluated",
                "records_flagged": int(mask.sum()),
                "tier_weight": weight,
                "explanation": rule.explanation,
            }
        )

    def skip(rule, missing: list[str]) -> None:
        rule_report.append(
            {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "rule_type": rule.rule_type,
                "source": rule.source,
                "status": "not_evaluated",
                "records_flagged": 0,
                "explanation": "Rule not evaluated because required data is "
                "unavailable: " + ", ".join(missing),
            }
        )

    t = config.thresholds
    for rule in config.rules:
        if not rule.enabled:
            continue
        missing = [f for f in rule.required_fields if f not in works.columns]
        if missing:
            skip(rule, missing)
            continue

        if rule.rule_id == "FIN_001":
            fire(rule, works["total_expenditure"] > works["sanction_amount"])
        elif rule.rule_id == "FIN_002":
            fire(rule, works["max_single_payment"] > works["sanction_amount"])
        elif rule.rule_id == "FIN_003":
            fire(rule, works["is_completed"] & ~works["has_expenditure"])
        elif rule.rule_id == "DATE_001":
            fire(rule, works["first_payment_date"] < works["sanction_date"])
        elif rule.rule_id == "DATE_002":
            fire(rule, works["completion_date"] < works["sanction_date"])
        elif rule.rule_id == "DATE_003":
            # Same calibrated basis as the timeline detector: "long" is
            # defined against this register's own 99th percentile, not a
            # guessed day count.
            lag_limit = works["days_recommendation_to_sanction"].quantile(
                t.lag_saturate_percentile
            )
            fire(rule, works["days_recommendation_to_sanction"] > lag_limit)
        elif rule.rule_id == "CEIL_001":
            fire(rule, works["sanction_amount"] > config.single_work_ceiling)
        elif rule.rule_id == "COST_002":
            fire(rule, works["sanction_uplift_pct"] > t.max_sanction_uplift_pct)
        elif rule.rule_id == "DUP_001":
            fire(rule, works["identical_description_count"] > 1)
        else:
            skip(rule, rule.required_fields)

    signal = (severity / 1.0).clip(upper=1.0)
    evidence = pd.DataFrame({"rule_reasons": reasons.apply(lambda r: "; ".join(r))})

    result = DetectorResult(
        "compliance",
        signal,
        "active",
        "Deterministic checks. Thresholds are administrative or analytical "
        "choices, not verified MPLADS guideline rules.",
        evidence=evidence,
        evaluated=int(len(works)),
    )
    return result, rule_report
