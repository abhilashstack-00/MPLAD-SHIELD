"""
Builds one work-level table from the four MPLADS exports.

The sanctioned register is the spine: every sanctioned work appears exactly
once in the output, whether or not it has been completed or paid.

The step that must not be got wrong is expenditure. That export is
payment-level -- 17,000 payments across about 10,000 works, one work carrying
121 of them. Joining those rows directly onto the spine would multiply a work by
its payment count and inflate every count, sum and average downstream. So
payments are aggregated to one row per work *before* the join, and there is a
test asserting the output row count is unchanged.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import normalise as nz
from . import validate as vd
from .readers import IngestError, read_workbook, require_columns
from .settings import IngestConfig


def _load_sanctioned(path: Path, q: vd.Quarantine) -> pd.DataFrame:
    raw = read_workbook(path)
    require_columns(
        raw,
        ["Sr. No.", "Work", "State", "IDA", "Sanction Amount ( ₹ )", "Work Status"],
        "Works Sanctioned",
    )
    raw["work_id"] = nz.extract_work_id(raw["Work"])
    raw = vd.validate_sanctioned(raw, q)

    out = pd.DataFrame(
        {
            "work_id": raw["work_id"],
            "work_title": nz.strip_work_id(raw["Work"]),
            "work_description": raw["Work description"].replace({"": np.nan}),
            "work_category": raw["Work category"],
            "state": raw["State"],
            "district": nz.extract_district(raw["IDA"]),
            "ida_raw": raw["IDA"],
            "mp_name": nz.clean_mp_name(raw["Hon'ble Members of Parliament"]),
            "mp_type": raw["Elected/Nominated"],
            "sanction_amount": nz.parse_amount(raw["Sanction Amount ( ₹ )"]),
            "recommended_date": nz.parse_date(raw["Recommended date"]),
            "sanction_date": nz.parse_date(raw["Sanction Date"]),
            "work_status": raw["Work Status"],
            "source_file": raw["source_file"],
            "source_row": raw["source_row"],
        }
    ).reset_index(drop=True)

    # Descriptions are frequently blank in the dedicated column while the title
    # carries the same text; fall back rather than lose the work to similarity.
    out["work_description"] = out["work_description"].fillna(out["work_title"])
    out["description_normalised"] = nz.normalise_text(out["work_description"])
    out["description_is_mojibake"] = nz.is_mojibake(out["work_description"])
    return out


def _load_completed(path: Path, q: vd.Quarantine) -> pd.DataFrame:
    raw = read_workbook(path)
    require_columns(raw, ["Sr. No.", "Work", "Completion Date"], "Works Completed")
    raw["work_id"] = nz.extract_work_id(raw["Work"])
    raw = vd.validate_completed(raw, q)

    return pd.DataFrame(
        {
            "work_id": raw["work_id"],
            "completion_date": nz.parse_date(raw["Completion Date"]),
            "amount_disbursed_at_completion": nz.parse_amount(
                raw["Amount Disbursed ( ₹ )"]
            ),
            "completed_source_row": raw["source_row"],
        }
    ).reset_index(drop=True)


def _load_expenditure(path: Path, q: vd.Quarantine) -> pd.DataFrame:
    raw = read_workbook(path)
    require_columns(
        raw, ["Sr. No.", "Work ID", "Fund Disbursed Amount ( ₹ )"], "Expenditure"
    )
    raw["work_id"] = nz.extract_work_id(raw["Work ID"])
    raw["payment_amount"] = nz.parse_amount(raw["Fund Disbursed Amount ( ₹ )"])
    raw = vd.validate_expenditure(raw, q)

    return pd.DataFrame(
        {
            "work_id": raw["work_id"],
            "payment_amount": raw["payment_amount"],
            "payment_date": nz.parse_date(raw["Expenditure Date"]),
            "payment_status": raw["Payment Status"],
            "vendor_name": raw["Vendor Name"].astype(str).str.strip(),
            # The `Work` column here holds only ~96 distinct values: it is a
            # work-type taxonomy, not a description, and is a far better peer
            # grouping dimension than the 4-value scheme category.
            "work_type": raw["Work"],
            "source_row": raw["source_row"],
        }
    ).reset_index(drop=True)


def _aggregate_payments(payments: pd.DataFrame) -> pd.DataFrame:
    """Collapse payment rows to one row per work."""
    grouped = payments.groupby("work_id", dropna=True)

    aggregated = grouped.agg(
        total_expenditure=("payment_amount", "sum"),
        payment_count=("payment_amount", "size"),
        max_single_payment=("payment_amount", "max"),
        first_payment_date=("payment_date", "min"),
        last_payment_date=("payment_date", "max"),
        distinct_vendors=("vendor_name", "nunique"),
    ).reset_index()

    # Most-frequent value per work for the categorical fields, which is stable
    # when a work's payments disagree.
    def mode_of(column: str, name: str) -> pd.DataFrame:
        modes = (
            payments.dropna(subset=[column])
            .groupby("work_id")[column]
            .agg(lambda s: s.value_counts().idxmax())
            .reset_index()
            .rename(columns={column: name})
        )
        return modes

    aggregated = aggregated.merge(mode_of("work_type", "work_type"), on="work_id", how="left")
    aggregated = aggregated.merge(
        mode_of("vendor_name", "primary_vendor"), on="work_id", how="left"
    )

    pending = (
        payments.assign(pending=payments["payment_status"].ne("Payment Success"))
        .groupby("work_id")["pending"]
        .sum()
        .reset_index()
        .rename(columns={"pending": "payments_not_successful"})
    )
    return aggregated.merge(pending, on="work_id", how="left")


def _load_recommended(path: Path, q: vd.Quarantine) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read the recommendation register.

    This export covers a stage the sanctioned register cannot see. Works an MP
    has recommended but which have not been sanctioned carry no work ID at all
    -- their `WORK` value begins "NA-" -- so they are invisible to any analysis
    built on sanctioned works alone. They are returned separately as the
    pipeline frame.

    Returns (recommendations keyed by work_id, works recommended but unsanctioned).
    """
    raw = read_workbook(path)
    require_columns(raw, ["Sr. No.", "WORK", "State", "IDA"], "Works Recommended")

    summary = vd.find_summary_rows(raw, "Sr. No.")
    q.add(raw, summary, "Summary or total row", "Works_Recommended")
    raw = raw.loc[~summary].copy()

    amount_column = next(c for c in raw.columns if "AMOUNT" in c.upper())
    raw["work_id"] = nz.extract_work_id(raw["WORK"])
    raw["recommended_amount"] = nz.parse_amount(raw[amount_column])
    raw["recommended_on"] = nz.parse_date(raw["Recommended date"])
    raw["sanctioned_on"] = nz.parse_date(raw["Sanction Date"])

    matched = (
        raw.loc[raw["work_id"].notna(), ["work_id", "recommended_amount", "recommended_on"]]
        .drop_duplicates(subset="work_id")
        .reset_index(drop=True)
    )

    # No work ID and no sanction date: recommended, never sanctioned.
    open_mask = raw["work_id"].isna() & raw["sanctioned_on"].isna()
    pipeline = pd.DataFrame(
        {
            "work_description": raw.loc[open_mask, "Work description"],
            "work_category": raw.loc[open_mask, "Work category"],
            "state": raw.loc[open_mask, "State"],
            "district": nz.extract_district(raw.loc[open_mask, "IDA"]),
            "ida_raw": raw.loc[open_mask, "IDA"],
            "mp_name": nz.clean_mp_name(raw.loc[open_mask, "Hon'ble Members of Parliament"]),
            "recommended_amount": raw.loc[open_mask, "recommended_amount"],
            "recommended_on": raw.loc[open_mask, "recommended_on"],
            "source_row": raw.loc[open_mask, "source_row"],
        }
    ).reset_index(drop=True)

    return matched, pipeline


def _load_allocation(path: Path, q: vd.Quarantine) -> pd.DataFrame:
    """
    Read the allocation register.

    Two shapes exist. The Lok Sabha export carries a Constituency column; the
    Rajya Sabha export does not, because its members represent a whole state
    rather than a constituency. The MP column is also spelled differently
    between the two. Both are handled rather than assumed.
    """
    raw = read_workbook(path)
    require_columns(raw, ["Sr. No.", "State"], "Allocated Limit")
    raw = vd.validate_allocation(raw, q)

    mp_column = next(
        (c for c in raw.columns if "Members of Parliament" in c), None
    )
    if mp_column is None:
        raise IngestError(
            "Allocated Limit has no Members of Parliament column. "
            f"Found: {', '.join(raw.columns[:8])}"
        )
    amount_column = next(c for c in raw.columns if "AMOUNT" in c.upper())

    return pd.DataFrame(
        {
            "mp_name_allocation": nz.clean_mp_name(raw[mp_column]),
            "state": raw["State"],
            # Absent in the Rajya Sabha export by design.
            "constituency": raw["Constituency"] if "Constituency" in raw.columns else pd.NA,
            # Cumulative over the MP's tenure in the supplied files, NOT the
            # annual entitlement, so it must never be compared against one year.
            "allocated_amount_cumulative": nz.parse_amount(raw[amount_column]),
            "source_row": raw["source_row"],
        }
    ).reset_index(drop=True)


def build(data_dir: str | Path, config: IngestConfig | None = None) -> dict:
    """
    Read the four exports and return the unified dataset plus its reports.

    Returns a dict with `works`, `payments`, `allocation`, `quarantine` and
    `reports`.
    """
    config = config or IngestConfig()
    data_dir = Path(data_dir)
    q = vd.Quarantine()

    sanctioned = _load_sanctioned(data_dir / config.files["sanctioned"], q)
    completed = _load_completed(data_dir / config.files["completed"], q)
    payments = _load_expenditure(data_dir / config.files["expenditure"], q)
    allocation = _load_allocation(data_dir / config.files["allocation"], q)

    recommended_path = data_dir / config.files.get("recommended", "Works_Recommended.xlsx")
    if recommended_path.exists():
        recommendations, pipeline = _load_recommended(recommended_path, q)
    else:
        recommendations = pd.DataFrame(columns=["work_id", "recommended_amount", "recommended_on"])
        pipeline = pd.DataFrame()

    match = vd.matching_report(sanctioned, completed, payments)

    works = sanctioned.merge(completed, on="work_id", how="left")
    works = works.merge(_aggregate_payments(payments), on="work_id", how="left")
    works = works.merge(recommendations, on="work_id", how="left")

    if len(works) != len(sanctioned):
        raise AssertionError(
            f"Join multiplied rows: {len(sanctioned)} sanctioned works became "
            f"{len(works)}. Expenditure must be aggregated before joining."
        )

    as_of = pd.Timestamp(config.as_of_date)

    # What the MP recommended against what was ultimately sanctioned. This is
    # the closest thing in the available data to a cost-revision signal, and it
    # replaces a rule that had no field to run on at all.
    works["sanction_uplift_pct"] = (
        (works["sanction_amount"] - works["recommended_amount"])
        / works["recommended_amount"].replace(0, np.nan)
        * 100
    )
    works["has_recommendation"] = works["recommended_amount"].notna()

    works["expenditure_ratio"] = (
        works["total_expenditure"] / works["sanction_amount"].replace(0, np.nan)
    )
    works["has_expenditure"] = works["total_expenditure"].notna()
    works["is_completed"] = works["completion_date"].notna()
    works["days_recommendation_to_sanction"] = (
        works["sanction_date"] - works["recommended_date"]
    ).dt.days
    # Completed works are aged to completion; open works to the as-of date.
    reference = works["completion_date"].fillna(as_of)
    works["days_sanction_to_reference"] = (reference - works["sanction_date"]).dt.days
    works["age_basis"] = np.where(works["is_completed"], "completion_date", "as_of_date")

    # Peer grouping prefers the 96-value work type and falls back to the
    # 4-value scheme category, which is 97% "Normal/Others" and on its own
    # compares a road against a classroom.
    works["peer_key_primary"] = (
        works["work_type"].fillna("UNKNOWN") + " | " + works["state"].fillna("UNKNOWN")
    )
    works["peer_key_fallback"] = (
        works["work_category"].fillna("UNKNOWN") + " | " + works["state"].fillna("UNKNOWN")
    )
    works["has_work_type"] = works["work_type"].notna()

    key_fields = [
        "sanction_amount", "sanction_date", "recommended_date", "work_description",
        "state", "district", "work_status", "total_expenditure",
    ]
    works["data_completeness"] = works[key_fields].notna().mean(axis=1).round(3)

    reports = {
        "config": {**asdict(config), "as_of_date": str(config.as_of_date)},
        "matching": match,
        "quarantine": q.summary(),
        "quarantined_rows": int(len(q.frame())),
        "dates": vd.date_consistency(works, as_of),
        "amounts": vd.amount_consistency(works),
        "columns": (
            vd.column_profile(sanctioned, "sanctioned")
            + vd.column_profile(completed, "completed")
            + vd.column_profile(payments, "expenditure")
            + vd.column_profile(allocation, "allocation")
        ),
        "recommendation_pipeline": {
            "recommended_records": int(len(recommendations) + len(pipeline)),
            "matched_to_sanctioned": int(
                works["has_recommendation"].sum() if "has_recommendation" in works else 0
            ),
            "recommended_not_sanctioned": int(len(pipeline)),
            "pipeline_value": float(pipeline["recommended_amount"].sum()) if len(pipeline) else 0.0,
        },
        "coverage": {
            "works_total": int(len(works)),
            "works_completed": int(works["is_completed"].sum()),
            "works_with_expenditure": int(works["has_expenditure"].sum()),
            "works_with_work_type": int(works["has_work_type"].sum()),
            "states": int(works["state"].nunique()),
            "districts": int(works["district"].nunique()),
            "mps": int(works["mp_name"].nunique()),
            "mojibake_descriptions": int(works["description_is_mojibake"].sum()),
        },
    }

    return {
        "works": works,
        "pipeline": pipeline,
        "payments": payments,
        "allocation": allocation,
        "quarantine": q.frame(),
        "reports": reports,
    }
