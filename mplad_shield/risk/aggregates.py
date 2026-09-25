"""
Aggregations for the four audiences the problem statement names, plus the
trend, early-warning and briefing outputs it asks for.

Everything here is derived from the scored work-level table. Nothing new is
detected; this module reshapes what the detectors already found so that a
Ministry user, a State Nodal Authority, a District Authority and an MP each see
the same evidence at the level they act on.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

# A work with no payment recorded for longer than this, while still open, is
# treated as stalling. A screening threshold, not an official deadline.
STALLED_PAYMENT_GAP_DAYS = 365


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return (numerator / denominator.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)


def _rollup(scored: pd.DataFrame, keys: list[str], label: str) -> pd.DataFrame:
    """
    One aggregation shape reused for every level.

    The same columns at every level on purpose: a Ministry user comparing states
    and a district officer comparing agencies are asking the same question, and
    should not have to learn two tables to ask it.
    """
    grouped = scored.groupby(keys, dropna=False)

    out = grouped.agg(
        works=("work_id", "size"),
        sanctioned=("sanction_amount", "sum"),
        expenditure=("total_expenditure", "sum"),
        completed=("is_completed", "sum"),
        high_risk=("risk_band", lambda s: int((s == "High").sum())),
        flagged=("risk_band", lambda s: int((s != "Low").sum())),
        mean_risk=("risk_score", "mean"),
        mean_confidence=("confidence", "mean"),
    ).reset_index()

    out["utilisation_pct"] = (_safe_ratio(out["expenditure"], out["sanctioned"]) * 100).round(1)
    out["completion_pct"] = (_safe_ratio(out["completed"], out["works"]) * 100).round(1)
    out["high_risk_pct"] = (_safe_ratio(out["high_risk"], out["works"]) * 100).round(1)
    out["mean_risk"] = out["mean_risk"].round(1)
    out["mean_confidence"] = out["mean_confidence"].round(3)
    out["level"] = label

    return out.sort_values("high_risk", ascending=False).reset_index(drop=True)


def rollups(scored: pd.DataFrame, min_works: int = 5) -> dict:
    """Aggregations for each audience: Ministry, State, District, MP, vendor."""
    result = {
        "state": _rollup(scored, ["state"], "state"),
        "district": _rollup(scored, ["state", "district"], "district"),
        "mp": _rollup(scored, ["mp_name", "state"], "mp"),
    }

    if "primary_vendor" in scored.columns:
        vendors = scored.loc[scored["primary_vendor"].notna()]
        if len(vendors):
            vendor_rollup = _rollup(vendors, ["primary_vendor", "district"], "vendor")
            # Concentration is context, not an accusation: a busy agency in a
            # small district is ordinary. Reported, never scored.
            result["vendor"] = vendor_rollup[vendor_rollup["works"] >= min_works]

    return {name: frame for name, frame in result.items()}


def national_summary(scored: pd.DataFrame) -> dict:
    """The Ministry-level headline figures."""
    sanctioned = float(scored["sanction_amount"].sum())
    expenditure = float(scored["total_expenditure"].sum(skipna=True))
    return {
        "works": int(len(scored)),
        "states": int(scored["state"].nunique()),
        "districts": int(scored["district"].nunique()),
        "mps": int(scored["mp_name"].nunique()),
        "sanctioned": sanctioned,
        "expenditure": expenditure,
        "utilisation_pct": round(100 * expenditure / sanctioned, 1) if sanctioned else None,
        "completed": int(scored["is_completed"].sum()),
        "completion_pct": round(100 * scored["is_completed"].mean(), 1),
        "high_risk": int((scored["risk_band"] == "High").sum()),
        "flagged": int((scored["risk_band"] != "Low").sum()),
    }


# ------------------------------------------------------------- trends


def trends(scored: pd.DataFrame) -> dict:
    """
    Movement over time.

    Sanctions are dated by sanction month, completions by completion month and
    money by first payment. Three different clocks, so they are reported as
    three series rather than forced onto one, which would imply a relationship
    the data does not support.
    """

    def monthly(dates: pd.Series, values: pd.Series | None, name: str) -> pd.DataFrame:
        valid = pd.to_datetime(dates, errors="coerce")
        frame = pd.DataFrame({"month": valid.dt.to_period("M")})
        frame["value"] = 1 if values is None else values.to_numpy()
        frame = frame.dropna(subset=["month"])
        aggregated = (
            frame.groupby("month")["value"]
            .agg(["size", "sum"])
            .reset_index()
            .rename(columns={"size": "count", "sum": "amount"})
        )
        aggregated["month"] = aggregated["month"].astype(str)
        aggregated["series"] = name
        return aggregated

    sanctions = monthly(scored["sanction_date"], scored["sanction_amount"], "sanctioned")
    completions = monthly(
        scored.loc[scored["is_completed"], "completion_date"],
        scored.loc[scored["is_completed"], "sanction_amount"],
        "completed",
    )
    paid = scored.loc[scored["total_expenditure"].notna()]
    payments = monthly(paid["first_payment_date"], paid["total_expenditure"], "expenditure")

    # Risk composition per sanction month, so a reviewer can see whether the
    # flagged share is rising or simply tracking volume.
    risk_month = scored.copy()
    risk_month["month"] = pd.to_datetime(
        risk_month["sanction_date"], errors="coerce"
    ).dt.to_period("M")
    by_month = (
        risk_month.dropna(subset=["month"])
        .groupby("month")
        .agg(works=("work_id", "size"), high_risk=("risk_band", lambda s: int((s == "High").sum())))
        .reset_index()
    )
    by_month["month"] = by_month["month"].astype(str)
    by_month["high_risk_pct"] = (
        _safe_ratio(by_month["high_risk"], by_month["works"]) * 100
    ).round(1)

    return {
        "monthly": pd.concat([sanctions, completions, payments], ignore_index=True),
        "risk_by_month": by_month,
    }


# -------------------------------------------------- fund utilisation


def allocation_utilisation(scored: pd.DataFrame, allocation: pd.DataFrame | None) -> dict:
    """
    Sanctioned and spent per MP, with allocation context where it can be joined.

    On the supplied exports it cannot. The allocation file lists 543 MPs with
    Lok Sabha constituencies; the works exports carry 180 MPs and no
    constituency at all, which is the Rajya Sabha pattern. Exactly one name
    matches out of 180, and the near-misses are plainly different people
    (Radha Mohan Das Agrawal against Radha Mohan Singh).

    So the two files describe different houses. Rather than force a join and
    publish utilisation percentages that mean nothing, the per-MP figures are
    returned without allocation columns and the mismatch is reported.
    """
    by_mp = (
        scored.groupby(["mp_name", "state"], dropna=False)
        .agg(
            works=("work_id", "size"),
            sanctioned=("sanction_amount", "sum"),
            expenditure=("total_expenditure", "sum"),
            completed=("is_completed", "sum"),
            high_risk=("risk_band", lambda s: int((s == "High").sum())),
        )
        .reset_index()
    )
    by_mp["utilisation_pct"] = (
        _safe_ratio(by_mp["expenditure"], by_mp["sanctioned"]) * 100
    ).round(1)
    by_mp = by_mp.sort_values("sanctioned", ascending=False).reset_index(drop=True)

    if allocation is None or allocation.empty:
        return {
            "rows": by_mp,
            "allocation_joined": False,
            "match_rate_pct": 0.0,
            "note": "No allocation file was supplied, so utilisation is reported "
                    "against sanctioned amounts only.",
        }

    merged = by_mp.merge(
        allocation.rename(columns={"mp_name_allocation": "mp_name"})[
            ["mp_name", "state", "constituency", "allocated_amount_cumulative"]
        ],
        on=["mp_name", "state"],
        how="left",
    )
    matched = int(merged["allocated_amount_cumulative"].notna().sum())
    rate = round(100 * matched / max(len(merged), 1), 1)

    # Below this, the join is noise rather than signal and is discarded.
    if rate < 20.0:
        return {
            "rows": by_mp,
            "allocation_joined": False,
            "match_rate_pct": rate,
            "note": (
                f"The allocation file could not be joined: only {matched} of "
                f"{len(merged)} MPs matched ({rate}%). It lists "
                f"{len(allocation)} MPs with Lok Sabha constituencies, while "
                "these works exports carry MPs with no constituency, which is "
                "the Rajya Sabha pattern. The two files describe different "
                "houses. Per-MP figures below are against sanctioned amounts "
                "only; supply the matching allocation export to enable "
                "utilisation against entitlement."
            ),
        }

    merged["sanctioned_pct_of_allocation"] = (
        _safe_ratio(merged["sanctioned"], merged["allocated_amount_cumulative"]) * 100
    ).round(1)
    merged["spent_pct_of_allocation"] = (
        _safe_ratio(merged["expenditure"], merged["allocated_amount_cumulative"]) * 100
    ).round(1)
    merged["allocation_matched"] = merged["allocated_amount_cumulative"].notna()
    return {
        "rows": merged,
        "allocation_joined": True,
        "match_rate_pct": rate,
        "note": f"{matched} of {len(merged)} MPs matched the allocation file ({rate}%).",
    }


# -------------------------------------------------------- early warning


def early_warning(scored: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """
    Works that look likely to stall, with the reason stated.

    This is not a forecast model and is not presented as one. It is a rule over
    observable facts: the work is still open, it has run well past what
    comparable works took, and either no money has moved or none has moved for
    a long time. Saying that plainly is more defensible than calling a threshold
    a prediction.
    """
    open_works = scored.loc[~scored["is_completed"]].copy()
    if open_works.empty:
        return pd.DataFrame()

    overdue = open_works["days_sanction_to_reference"] > (
        open_works["peer_median_duration"] * 1.5
    )

    last_payment = pd.to_datetime(open_works["last_payment_date"], errors="coerce")
    gap_days = (as_of - last_payment).dt.days
    no_payment = ~open_works["has_expenditure"]
    payment_stalled = gap_days > STALLED_PAYMENT_GAP_DAYS

    at_risk = overdue.fillna(False) & (no_payment | payment_stalled.fillna(False))
    flagged = open_works.loc[at_risk].copy()
    if flagged.empty:
        return pd.DataFrame()

    flagged["days_since_last_payment"] = gap_days.loc[flagged.index]
    flagged["warning_reason"] = np.where(
        no_payment.loc[flagged.index],
        "Open past the peer-group duration with no payment recorded at all",
        "Open past the peer-group duration with no payment for over a year",
    )

    columns = [
        "work_id", "work_description", "state", "district", "mp_name",
        "sanction_amount", "sanction_date", "days_sanction_to_reference",
        "peer_median_duration", "days_since_last_payment", "total_expenditure",
        "risk_score", "risk_band", "confidence_band", "warning_reason",
    ]
    available = [c for c in columns if c in flagged.columns]
    return (
        flagged.sort_values("days_sanction_to_reference", ascending=False)[available]
        .head(300)
        .reset_index(drop=True)
    )


def recommendation_pipeline(pipeline: pd.DataFrame | None) -> dict:
    """
    Works recommended but never sanctioned.

    Invisible to any analysis built on the sanctioned register alone, because
    they carry no work ID at all. Reported as a queue of its own: a
    recommendation sitting unsanctioned for years is a different administrative
    problem from a sanctioned work running late, and belongs to a different
    person to chase.
    """
    if pipeline is None or pipeline.empty:
        return {"available": False, "works": 0, "value": 0.0, "by_state": [], "oldest": []}

    frame = pipeline.copy()
    frame["recommended_on"] = pd.to_datetime(frame["recommended_on"], errors="coerce")

    by_state = (
        frame.groupby("state", dropna=False)
        .agg(works=("recommended_amount", "size"), value=("recommended_amount", "sum"))
        .reset_index()
        .sort_values("works", ascending=False)
    )

    oldest = frame.sort_values("recommended_on").head(200)[
        ["work_description", "work_category", "state", "district", "mp_name",
         "recommended_amount", "recommended_on"]
    ]

    return {
        "available": True,
        "works": int(len(frame)),
        "value": float(frame["recommended_amount"].sum(skipna=True)),
        "by_state": json.loads(by_state.to_json(orient="records")),
        "oldest": json.loads(oldest.to_json(orient="records", date_format="iso")),
    }


# ------------------------------------------------------------ briefing


def _rupees(value) -> str:
    """Indian-notation rupees for narrative text."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "an unrecorded amount"
    value = float(value)
    if value >= 1e7:
        return f"Rs {value / 1e7:.2f} crore"
    if value >= 1e5:
        return f"Rs {value / 1e5:.2f} lakh"
    return f"Rs {value:,.0f}"


def briefing(row: pd.Series) -> str:
    """
    A plain-language summary of one work, composed from computed evidence.

    Written from the numbers the detectors produced rather than generated by a
    language model, so every sentence can be traced to a field and nothing can
    be invented. It also means the briefing works offline and costs nothing.
    """
    parts: list[str] = []

    what = row.get("work_description") or row.get("work_id")
    where = ", ".join(str(p) for p in (row.get("district"), row.get("state")) if p)
    parts.append(
        f"This {_rupees(row.get('sanction_amount'))} sanction"
        + (f" in {where}" if where else "")
        + f" carries an analytical risk indicator of {row.get('risk_score', 0):.0f} out of 100"
        f" ({row.get('risk_band', 'Low')} priority, {str(row.get('confidence_band', '')).lower()}"
        " confidence)."
    )

    median = row.get("peer_median_cost")
    if pd.notna(median) and median and pd.notna(row.get("sanction_amount")):
        multiple = row["sanction_amount"] / median
        if multiple >= 2:
            parts.append(
                f"It is {multiple:.1f} times the median of {_rupees(median)} for"
                f" {int(row.get('peer_size', 0))} comparable works grouped by"
                f" {row.get('peer_level', 'peer group')}."
            )

    ratio = row.get("expenditure_ratio")
    if row.get("is_completed") and pd.isna(row.get("total_expenditure")):
        parts.append("It is recorded as completed but carries no payment record at all.")
    elif pd.notna(ratio):
        parts.append(
            f"{ratio * 100:.0f}% of the sanctioned amount has been disbursed across"
            f" {int(row.get('payment_count') or 0)} payment(s)."
        )

    if row.get("similar_work_id"):
        parts.append(
            f"A closely similar work, {row['similar_work_id']}, was sanctioned in the"
            " same district and should be checked to confirm the two were separately"
            " executed."
        )

    if row.get("rule_reasons"):
        first_rule = str(row["rule_reasons"]).split("; ")[0]
        parts.append(f"Rule check: {first_rule}.")

    parts.append(
        "Suggested action: verify scope and supporting records before any site visit."
        " This summary describes unusual patterns only and does not establish"
        " irregularity or fraud."
    )
    return " ".join(parts)


def add_briefings(scored: pd.DataFrame, only_flagged: bool = True) -> pd.Series:
    """Attach a briefing to each work (flagged works only, by default)."""
    text = pd.Series("", index=scored.index, dtype=object)
    scope = scored["risk_band"] != "Low" if only_flagged else pd.Series(True, index=scored.index)
    for idx in scored.index[scope]:
        text.at[idx] = briefing(scored.loc[idx])
    return text
