"""
End-to-end orchestration: register in, scored queue out.

The export step matters as much as the scoring. The UI never runs a model --
it reads `scored.json`, which means a demo cannot break because a Python
process died, and the numbers on screen are still the ones the real detectors
produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import data_gen, detectors, evaluate, features, scoring
from .config import THRESHOLDS, WEIGHTS
from .models import MultivariateDetector


@dataclass
class Result:
    scored: pd.DataFrame
    queue: pd.DataFrame
    agencies: pd.DataFrame
    metrics: dict
    bands: pd.DataFrame
    reasons: pd.DataFrame


def load(path: str | Path) -> pd.DataFrame:
    """
    Read a real register from CSV.

    Column names must match `data_gen.REQUIRED_COLUMNS`. Anything missing is
    reported by name rather than surfacing later as a confusing KeyError deep
    inside a detector.
    """
    df = pd.read_csv(path)
    missing = [c for c in data_gen.REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Register is missing required columns: " + ", ".join(missing)
        )
    return df


def run(df: pd.DataFrame, top_n: int = 50) -> Result:
    """Score a register. `df` may be synthetic or real."""
    engineered = features.build(df)

    # --- univariate detectors -------------------------------------------
    engineered["cost_deviation"] = detectors.cost_deviation(engineered)
    engineered["delay"] = detectors.delay(engineered)
    engineered["expenditure_mismatch"] = detectors.expenditure_mismatch(engineered)

    duplicate_score, duplicate_partner = detectors.duplicate_similarity(engineered)
    engineered["duplicate"] = duplicate_score
    engineered["duplicate_match_id"] = duplicate_partner

    compliance_score, compliance_reasons = detectors.compliance(engineered)
    engineered["compliance"] = compliance_score
    engineered["compliance_reasons"] = compliance_reasons

    # --- unsupervised layer ---------------------------------------------
    matrix, feature_names = features.numeric_matrix(engineered)
    multivariate = MultivariateDetector()
    signals = multivariate.fit_score(matrix, feature_names)
    for key, values in signals.items():
        engineered[key] = values
    engineered["multivariate"] = signals["multivariate_score"]

    attributions = multivariate.attribute()

    # --- combine ---------------------------------------------------------
    scored = scoring.score(engineered, attributions)

    return Result(
        scored=scored,
        queue=scoring.priority_queue(scored, top_n=top_n),
        agencies=scoring.agency_rollup(scored),
        metrics=evaluate.evaluate(scored),
        bands=evaluate.band_summary(scored),
        reasons=evaluate.reason_summary(scored),
    )


def _clean(value):
    """Make numpy and pandas scalars JSON-serialisable."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else round(float(value), 4)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if value is pd.NaT or (isinstance(value, float) and not np.isfinite(value)):
        return None
    return value


def export(result: Result, outdir: str | Path) -> dict:
    """Write everything the UI and the report need. Returns the paths written."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    project_fields = [
        "project_id", "state", "district", "block", "latitude", "longitude",
        "constituency", "sector", "work_category", "work_description",
        "implementing_agency", "sanction_date", "expected_completion_date",
        "actual_completion_date", "sanctioned_cost", "revised_cost",
        "effective_cost", "expenditure", "physical_progress_pct", "status",
        "peer_median_cost", "peer_cost_percentile", "peer_size",
        "cost_robust_z", "overrun_days", "expected_duration_days",
        "expenditure_ratio_pct", "progress_gap_pct", "cost_escalation_pct",
        "duplicate_match_id", "compliance_reasons", "agency_work_share",
        "isolation_forest_score", "dbscan_is_noise",
        "risk_score", "risk_band", "confidence", "primary_reason",
        "review_status", "assessment",
    ] + [f"points_{i}" for i in scoring.INDICATORS]

    available = [c for c in project_fields if c in result.scored.columns]

    projects = []
    for _, row in result.scored.iterrows():
        record = {field: _clean(row[field]) for field in available}
        record["explanation"] = row["explanation"]
        projects.append(record)

    dashboard = {
        "projects_analysed": int(len(result.scored)),
        "potential_risks": int((result.scored["risk_band"] != "Low").sum()),
        "pending_review": int((result.scored["review_status"] == "Pending review").sum()),
        "risk_distribution": result.bands.to_dict(orient="records"),
        "flag_reasons": result.reasons.to_dict(orient="records"),
        "weights": WEIGHTS.as_dict(),
        "bands": {"high": THRESHOLDS.band_high, "medium": THRESHOLDS.band_medium},
    }

    payload = {
        # Present so that if this payload is ever synced to the frontend, the
        # dashboard banner says plainly that the figures are generated.
        "meta": {
            "data_mode": "synthetic_benchmark",
            "data_source": "Locally generated synthetic register with planted "
                           "irregularities — NOT MPLADS data",
            "as_of_date": "n/a",
            "engine_version": "v1-benchmark",
            "config_version": "v1",
            "source_files": ["mplad_shield/data_gen.py"],
            "limitations": [
                "Every record here is generated. No work, agency, MP or amount "
                "describes anything real.",
                "Precision and recall measured on this register describe the "
                "detectors, not performance on real MPLADS data.",
            ],
        },
        "generated_by": "MPLAD-SHIELD risk engine (synthetic benchmark)",
        "disclaimer": (
            "Risk scores indicate statistically unusual patterns requiring human "
            "review. They do not establish irregularity or fraud."
        ),
        "dashboard": dashboard,
        "priority_queue": json.loads(
            result.queue.to_json(orient="records", date_format="iso")
        ),
        "agencies": json.loads(
            result.agencies.to_json(orient="records", date_format="iso")
        ),
        "projects": projects,
        "benchmark": result.metrics,
    }

    paths = {
        "scored_json": outdir / "scored.json",
        "scored_csv": outdir / "scored.csv",
        "queue_csv": outdir / "priority_queue.csv",
        "metrics_json": outdir / "benchmark.json",
    }

    paths["scored_json"].write_text(json.dumps(payload, indent=2, default=str))
    result.scored[available].to_csv(paths["scored_csv"], index=False)
    result.queue.to_csv(paths["queue_csv"], index=False)
    paths["metrics_json"].write_text(json.dumps(result.metrics, indent=2, default=str))

    return {name: str(path) for name, path in paths.items()}


def run_demo(n: int = 1200, seed: int = 42, outdir: str | Path = "outputs") -> Result:
    """Generate a labelled register, score it, export, and return the result."""
    register = data_gen.generate(n=n, seed=seed)
    result = run(register)
    export(result, outdir)
    return result
