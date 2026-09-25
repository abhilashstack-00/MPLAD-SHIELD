"""
Combination, confidence, and export for the V2 engine.

The combiner is carried over from V1 unchanged, because it was the part that
worked: indicators combine as independent evidence rather than a weighted
average, computed in log space so the result decomposes exactly back into
per-indicator points. What changed is everything feeding it.

One addition matters. A detector that could not run contributes no evidence at
all — it is not treated as a quiet zero. A work nobody could check on four of
six dimensions should not look reassuring; it should look uncertain, and that
shows up in confidence rather than in the score.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from . import aggregates as agg
from . import detectors as det
from . import features as ft
from .config import INDICATOR_LABELS, INDICATORS, PEER_LEVEL_STRENGTH, RiskConfig


# ------------------------------------------------------- multivariate


def multivariate(works: pd.DataFrame, config: RiskConfig) -> det.DetectorResult:
    """Isolation Forest plus DBSCAN over the scale-free feature matrix."""
    matrix, names = ft.model_matrix(works)
    params = config.model

    if len(works) < params.min_rows_to_fit:
        return det._skipped(
            "multivariate",
            [f"at least {params.min_rows_to_fit} records to fit"],
            works.index,
        )

    scaled = RobustScaler().fit_transform(matrix)

    forest = IsolationForest(
        n_estimators=params.isolation_forest_estimators,
        contamination=params.contamination,
        random_state=params.random_state,
        n_jobs=-1,
    ).fit(scaled)

    raw = -forest.decision_function(scaled)
    spread = raw.max() - raw.min()
    forest_score = (raw - raw.min()) / spread if spread > 0 else np.zeros_like(raw)

    labels = DBSCAN(
        eps=params.dbscan_eps, min_samples=params.dbscan_min_samples, n_jobs=-1
    ).fit_predict(scaled)
    blended = np.clip(forest_score + 0.25 * (labels == -1), 0, 1)

    # Only the upper tail is treated as signal. Isolation Forest scores every
    # record, so passing the raw value through would give all 20,187 works a
    # standing contribution to their own risk score.
    ranks = pd.Series(blended, index=works.index).rank(pct=True)
    floor = params.multivariate_percentile_floor
    signal = ((ranks - floor) / (1 - floor)).clip(0, 1)

    result = det.DetectorResult(
        "multivariate",
        signal,
        "active",
        f"Isolation Forest and DBSCAN over {len(names)} scale-free features; "
        "only the top 15% by rank is treated as a signal.",
        evaluated=len(works),
    )
    result.feature_names = names
    result.dbscan_noise = int((labels == -1).sum())
    return result


# ------------------------------------------------------------ scoring


def _band(score: float, config: RiskConfig) -> str:
    if score >= config.thresholds.band_high:
        return "High"
    if score >= config.thresholds.band_medium:
        return "Medium"
    return "Low"


def combine(works: pd.DataFrame, results: dict, config: RiskConfig) -> pd.DataFrame:
    """Combine detector signals into a 0-100 indicator with exact decomposition."""
    out = works.copy()
    caps = config.caps

    evidence = pd.DataFrame(index=out.index)
    for name in INDICATORS:
        result = results.get(name)
        if result is None or result.signal is None:
            out[f"points_{name}"] = 0.0
            evidence[name] = 0.0
            continue
        # NaN means "not evaluated for this record": no evidence either way.
        x = result.signal.fillna(0.0).clip(0.0, 0.999)
        evidence[name] = -np.log1p(-caps[name] * x)

    total = evidence.sum(axis=1)
    risk = (1 - np.exp(-total)) * 100

    # Points are rounded first and the score is then defined as their sum, so
    # the decomposition is exact by construction rather than exact to within a
    # rounding tolerance. The interface asserts this on load.
    safe = total.replace(0.0, np.nan)
    point_columns = []
    for name in INDICATORS:
        column = f"points_{name}"
        out[column] = ((evidence[name] / safe).fillna(0.0) * risk).round(2)
        point_columns.append(column)

    out["risk_score"] = out[point_columns].sum(axis=1).round(2)
    out["risk_band"] = out["risk_score"].apply(lambda s: _band(s, config))

    # Confidence is about the record, not the risk: how much was observable,
    # how solid the peer group was, and how many detectors could actually run.
    evaluated = pd.DataFrame(
        {n: (results[n].signal.notna() if n in results and results[n].signal is not None
             else pd.Series(False, index=out.index)) for n in INDICATORS}
    )
    out["detectors_evaluated"] = evaluated.sum(axis=1)
    detector_cover = out["detectors_evaluated"] / len(INDICATORS)

    # Peer strength dominates, because it is what actually varies across this
    # register and what most affects whether a cost finding means anything.
    level_strength = out["peer_level"].map(PEER_LEVEL_STRENGTH).fillna(0.0)
    size_adequacy = (
        out["peer_size"] / (config.thresholds.min_peer_group * 4)
    ).clip(upper=1.0).fillna(0.0)
    out["peer_strength"] = (0.7 * level_strength + 0.3 * size_adequacy).round(3)

    out["confidence"] = (
        0.30 * out["data_completeness"].fillna(0)
        + 0.15 * detector_cover
        + 0.55 * out["peer_strength"]
    ).round(3)
    out["confidence_band"] = pd.cut(
        out["confidence"], [-0.01, 0.55, 0.78, 1.01], labels=["Low", "Medium", "High"]
    ).astype(str)

    # Stated plainly so the interface can show why, rather than a bare number.
    out["confidence_reason"] = np.where(
        level_strength >= 0.85,
        "Compared against works of the same type",
        np.where(
            level_strength >= 0.45,
            "Only a broad category peer group was available",
            "No adequate peer group — cost comparison not attempted",
        ),
    )

    return out


def _reason(name: str, row: pd.Series) -> str:
    """One indicator explained in the terms a reviewer would use."""
    if name == "cost_deviation":
        median = row.get("peer_median_cost")
        if pd.notna(median):
            return (
                f"Sanctioned at Rs {row['sanction_amount']:,.0f} against a peer median of "
                f"Rs {median:,.0f} ({row.get('peer_cost_percentile', float('nan')):.0f}th "
                f"percentile among {int(row.get('peer_size', 0))} comparable works, "
                f"grouped by {row.get('peer_level', 'n/a')})"
            )
        return "Cost is high relative to comparable works"

    if name == "timeline":
        days = row.get("days_sanction_to_reference")
        median = row.get("peer_median_duration")
        if pd.notna(days) and pd.notna(median) and median > 0:
            return (
                f"{int(days)} days since sanction against a peer median of "
                f"{int(median)} days ({row.get('age_basis', 'reference')})"
            )
        lag = row.get("days_recommendation_to_sanction")
        return f"{int(lag)} days between recommendation and sanction" if pd.notna(lag) else "Timeline indicator"

    if name == "expenditure_consistency":
        if row.get("is_completed") and not row.get("has_expenditure"):
            return "Recorded as completed but carries no payment record"
        ratio = row.get("expenditure_ratio")
        if pd.notna(ratio):
            return (
                f"{ratio * 100:.0f}% of the sanctioned amount disbursed across "
                f"{int(row.get('payment_count', 0))} payment(s)"
            )
        return "Expenditure consistency indicator"

    if name == "similarity":
        partner = row.get("similar_work_id", "")
        if partner:
            return (
                f"Description closely resembles {partner} in the same district "
                f"(similarity {row.get('similarity_score', float('nan')):.2f}) — "
                "requires verification, not a confirmed duplicate"
            )
        return "Description resembles another nearby work"

    if name == "compliance":
        return row.get("rule_reasons", "") or "Rule-based indicator"

    if name == "multivariate":
        return "Combination of indicators is unusual for this peer group"

    return INDICATOR_LABELS.get(name, name)


def explain(works: pd.DataFrame) -> pd.DataFrame:
    """Attach the top contributing indicators, with figures, to every work."""
    out = works.copy()
    explanations, primary = [], []

    for _, row in out.iterrows():
        contributions = sorted(
            ((n, row[f"points_{n}"]) for n in INDICATORS), key=lambda p: p[1], reverse=True
        )
        material = [(n, p) for n, p in contributions if p >= 3.0]
        if not material:
            explanations.append([])
            primary.append("No material indicator")
            continue
        explanations.append(
            [
                {
                    "indicator": INDICATOR_LABELS[n],
                    "points": round(p, 1),
                    "share_pct": round(100 * p / max(row["risk_score"], 1e-9), 1),
                    "detail": _reason(n, row),
                }
                for n, p in material[:3]
            ]
        )
        primary.append(INDICATOR_LABELS[material[0][0]])

    out["explanation"] = explanations
    out["primary_reason"] = primary
    out["assessment"] = (
        "This work exhibits unusual patterns under the configured indicators "
        "and may warrant further review. The system does not establish fraud "
        "or wrongdoing."
    )
    return out


# ----------------------------------------------------------- pipeline


def run(works: pd.DataFrame, config: RiskConfig | None = None) -> dict:
    """Score a unified work-level dataset."""
    config = config or RiskConfig()
    prepared = ft.build(works, config)

    results: dict = {}
    results["cost_deviation"] = det.cost_deviation(prepared, config)
    results["timeline"] = det.timeline(prepared, config)
    results["expenditure_consistency"] = det.expenditure_consistency(prepared, config)
    results["similarity"] = det.similarity(prepared, config)
    compliance_result, rule_report = det.compliance(prepared, config)
    results["compliance"] = compliance_result
    results["multivariate"] = multivariate(prepared, config)

    for result in results.values():
        if not result.evidence.empty:
            for column in result.evidence.columns:
                prepared[column] = result.evidence[column]

    scored = combine(prepared, results, config)
    scored = explain(scored)

    return {
        "scored": scored,
        "detectors": [r.meta() for r in results.values()],
        "rules": rule_report,
        "config": {
            "engine_version": config.engine_version,
            "config_version": config.config_version,
            "caps": config.caps,
            "bands": {
                "high": config.thresholds.band_high,
                "medium": config.thresholds.band_medium,
            },
            "single_work_ceiling": config.single_work_ceiling,
            "min_peer_group": config.thresholds.min_peer_group,
        },
    }


EXPORT_FIELDS = [
    "work_id", "work_description", "work_category", "work_type", "state", "district",
    "ida_raw", "mp_name", "sanction_amount", "recommended_date", "sanction_date",
    "completion_date", "work_status", "is_completed", "total_expenditure",
    "expenditure_ratio", "payment_count", "max_single_payment", "distinct_vendors",
    "primary_vendor", "first_payment_date", "last_payment_date",
    "peer_key", "peer_level", "peer_size", "peer_median_cost", "peer_cost_percentile",
    "cost_robust_z", "days_recommendation_to_sanction", "days_sanction_to_reference",
    "peer_median_duration", "age_basis", "similar_work_id", "similarity_score",
    "rule_reasons", "identical_description_count", "vendor_district_share",
    "data_completeness", "detectors_evaluated", "peer_strength", "confidence_reason",
    "risk_score", "risk_band", "confidence", "confidence_band",
    "primary_reason", "assessment", "briefing", "source_file", "source_row",
] + [f"points_{n}" for n in INDICATORS]


def _clean(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else round(float(value), 4)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.strftime("%Y-%m-%d")
    if value is pd.NaT or (isinstance(value, float) and not np.isfinite(value)):
        return None
    if pd.isna(value) if np.isscalar(value) else False:
        return None
    return value


def export(
    result: dict,
    ingest_report: dict,
    outdir: str | Path,
    top_n: int = 100,
    detail_scope: str = "all",
    allocation: pd.DataFrame | None = None,
    recommendation_pipeline: pd.DataFrame | None = None,
    as_of: str | None = None,
) -> dict:
    """Write the payload the dashboard reads."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    scored = result["scored"]

    # ---- audience-level views, trends and early warning ------------------
    reference = pd.Timestamp(as_of or ingest_report["config"]["as_of_date"])
    scored["briefing"] = agg.add_briefings(scored)

    roll = agg.rollups(scored)
    trend = agg.trends(scored)
    utilisation = agg.allocation_utilisation(scored, allocation)
    warnings = agg.early_warning(scored, reference)
    pipeline_summary = agg.recommendation_pipeline(recommendation_pipeline)

    def records(frame: pd.DataFrame, limit: int | None = None) -> list:
        if frame is None or frame.empty:
            return []
        subset = frame if limit is None else frame.head(limit)
        return json.loads(subset.to_json(orient="records", date_format="iso"))

    available = [c for c in EXPORT_FIELDS if c in scored.columns]

    # The payload is split. Serialising all 20,187 works with every field ran
    # to 41 MB, which makes the dashboard unusable on a conference network.
    #
    # `scored.json` carries a light index covering every work -- enough for the
    # register list, search and the queue -- plus all the report blocks.
    # `work_details.json` carries the full record and is fetched only when a
    # reviewer opens a work. By default it covers the flagged works, which are
    # the ones anybody actually opens; pass detail_scope="all" to include the
    # whole register at the cost of size.
    index_fields = [
        "work_id", "work_description", "state", "district", "work_category",
        "work_type", "sanction_amount", "work_status", "risk_score", "risk_band",
        "confidence", "confidence_band", "primary_reason",
    ]
    index_fields = [c for c in index_fields if c in scored.columns]

    def record_for(row, fields, with_explanation):
        out_record = {}
        for field in fields:
            value = _clean(row[field])
            if value is not None and value != "":
                out_record[field] = value
        if with_explanation:
            out_record["explanation"] = row["explanation"]
        return out_record

    works = []
    for _, row in scored.iterrows():
        entry = record_for(row, index_fields, False)
        # The index only needs enough description to search and recognise a
        # work; the full text lives in the detail payload.
        description = entry.get("work_description")
        if isinstance(description, str) and len(description) > 90:
            entry["work_description"] = description[:90] + "\u2026"
        works.append(entry)

    detail_rows = scored if detail_scope == "all" else scored[scored["risk_band"] != "Low"]
    details = {
        row["work_id"]: record_for(row, available, True)
        for _, row in detail_rows.iterrows()
    }

    queue_cols = [
        "work_id", "work_description", "state", "district", "work_category",
        "sanction_amount", "work_status", "risk_score", "risk_band", "confidence",
        "confidence_band", "primary_reason",
    ]
    ranked = scored.sort_values(["risk_score", "confidence"], ascending=[False, False])
    if top_n > 0:
        ranked = ranked.head(top_n)
    queue = ranked[[c for c in queue_cols if c in scored.columns]]

    bands = (
        scored.groupby("risk_band")
        .agg(works=("work_id", "size"), mean_score=("risk_score", "mean"),
             mean_confidence=("confidence", "mean"))
        .reindex(["High", "Medium", "Low"]).dropna(how="all").reset_index()
    )
    bands["share_pct"] = (bands["works"] / bands["works"].sum() * 100).round(1)

    similar = scored.loc[
        scored.get("similar_work_id", pd.Series("", index=scored.index)).astype(str).ne("")
    ].copy()
    # Similarity is recorded on both sides of a match. Canonicalising the two
    # IDs prevents one relationship from appearing twice in the review view.
    similar["_pair_key"] = similar.apply(
        lambda row: "||".join(sorted([str(row["work_id"]), str(row["similar_work_id"])])),
        axis=1,
    )
    pairs = similar.sort_values("similarity_score", ascending=False).drop_duplicates(
        "_pair_key"
    ).head(200)[
        ["work_id", "similar_work_id", "similarity_score", "state", "district",
         "work_category", "sanction_amount", "work_description"]
    ]

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_mode": ingest_report["config"]["data_mode"],
            "data_source": ingest_report["config"]["source_label"],
            "as_of_date": ingest_report["config"]["as_of_date"],
            "engine_version": result["config"]["engine_version"],
            "config_version": result["config"]["config_version"],
            "source_files": list(ingest_report["config"]["files"].values()),
            "limitations": [
                "The risk indicator is an analytical screening score, not a "
                "probability of fraud and not a legal finding.",
                "No fraud labels exist for this data, so precision and recall "
                "cannot be measured on it.",
                "Rule thresholds are administrative or analytical choices, not "
                "verified MPLADS guideline rules.",
                "Similar descriptions indicate potential duplication requiring "
                "verification, not confirmed duplicate works.",
                "District is inferred from the IDA text and its meaning "
                "requires confirmation.",
            ],
        },
        "dashboard": {
            "works_total": int(len(scored)),
            "works_requiring_review": int((scored["risk_band"] != "Low").sum()),
            "high_priority": int((scored["risk_band"] == "High").sum()),
            "works_completed": int(scored["is_completed"].sum()),
            "works_with_expenditure": int(scored["has_expenditure"].sum()),
            "total_sanctioned": float(scored["sanction_amount"].sum()),
            "total_expenditure": float(scored["total_expenditure"].sum(skipna=True)),
            "mean_data_completeness": round(float(scored["data_completeness"].mean()), 3),
            "risk_distribution": json.loads(bands.to_json(orient="records")),
            "flag_reasons": json.loads(
                scored.loc[scored["risk_band"] != "Low", "primary_reason"]
                .value_counts().rename_axis("reason").reset_index(name="works")
                .to_json(orient="records")
            ),
            "caps": result["config"]["caps"],
            "bands": result["config"]["bands"],
        },
        "detectors": result["detectors"],
        "rules": result["rules"],
        "data_quality": ingest_report,
        "priority_queue": json.loads(queue.to_json(orient="records", date_format="iso")),
        "similar_pairs": json.loads(pairs.to_json(orient="records", date_format="iso")),
        "national": agg.national_summary(scored),
        "rollups": {
            "state": records(roll.get("state")),
            "district": records(roll.get("district"), 400),
            "mp": records(roll.get("mp")),
            "vendor": records(roll.get("vendor"), 300),
        },
        "trends": {
            "monthly": records(trend["monthly"]),
            "risk_by_month": records(trend["risk_by_month"]),
        },
        "fund_utilisation": {
            "rows": records(utilisation["rows"]),
            "allocation_joined": utilisation["allocation_joined"],
            "match_rate_pct": utilisation["match_rate_pct"],
            "note": utilisation["note"],
        },
        "early_warning": records(warnings),
        "recommendation_pipeline": pipeline_summary,
        "detail_scope": detail_scope,
        "detail_available_for": len(details),
        "works": works,
    }

    path = outdir / "scored.json"
    detail_path = outdir / "work_details.json"
    # Compact separators: indentation on a payload this size is pure weight.
    path.write_text(json.dumps(payload, separators=(",", ":"), default=str))
    detail_path.write_text(json.dumps(details, separators=(",", ":"), default=str))
    scored[available].to_csv(outdir / "scored.csv", index=False)
    queue.to_csv(outdir / "priority_queue.csv", index=False)
    return {"scored_json": str(path), "work_details_json": str(detail_path)}
