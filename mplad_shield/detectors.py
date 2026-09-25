"""
Individual risk detectors.

Each detector returns a value in [0, 1] for every work, where 0 means "nothing
unusual on this dimension" and 1 means "as extreme as this indicator gets".
Keeping every detector on the same scale is what lets the final score be a
transparent weighted sum rather than an opaque model output -- the reviewer can
be shown precisely how many of the 100 points came from each source.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import INADMISSIBLE_CATEGORIES, MAX_COST_ESCALATION_PCT, SINGLE_WORK_CEILING, THRESHOLDS

EARTH_RADIUS_KM = 6371.0


def _saturate(values: pd.Series, ceiling: float) -> pd.Series:
    """Map [0, ceiling] onto [0, 1], clipping anything beyond."""
    return (values / ceiling).clip(lower=0.0, upper=1.0).fillna(0.0)


# --------------------------------------------------------------------------
# Cost, delay, expenditure
# --------------------------------------------------------------------------


def cost_deviation(df: pd.DataFrame) -> pd.Series:
    """
    How far the sanctioned cost sits above its peer group.

    Only the upper tail is scored. A work costing far less than its peers is a
    data-quality question or a genuine saving; it is not the pattern this system
    exists to surface, and scoring it would flood the queue.
    """
    return _saturate(df["cost_robust_z"].clip(lower=0), THRESHOLDS.cost_z_saturate)


def delay(df: pd.DataFrame) -> pd.Series:
    """
    Overrun as a fraction of the category's expected duration, beyond the
    tolerance band for routine slippage.
    """
    excess = df["delay_ratio"] - THRESHOLDS.delay_tolerance_ratio
    span = THRESHOLDS.delay_ratio_saturate - THRESHOLDS.delay_tolerance_ratio
    return _saturate(excess.clip(lower=0), span)


def expenditure_mismatch(df: pd.DataFrame) -> pd.Series:
    """
    Money drawn well ahead of work delivered.

    A tolerance band absorbs ordinary advance payments and mobilisation
    advances; only the excess beyond it is scored.
    """
    excess = df["progress_gap_pct"] - THRESHOLDS.mismatch_tolerance_pct
    span = THRESHOLDS.mismatch_saturate_pct - THRESHOLDS.mismatch_tolerance_pct
    return _saturate(excess.clip(lower=0), span)


# --------------------------------------------------------------------------
# Duplicate detection
# --------------------------------------------------------------------------


def _haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km between two arrays of coordinates."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def duplicate_similarity(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    Find works that look like re-sanctions of a neighbouring work.

    Descriptions are compared with TF-IDF over character n-grams rather than
    whole words. Duplicate sanctions in real registers differ by a
    transliteration or a typo -- "Instalation" against "Installation",
    "gaon" against "village" -- and word-level matching misses exactly those.
    Character n-grams degrade gracefully through spelling drift.

    Comparison is confined to works in the same district: two identical CC road
    descriptions in different states are unremarkable, and comparing every pair
    in the register would be both meaningless and quadratic in the wrong way.

    Returns the similarity score in [0, 1] and the project_id it matched.
    """
    scores = pd.Series(0.0, index=df.index)
    partners = pd.Series("", index=df.index, dtype=object)

    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True
    )

    for _, block in df.groupby("district"):
        if len(block) < 2:
            continue

        descriptions = block["work_description"].fillna("").astype(str)
        if descriptions.str.strip().eq("").all():
            continue

        try:
            matrix = vectorizer.fit_transform(descriptions)
        except ValueError:
            continue

        similarity = cosine_similarity(matrix)
        np.fill_diagonal(similarity, 0.0)

        # Works far apart on the ground are not duplicates of each other, even
        # if the text matches. Rows with no coordinates keep the text signal
        # rather than being silently exonerated.
        lat = block["latitude"].to_numpy(dtype=float)
        lon = block["longitude"].to_numpy(dtype=float)
        known = ~np.isnan(lat) & ~np.isnan(lon)
        if known.any():
            distance = _haversine_km(
                lat[:, None], lon[:, None], lat[None, :], lon[None, :]
            )
            too_far = distance > THRESHOLDS.duplicate_radius_km
            # Only suppress where both endpoints actually have coordinates.
            both_known = known[:, None] & known[None, :]
            similarity[too_far & both_known] = 0.0

        # Same category is required: a school and a road sharing a village name
        # are not duplicates.
        category = block["work_category"].to_numpy()
        similarity[category[:, None] != category[None, :]] = 0.0

        best = similarity.argmax(axis=1)
        best_score = similarity.max(axis=1)
        scores.loc[block.index] = best_score
        partners.loc[block.index] = np.where(
            best_score >= THRESHOLDS.duplicate_similarity_floor,
            block["project_id"].to_numpy()[best],
            "",
        )

    # Rescale so the floor maps to 0 and a perfect match maps to 1: a 0.56
    # similarity should contribute almost nothing, not half the duplicate weight.
    floor = THRESHOLDS.duplicate_similarity_floor
    scaled = ((scores - floor) / (1.0 - floor)).clip(lower=0.0, upper=1.0)
    return scaled.fillna(0.0), partners


# --------------------------------------------------------------------------
# Rule engine
# --------------------------------------------------------------------------


def compliance(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    Deterministic guideline checks.

    These are not statistical findings. A work in an inadmissible category is a
    breach whether or not it resembles its peers, so it is asserted directly
    rather than inferred -- which also means the reviewer gets a citable reason
    instead of a probability.

    Returns the score in [0, 1] and a semicolon-joined list of violated rules.
    """
    violations = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    severity = pd.Series(0.0, index=df.index)

    def flag(mask: pd.Series, message: str, weight: float) -> None:
        mask = mask.fillna(False)
        for idx in df.index[mask]:
            violations.at[idx].append(message)
        severity.loc[mask] += weight

    flag(
        df["work_category"].isin(INADMISSIBLE_CATEGORIES),
        "Work category is inadmissible under MPLADS guidelines",
        1.0,
    )
    flag(
        df["effective_cost"] > SINGLE_WORK_CEILING,
        f"Sanctioned cost exceeds the single-work ceiling of Rs {SINGLE_WORK_CEILING:,}",
        0.8,
    )
    flag(
        df["cost_escalation_pct"] > MAX_COST_ESCALATION_PCT,
        f"Cost revised upward by more than {MAX_COST_ESCALATION_PCT:.0f}% without re-sanction",
        0.5,
    )
    flag(
        df["expenditure_ratio_pct"] > 100.5,
        "Expenditure booked exceeds the sanctioned amount",
        0.7,
    )
    flag(
        (df["physical_progress_pct"] >= 99.5) & (df["status"] != "Completed"),
        "Reported as fully progressed but not closed as completed",
        0.3,
    )
    flag(
        df["agency_work_share"] > 0.45,
        "Implementing agency holds an unusually large share of the district's works",
        0.3,
    )

    # A single definitive breach saturates the indicator. Dividing by a larger
    # constant here would mean a work in an inadmissible category scored only a
    # fraction of the compliance signal unless it also failed other checks,
    # which inverts the point: this is a rule violation, not weak evidence.
    score = severity.clip(upper=1.0)
    reasons = violations.apply(lambda items: "; ".join(items))
    return score, reasons
