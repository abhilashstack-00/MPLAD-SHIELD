"""
Tests for the MPLAD-SHIELD risk engine.

These check the properties that must hold for the score to be defensible to a
reviewer -- that it stays in range, that it decomposes exactly, and that a
definitive guideline breach cannot be quietly diluted by quiet detectors.
"""

import numpy as np
import pytest

from mplad_shield import config, data_gen, detectors, features, pipeline, scoring


@pytest.fixture(scope="module")
def register():
    return data_gen.generate(n=400, seed=7)


@pytest.fixture(scope="module")
def result(register):
    return pipeline.run(register, top_n=25)


def test_indicator_caps_are_valid():
    config.WEIGHTS.validate()


def test_generated_register_has_required_columns(register):
    missing = set(data_gen.REQUIRED_COLUMNS) - set(register.columns)
    assert not missing, f"generator is missing {missing}"


def test_generator_labels_irregularities(register):
    assert register["is_anomaly"].sum() > 0
    assert register.loc[register["is_anomaly"], "anomaly_type"].ne("").any()


def test_scores_stay_in_range(result):
    scores = result.scored["risk_score"]
    assert scores.between(0, 100).all()
    assert result.scored["confidence"].between(0, 1).all()


def test_indicators_are_bounded(result):
    for indicator in scoring.INDICATORS:
        values = result.scored[indicator].fillna(0)
        assert values.between(0, 1).all(), f"{indicator} escaped [0, 1]"


def test_score_decomposes_exactly(result):
    """The points attributed to each indicator must reconstruct the score."""
    points = result.scored[[f"points_{i}" for i in scoring.INDICATORS]].sum(axis=1)
    assert np.allclose(points, result.scored["risk_score"], atol=0.15)


def test_inadmissible_category_saturates_compliance(register):
    engineered = features.build(register)
    score, reasons = detectors.compliance(engineered)
    inadmissible = engineered["work_category"].isin(config.INADMISSIBLE_CATEGORIES)
    if inadmissible.any():
        assert score[inadmissible].min() >= 0.99
        assert reasons[inadmissible].str.len().gt(0).all()


def test_duplicate_detector_separates_planted_duplicates(register):
    engineered = features.build(register)
    similarity, _ = detectors.duplicate_similarity(engineered)
    planted = engineered["anomaly_type"] == "duplicate_work"
    if planted.sum() >= 3:
        assert similarity[planted].mean() > similarity[~planted].mean() * 2


def test_cost_detector_ignores_the_cheap_tail(register):
    """Works far below their peers must not be scored as cost risks."""
    engineered = features.build(register)
    cheap = engineered["cost_robust_z"] < -1
    if cheap.any():
        assert detectors.cost_deviation(engineered)[cheap].max() == 0


def test_ranking_beats_chance(result):
    metrics = result.metrics
    assert metrics["available"]
    assert metrics["roc_auc"] > 0.75, "ranking is no better than a coin flip"
    assert metrics["at_k"]["top_25"]["precision"] > metrics["base_rate"]


def test_queue_is_sorted_and_bounded(result):
    scores = result.queue["risk_score"].to_numpy()
    assert (np.diff(scores) <= 1e-9).all(), "queue is not in descending order"
    assert len(result.queue) <= 25


def test_every_flagged_work_carries_a_reason(result):
    flagged = result.scored[result.scored["risk_band"] != "Low"]
    assert flagged["explanation"].apply(len).gt(0).all()
    assert flagged["primary_reason"].str.len().gt(0).all()


def test_export_round_trips(result, tmp_path):
    import json

    paths = pipeline.export(result, tmp_path)
    payload = json.loads(open(paths["scored_json"]).read())
    assert payload["projects"]
    assert payload["dashboard"]["projects_analysed"] == len(result.scored)
    assert "not establish irregularity or fraud" in payload["disclaimer"]


def test_missing_columns_are_reported_by_name(tmp_path, register):
    path = tmp_path / "bad.csv"
    register.drop(columns=["expenditure"]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="expenditure"):
        pipeline.load(path)
