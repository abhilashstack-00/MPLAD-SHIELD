"""
Tests for the V2 risk engine.

The properties checked here are the ones the system's credibility rests on: that
a detector which cannot run says so rather than returning a quiet zero, that the
score decomposes exactly into the points shown to a reviewer, and that a weak
peer group lowers confidence rather than being hidden.
"""

import json

import numpy as np
import pandas as pd
import pytest

from mplad_shield.risk import detectors as det
from mplad_shield.risk import features as ft
from mplad_shield.risk import pipeline as rp
from mplad_shield.risk.config import INDICATORS, RiskConfig


def make_works(n: int = 60) -> pd.DataFrame:
    """A unified work-level frame shaped like the ingestion output."""
    rng = np.random.default_rng(7)
    sanction = pd.Timestamp("2023-04-01") + pd.to_timedelta(rng.integers(0, 200, n), "D")
    amount = rng.normal(500000, 60000, n).round(-3)

    frame = pd.DataFrame(
        {
            "work_id": [f"WS/MP1/2023-2024/{i:04d}" for i in range(n)],
            "work_description": [
                f"{verb} of {asset} at {place}-{i}"
                for i, (verb, asset, place) in enumerate(
                    zip(
                        rng.choice(["Construction", "Providing", "Installation"], n),
                        rng.choice(["CC road", "drainage", "toilet block", "hand pump"], n),
                        rng.choice(["Rampur", "Kesarpur", "Manjari", "Dhanora"], n),
                    )
                )
            ],
            "work_category": "Normal/Others",
            "work_type": "Roads",
            "state": "Bihar",
            "district": "Gaya",
            "ida_raw": "GAYA(DISTRICT MAGISTRATE GAYA_IDA)",
            "mp_name": "Shri A B",
            "sanction_amount": amount,
            "recommended_date": sanction - pd.Timedelta(days=30),
            "sanction_date": sanction,
            "completion_date": sanction + pd.Timedelta(days=120),
            "work_status": "Work Completed",
            "is_completed": True,
            "total_expenditure": amount,
            "expenditure_ratio": 1.0,
            "payment_count": 1.0,
            "max_single_payment": amount,
            "distinct_vendors": 1.0,
            "primary_vendor": "Vendor A",
            "first_payment_date": sanction + pd.Timedelta(days=60),
            "last_payment_date": sanction + pd.Timedelta(days=110),
            "payments_not_successful": 0.0,
            "has_expenditure": True,
            "days_recommendation_to_sanction": 30.0,
            "days_sanction_to_reference": 120.0,
            "age_basis": "completion_date",
            "data_completeness": 1.0,
        }
    )
    frame["description_normalised"] = frame["work_description"].str.lower()
    frame["description_is_mojibake"] = False
    return frame


@pytest.fixture
def works() -> pd.DataFrame:
    return make_works()


@pytest.fixture
def config() -> RiskConfig:
    return RiskConfig()


# ------------------------------------------------------- peer groups


def test_peer_cascade_prefers_work_type(works, config):
    prepared = ft.assign_peer_groups(works, config)
    assert (prepared["peer_level"] == "work_type + state").all()


def test_small_groups_fall_through_to_insufficient(config):
    """A group too small to support a comparison must not be used anyway."""
    tiny = make_works(3)
    tiny["state"] = ["Bihar", "Kerala", "Assam"]
    tiny["work_type"] = ["Roads", "Drains", "Toilets"]
    prepared = ft.assign_peer_groups(tiny, config)
    assert (prepared["peer_level"] == "insufficient").all()
    assert prepared["peer_key"].isna().all()


def test_fallback_level_is_recorded(config):
    works = make_works(40)
    works["work_type"] = np.nan  # no work type: must fall back to category
    prepared = ft.assign_peer_groups(works, config)
    assert (prepared["peer_level"] == "category + state").all()


# --------------------------------------------------------- detectors


def test_cost_detector_ignores_the_cheap_tail(works, config):
    works.loc[0, "sanction_amount"] = 1000  # far below peers
    prepared = ft.build(works, config)
    signal = det.cost_deviation(prepared, config).signal
    assert signal.iloc[0] == 0.0


def test_cost_detector_flags_the_expensive_tail(works, config):
    works.loc[0, "sanction_amount"] = 50_000_000
    prepared = ft.build(works, config)
    signal = det.cost_deviation(prepared, config).signal
    assert signal.iloc[0] > 0.5


def test_cost_detector_returns_null_without_a_peer_group(config):
    tiny = ft.build(make_works(3), config)
    signal = det.cost_deviation(tiny, config).signal
    assert signal.isna().all(), "no peer group must mean no verdict, not a zero"


def test_missing_field_makes_a_detector_skip_not_score(works, config):
    """
    The property the whole honesty argument rests on: a detector without its
    field reports `skipped`, never 0.0.
    """
    prepared = ft.build(works, config).drop(columns=["total_expenditure"])
    result = det.expenditure_consistency(prepared, config)
    assert result.status == "skipped"
    assert "total_expenditure" in result.missing_fields
    assert result.signal.isna().all()


def test_underspend_on_a_completed_work_is_flagged(works, config):
    works.loc[0, "expenditure_ratio"] = 0.4
    prepared = ft.build(works, config)
    signal = det.expenditure_consistency(prepared, config).signal
    assert signal.iloc[0] > 0


def test_completed_work_with_no_payment_record_is_flagged(works, config):
    works.loc[0, ["has_expenditure", "total_expenditure", "expenditure_ratio"]] = [
        False, np.nan, np.nan
    ]
    prepared = ft.build(works, config)
    assert det.expenditure_consistency(prepared, config).signal.iloc[0] > 0


def test_similarity_finds_a_planted_near_duplicate(works, config):
    """A duplicate differing by spacing and punctuation must be found."""
    works.loc[0, "work_description"] = "Construction of CC road at Rampur-0"
    works.loc[1, "work_description"] = "Construction of CC road,  at   Rampur-0 "
    works["description_normalised"] = works["work_description"].str.lower()
    prepared = ft.build(works, config)
    result = det.similarity(prepared, config)
    assert result.evidence["similarity_score"].iloc[1] > config.thresholds.similarity_floor
    assert result.evidence["similar_work_id"].iloc[1] == works.loc[0, "work_id"]


def test_abbreviated_duplicates_are_detected(works, config):
    """
    "Constrn." against "Construction" must still match.

    This is the case character n-grams exist for: word-level matching treats
    the two as unrelated tokens. Worth knowing that TF-IDF similarity depends
    on the variety of the surrounding corpus — in a district where every
    description follows one template and differs only by village name, IDF
    weighting flattens and scores shift. The fixture therefore varies verbs,
    assets and places the way a real district register does.
    """
    works.loc[0, "work_description"] = "Construction of CC road at Rampur-0"
    works.loc[1, "work_description"] = "Constrn. of CC road at Rampur-0"
    works["description_normalised"] = works["work_description"].str.lower()
    prepared = ft.build(works, config)
    evidence = det.similarity(prepared, config).evidence
    assert evidence["similarity_score"].iloc[1] > config.thresholds.similarity_floor
    assert evidence["similar_work_id"].iloc[1] == works.loc[0, "work_id"]


def test_unrelated_works_are_not_matched(works, config):
    """A road and a hand pump in the same district must not pair up."""
    works.loc[0, "work_description"] = "Construction of CC road at Rampur-0"
    works.loc[1, "work_description"] = "Providing of hand pump at Dhanora-1"
    works["description_normalised"] = works["work_description"].str.lower()
    prepared = ft.build(works, config)
    evidence = det.similarity(prepared, config).evidence
    partner = evidence["similar_work_id"].iloc[0]
    assert partner != works.loc[1, "work_id"]


def test_unevaluable_rules_are_reported_not_passed(works, config):
    """
    A rule whose field is absent must say so, not report clean.

    COMP_001 (inadmissible category) still has no supporting field in any
    export. COMP_002 was in this list until the recommendation register
    arrived, which supplies the recommended amount and makes the same question
    answerable — it is now COST_002 and evaluates.
    """
    prepared = ft.build(works, config)
    _, report = det.compliance(prepared, config)
    unevaluated = {r["rule_id"] for r in report if r["status"] == "not_evaluated"}
    assert "COMP_001" in unevaluated


def test_sanction_uplift_rule_fires_on_a_large_gap(works, config):
    """Sanctioned materially above what the MP recommended."""
    works["recommended_amount"] = works["sanction_amount"]
    works.loc[0, "recommended_amount"] = works.loc[0, "sanction_amount"] / 3
    works["sanction_uplift_pct"] = (
        (works["sanction_amount"] - works["recommended_amount"])
        / works["recommended_amount"] * 100
    )
    prepared = ft.build(works, config)
    result, report = det.compliance(prepared, config)
    assert result.signal.iloc[0] > 0
    uplift = next(r for r in report if r["rule_id"] == "COST_002")
    assert uplift["status"] == "evaluated" and uplift["records_flagged"] >= 1


def test_uplift_rule_skips_without_a_recommendation_register(works, config):
    """Without the recommendation export the rule must report not-evaluated."""
    prepared = ft.build(works, config)
    assert "sanction_uplift_pct" not in prepared.columns
    _, report = det.compliance(prepared, config)
    uplift = next(r for r in report if r["rule_id"] == "COST_002")
    assert uplift["status"] == "not_evaluated"


def test_rules_carry_their_tier_and_basis(works, config):
    prepared = ft.build(works, config)
    _, report = det.compliance(prepared, config)
    for rule in report:
        assert rule["rule_type"] in {
            "verified", "financial_consistency", "configurable",
            "heuristic", "data_quality",
        }
        assert rule["source"]


def test_ceiling_rule_fires_on_a_large_sanction(works, config):
    works.loc[0, "sanction_amount"] = 20_000_000
    prepared = ft.build(works, config)
    result, report = det.compliance(prepared, config)
    assert result.signal.iloc[0] > 0
    ceiling = next(r for r in report if r["rule_id"] == "CEIL_001")
    assert ceiling["records_flagged"] >= 1


# ----------------------------------------------------------- scoring


def test_score_decomposes_exactly(works, config):
    """The score is defined as the sum of its points, so this is exact."""
    scored = rp.run(works, config)["scored"]
    points = scored[[f"points_{n}" for n in INDICATORS]].sum(axis=1)
    assert np.allclose(points, scored["risk_score"], atol=0.01)


def test_scores_and_confidence_stay_in_range(works, config):
    scored = rp.run(works, config)["scored"]
    assert scored["risk_score"].between(0, 100).all()
    assert scored["confidence"].between(0, 1).all()
    assert not scored["risk_score"].isna().any()


def test_weak_peer_group_lowers_confidence(config):
    strong = rp.run(make_works(60), config)["scored"]["confidence"].mean()
    weak_frame = make_works(60)
    weak_frame["work_type"] = np.nan
    weak = rp.run(weak_frame, config)["scored"]["confidence"].mean()
    assert weak < strong, "a broad-category fallback must cost confidence"


def test_confidence_reason_is_stated_in_words(works, config):
    scored = rp.run(works, config)["scored"]
    assert scored["confidence_reason"].str.len().gt(0).all()


def test_every_flagged_work_carries_a_reason(works, config):
    works.loc[0, "sanction_amount"] = 50_000_000
    scored = rp.run(works, config)["scored"]
    flagged = scored[scored["risk_band"] != "Low"]
    if len(flagged):
        assert flagged["explanation"].apply(len).gt(0).all()
        assert flagged["primary_reason"].str.len().gt(0).all()


def test_assessment_wording_never_claims_fraud(works, config):
    scored = rp.run(works, config)["scored"]
    text = " ".join(scored["assessment"].unique()).lower()
    assert "does not establish fraud" in text
    for banned in ("fraudulent", "corrupt", "guilty", "confirmed duplicate"):
        assert banned not in text


def test_detector_statuses_are_reported(works, config):
    result = rp.run(works, config)
    names = {d["detector"] for d in result["detectors"]}
    assert set(INDICATORS) <= names
    for detector in result["detectors"]:
        assert detector["status"] in {"active", "skipped"}


# ------------------------------------------------------------ export


def _ingest_stub() -> dict:
    return {
        "config": {
            "data_mode": "official_export",
            "source_label": "test",
            "as_of_date": "2026-09-24",
            "files": {"sanctioned": "Works_Sanctioned.xlsx"},
        }
    }


def test_export_writes_index_and_detail(works, config, tmp_path):
    result = rp.run(works, config)
    paths = rp.export(result, _ingest_stub(), tmp_path, detail_scope="all")
    payload = json.loads(open(paths["scored_json"]).read())
    details = json.loads(open(paths["work_details_json"]).read())

    assert payload["dashboard"]["works_total"] == len(works)
    assert len(details) == len(works)
    assert payload["meta"]["data_mode"] == "official_export"
    assert payload["meta"]["limitations"]


def test_flagged_scope_exports_fewer_details_than_all(works, config, tmp_path):
    works.loc[0, "sanction_amount"] = 50_000_000
    result = rp.run(works, config)
    rp.export(result, _ingest_stub(), tmp_path / "a", detail_scope="flagged")
    rp.export(result, _ingest_stub(), tmp_path / "b", detail_scope="all")
    flagged = json.loads(open(tmp_path / "a" / "work_details.json").read())
    every = json.loads(open(tmp_path / "b" / "work_details.json").read())
    assert len(flagged) <= len(every)


def test_export_contains_no_nan_scores(works, config, tmp_path):
    result = rp.run(works, config)
    paths = rp.export(result, _ingest_stub(), tmp_path)
    payload = json.loads(open(paths["scored_json"]).read())
    for work in payload["works"]:
        assert isinstance(work["risk_score"], (int, float))
        assert work["risk_score"] == work["risk_score"]  # not NaN
