"""
Validation, quarantine and reporting.

Rows are never silently dropped. Anything removed goes to a quarantine frame
carrying the reason and its original row number, and the counts surface in the
data-quality report and on the dashboard. A pipeline that quietly discards the
records it cannot handle will always look cleaner than it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .settings import IMPLAUSIBLE_PAYMENT_CEILING

# Work Status values actually present in the supplied sanctioned export. A value
# outside this set means something other than a status has landed in the column
# -- the supplied file has one row whose status reads "17629503056.99", a grand
# total that leaked into a data field.
KNOWN_WORK_STATUS = {
    "Physical Inspection",
    "Sanction",
    "Vendor Identification",
    "Work partially Completed",
    "Work Completed",
    "Time Estimation",
}

SUMMARY_MARKERS = ("grand total", "total", "subtotal", "summary", "overall total")


@dataclass
class Quarantine:
    """Rows removed from processing, with the reason and where they came from."""

    rows: list = field(default_factory=list)

    def add(self, frame: pd.DataFrame, mask: pd.Series, reason: str, source: str) -> None:
        mask = mask.fillna(False)
        if not mask.any():
            return
        removed = frame.loc[mask].copy()
        removed["quarantine_reason"] = reason
        removed["quarantine_source"] = source
        self.rows.append(removed)

    def frame(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=["quarantine_reason", "quarantine_source"])
        return pd.concat(self.rows, ignore_index=True)

    def summary(self) -> list[dict]:
        frame = self.frame()
        if frame.empty:
            return []
        grouped = (
            frame.groupby(["quarantine_source", "quarantine_reason"])
            .size()
            .reset_index(name="rows")
        )
        return grouped.to_dict(orient="records")


def find_summary_rows(frame: pd.DataFrame, key_column: str) -> pd.Series:
    """
    Identify total or summary rows.

    Only the key column is examined. Scanning every column would match ordinary
    project rows whose description happens to contain the word "total", which is
    how a genuine work gets deleted as a footer.
    """
    text = frame[key_column].astype(str).str.strip().str.lower()
    return text.isin(SUMMARY_MARKERS) | text.str.startswith("grand total")


def validate_sanctioned(frame: pd.DataFrame, quarantine: Quarantine) -> pd.DataFrame:
    """Remove summary and malformed rows from the sanctioned register."""
    source = "Works_Sanctioned"

    quarantine.add(frame, find_summary_rows(frame, "Sr. No."), "Summary or total row", source)
    frame = frame.loc[~find_summary_rows(frame, "Sr. No.")].copy()

    bad_status = frame["Work Status"].notna() & ~frame["Work Status"].isin(KNOWN_WORK_STATUS)
    quarantine.add(
        frame, bad_status, "Work Status holds a value that is not a status", source
    )
    frame = frame.loc[~bad_status].copy()

    missing_id = frame["work_id"].isna()
    quarantine.add(frame, missing_id, "No work ID could be extracted", source)
    frame = frame.loc[~missing_id].copy()

    return frame


def validate_completed(frame: pd.DataFrame, quarantine: Quarantine) -> pd.DataFrame:
    source = "Works_Completed"
    summary = find_summary_rows(frame, "Sr. No.")
    quarantine.add(frame, summary, "Summary or total row", source)
    frame = frame.loc[~summary].copy()

    missing_id = frame["work_id"].isna()
    quarantine.add(frame, missing_id, "No work ID could be extracted", source)
    return frame.loc[~missing_id].copy()


def validate_expenditure(frame: pd.DataFrame, quarantine: Quarantine) -> pd.DataFrame:
    """
    Clean the payment-level export.

    The implausible-payment rule matters: the supplied file contains a single
    payment of roughly Rs 1,276 crore against a maximum sanction anywhere of
    Rs 7.35 crore. Aggregated without challenge it would dominate every
    expenditure statistic in the system.
    """
    source = "Expenditure"

    summary = find_summary_rows(frame, "Sr. No.")
    quarantine.add(frame, summary, "Summary or total row", source)
    frame = frame.loc[~summary].copy()

    missing_id = frame["work_id"].isna()
    quarantine.add(frame, missing_id, "No work ID present", source)
    frame = frame.loc[~missing_id].copy()

    implausible = frame["payment_amount"] > IMPLAUSIBLE_PAYMENT_CEILING
    quarantine.add(
        frame,
        implausible,
        f"Payment exceeds the plausibility ceiling of Rs {IMPLAUSIBLE_PAYMENT_CEILING:,}",
        source,
    )
    frame = frame.loc[~implausible].copy()

    non_positive = frame["payment_amount"].notna() & (frame["payment_amount"] <= 0)
    quarantine.add(frame, non_positive, "Payment amount is zero or negative", source)
    return frame.loc[~non_positive].copy()


def validate_allocation(frame: pd.DataFrame, quarantine: Quarantine) -> pd.DataFrame:
    """Drop the explicit Grand Total row carried in the allocation export."""
    source = "Allocated_Limit"
    summary = find_summary_rows(frame, "Sr. No.") | frame["State"].isna()
    quarantine.add(frame, summary, "Summary or total row", source)
    return frame.loc[~summary].copy()


# ------------------------------------------------------------- reporting


def column_profile(frame: pd.DataFrame, label: str) -> list[dict]:
    """Per-column completeness, for the Data Quality page."""
    rows = []
    skip = {"source_row", "source_file", "source_sheet", "ingested_at"}
    for column in frame.columns:
        if column in skip:
            continue
        non_null = int(frame[column].notna().sum())
        rows.append(
            {
                "dataset": label,
                "column": column,
                "non_null": non_null,
                "missing": int(len(frame) - non_null),
                "completeness_pct": round(100 * non_null / max(len(frame), 1), 1),
                "distinct": int(frame[column].nunique(dropna=True)),
            }
        )
    return rows


def matching_report(
    sanctioned: pd.DataFrame, completed: pd.DataFrame, expenditure: pd.DataFrame
) -> dict:
    """
    How well the three work-level files reconcile.

    Unmatched records are reported rather than dropped. A completed work with no
    sanction record is itself a finding, not a nuisance.
    """
    s_ids = set(sanctioned["work_id"].dropna())
    c_ids = set(completed["work_id"].dropna())
    e_ids = set(expenditure["work_id"].dropna())

    return {
        "sanctioned_records": int(len(sanctioned)),
        "completed_records": int(len(completed)),
        "expenditure_payment_records": int(len(expenditure)),
        "sanctioned_distinct_ids": len(s_ids),
        "completed_distinct_ids": len(c_ids),
        "expenditure_distinct_works": len(e_ids),
        "completed_matched_to_sanctioned": len(c_ids & s_ids),
        "completed_unmatched": len(c_ids - s_ids),
        "expenditure_matched_to_sanctioned": len(e_ids & s_ids),
        "expenditure_unmatched": len(e_ids - s_ids),
        "works_with_both_completion_and_payments": len(c_ids & e_ids),
        "duplicate_ids_in_sanctioned": int(sanctioned["work_id"].duplicated().sum()),
        "duplicate_ids_in_completed": int(completed["work_id"].duplicated().sum()),
        "match_rate_completed_pct": round(100 * len(c_ids & s_ids) / max(len(c_ids), 1), 2),
        "match_rate_expenditure_pct": round(
            100 * len(e_ids & s_ids) / max(len(e_ids), 1), 2
        ),
    }


def date_consistency(works: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """Date-ordering and range checks over the unified dataset."""

    def count(mask) -> int:
        return int(pd.Series(mask).fillna(False).sum())

    return {
        "sanction_before_recommendation": count(
            works["sanction_date"] < works["recommended_date"]
        ),
        "completion_before_sanction": count(
            works["completion_date"] < works["sanction_date"]
        ),
        "first_payment_before_sanction": count(
            works["first_payment_date"] < works["sanction_date"]
        ),
        "sanction_date_in_future": count(works["sanction_date"] > as_of),
        "completion_date_in_future": count(works["completion_date"] > as_of),
        "missing_sanction_date": count(works["sanction_date"].isna()),
        "completed_status_without_completion_date": count(
            works["work_status"].eq("Work Completed") & works["completion_date"].isna()
        ),
        "completion_date_without_completed_status": count(
            works["completion_date"].notna() & ~works["work_status"].eq("Work Completed")
        ),
    }


def amount_consistency(works: pd.DataFrame) -> dict:
    """Financial sanity checks over the unified dataset."""

    def count(mask) -> int:
        return int(pd.Series(mask).fillna(False).sum())

    has_both = works["total_expenditure"].notna() & works["sanction_amount"].notna()
    return {
        "missing_sanction_amount": count(works["sanction_amount"].isna()),
        "zero_or_negative_sanction": count(works["sanction_amount"] <= 0),
        "works_with_expenditure": count(works["total_expenditure"].notna()),
        "expenditure_exceeds_sanction": count(
            has_both & (works["total_expenditure"] > works["sanction_amount"])
        ),
        "completed_without_any_payment": count(
            works["completion_date"].notna() & works["total_expenditure"].isna()
        ),
        "single_payment_exceeds_sanction": count(
            works["max_single_payment"].notna()
            & (works["max_single_payment"] > works["sanction_amount"])
        ),
        "median_expenditure_ratio": (
            round(float(np.nanmedian(works.loc[has_both, "expenditure_ratio"])), 3)
            if count(has_both)
            else None
        ),
    }
