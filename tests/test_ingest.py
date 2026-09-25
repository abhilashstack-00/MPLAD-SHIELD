"""
Tests for the ingestion layer.

These matter more than the synthetic-engine tests, because this is the code
that reads real government exports and every figure on the dashboard descends
from it. The fixtures build small workbooks shaped like the real MPLADS exports
— title in row 0, headers in row 1, work IDs prefixed to descriptions, a Grand
Total row at the bottom — so the tests exercise the parsing rather than
depending on 39 MB of data being present.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mplad_shield.ingest import build
from mplad_shield.ingest import normalise as nz
from mplad_shield.ingest import validate as vd
from mplad_shield.ingest.readers import IngestError, read_workbook, require_columns
from mplad_shield.ingest.settings import IngestConfig

REAL_DATA = Path("data/raw")


def _write(path: Path, title: str, header: list[str], rows: list[list]) -> None:
    """Write a workbook shaped like an MPLADS export: title row, then headers."""
    frame = pd.DataFrame([header] + [[str(c) for c in r] for r in rows])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([[title]]).to_excel(writer, index=False, header=False, startrow=0)
        frame.to_excel(writer, index=False, header=False, startrow=1)


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    """A miniature four-file MPLADS export, including the traps in the real one."""
    _write(
        tmp_path / "Works_Sanctioned.xlsx",
        "Works Sanctioned Report",
        ["Sr. No.", "Work", "Work category", "State", "IDA",
         "Hon'ble Members of Parliament", "Elected/Nominated", "Work description",
         "Recommended date", "Sanction Date", "Sanction Amount ( ₹ )", "Work Status"],
        [
            [1, "WS/MP1/2023-2024/101-Construction of CC road", "Normal/Others", "Bihar",
             "GAYA(DISTRICT MAGISTRATE GAYA_IDA)", "Shri A B (2019-24)", "Elected",
             "Construction of CC road", "01-Apr-2023", "10-Apr-2023", "500000", "Sanction"],
            [2, "WS/MP1/2023-2024/102-Drainage work", "Normal/Others", "Bihar",
             "GAYA(DISTRICT MAGISTRATE GAYA_IDA)", "Shri A B (2019-24)", "Elected",
             "Drainage work near total market", "05-Apr-2023", "20-Apr-2023",
             "1,25,000", "Physical Inspection"],
            # Status column holding a total figure, as one real row does.
            [3, "WS/MP1/2023-2024/103-Toilet block", "Normal/Others", "Bihar",
             "GAYA(DISTRICT MAGISTRATE GAYA_IDA)", "Shri A B (2019-24)", "Elected",
             "Toilet block", "06-Apr-2023", "21-Apr-2023", "300000", "17629503056.99"],
            ["Grand Total", "", "", "", "", "", "", "", "", "", "925000", ""],
        ],
    )
    _write(
        tmp_path / "Works_Completed.xlsx",
        "Works Completed Report",
        ["Sr. No.", "Work", "Completion Date", "Amount Disbursed ( ₹ )"],
        [[1, "WS/MP1/2023-2024/101-Construction of CC road", "01-Sep-2023", "495000"]],
    )
    _write(
        tmp_path / "Expenditure_on_Completed_and_On-going_Works_as_on_Date.xlsx",
        "Expenditure Report",
        ["Sr. No.", "Work ID", "Work", "Vendor Name", "Expenditure Date",
         "Payment Status", "Fund Disbursed Amount ( ₹ )"],
        [
            [1, "WS/MP1/2023-2024/101", "Roads", "Vendor A", "01-Jun-2023",
             "Payment Success", "300000"],
            [2, "WS/MP1/2023-2024/101", "Roads", "Vendor A", "01-Aug-2023",
             "Payment Success", "195000"],
            [3, "WS/MP1/2023-2024/102", "Drainage", "Vendor B", "01-Jul-2023",
             "In-Progress", "60000"],
            # Implausible payment, as the real export carries.
            ["Grand Total", "WS/MP1/2023-2024/102", "Drainage", "", "",
             "Payment Success", "12761418099"],
        ],
    )
    _write(
        tmp_path / "Allocated_Limit_for_Honble_MPs.xlsx",
        "Allocated Limit Report",
        ["Sr. No.", "State", "Constituency", "Hon'ble Members of Parliaments",
         "Allocated AMOUNT ( ₹ )"],
        [
            [1, "Bihar", "Gaya", "Shri A B (2019-24)", "190289442"],
            ["Grand Total", "", "", "", "190289442"],
        ],
    )
    return tmp_path


# ------------------------------------------------------------- readers


def test_header_is_taken_from_the_second_row(export_dir: Path):
    frame = read_workbook(export_dir / "Works_Sanctioned.xlsx")
    assert "Sanction Amount ( ₹ )" in frame.columns
    assert "Works Sanctioned Report" not in frame.columns


def test_provenance_is_attached_to_every_row(export_dir: Path):
    frame = read_workbook(export_dir / "Works_Sanctioned.xlsx")
    for column in ("source_row", "source_file", "source_sheet", "ingested_at"):
        assert column in frame.columns
    assert frame["source_file"].iloc[0] == "Works_Sanctioned.xlsx"
    # Row numbers count as a human would in Excel: title, header, then data.
    assert frame["source_row"].iloc[0] == 3


def test_missing_file_raises_a_named_error(tmp_path: Path):
    with pytest.raises(IngestError, match="not found"):
        read_workbook(tmp_path / "nope.xlsx")


def test_missing_columns_are_reported_by_name(export_dir: Path):
    frame = read_workbook(export_dir / "Works_Completed.xlsx")
    with pytest.raises(IngestError, match="Nonexistent"):
        require_columns(frame, ["Sr. No.", "Nonexistent"], "Works Completed")


# ---------------------------------------------------------- normalise


@pytest.mark.parametrize(
    "raw,expected",
    [("500000", 500000.0), ("1,25,000", 125000.0), ("₹ 3,00,000", 300000.0),
     ("(5000)", -5000.0), ("", np.nan), ("n/a", np.nan)],
)
def test_amount_parsing(raw, expected):
    value = nz.parse_amount(pd.Series([raw])).iloc[0]
    assert np.isnan(value) if np.isnan(expected) else value == expected


def test_unparseable_amount_becomes_null_not_zero():
    """A zero would look like a finding; a null is correctly read as missing."""
    assert pd.isna(nz.parse_amount(pd.Series(["not a number"])).iloc[0])


def test_date_parsing_and_rejection():
    parsed = nz.parse_date(pd.Series(["01-Apr-2023", "rubbish"]))
    assert parsed.iloc[0] == pd.Timestamp("2023-04-01")
    assert pd.isna(parsed.iloc[1])


def test_work_id_extraction_from_both_shapes():
    embedded = nz.extract_work_id(pd.Series(["WS/MP187/2023-2024/1199-Construction of road"]))
    bare = nz.extract_work_id(pd.Series(["WS/MP18283/2025-2026/238259"]))
    assert embedded.iloc[0] == "WS/MP187/2023-2024/1199"
    assert bare.iloc[0] == "WS/MP18283/2025-2026/238259"


def test_stripping_the_id_leaves_the_description():
    remainder = nz.strip_work_id(pd.Series(["WS/MP1/2023-2024/101-Construction of CC road"]))
    assert remainder.iloc[0] == "Construction of CC road"


def test_district_is_taken_from_the_ida_prefix():
    district = nz.extract_district(pd.Series(["SAMBHAL(DISTRICT MAGISTRATE SAMBHAL_IDA)"]))
    assert district.iloc[0] == "Sambhal"


def test_mp_tenure_brackets_are_removed():
    cleaned = nz.clean_mp_name(pd.Series(["Shri Javed Ali Khan (2022-28) (2022-2028)"]))
    assert cleaned.iloc[0] == "Shri Javed Ali Khan"


def test_mojibake_descriptions_are_flagged():
    flags = nz.is_mojibake(pd.Series(["P.C.C ??? ?? ???????", "Construction of CC road"]))
    assert bool(flags.iloc[0]) and not bool(flags.iloc[1])


# ----------------------------------------------------------- validate


def test_summary_rows_are_detected_on_the_key_column_only():
    """
    A work whose description mentions "total" must not be mistaken for a footer.
    Scanning every column is how a genuine record gets deleted.
    """
    frame = pd.DataFrame(
        {"Sr. No.": ["1", "Grand Total"],
         "Work description": ["Drainage near total market", ""]}
    )
    flags = vd.find_summary_rows(frame, "Sr. No.")
    assert not bool(flags.iloc[0])
    assert bool(flags.iloc[1])


def test_quarantine_records_reason_and_source(export_dir: Path):
    result = build(export_dir, IngestConfig())
    quarantine = result["quarantine"]
    reasons = set(quarantine["quarantine_reason"])
    assert any("Summary or total row" in r for r in reasons)
    assert any("not a status" in r for r in reasons)
    assert "source_row" in quarantine.columns


def test_implausible_payment_is_quarantined_not_aggregated(export_dir: Path):
    result = build(export_dir, IngestConfig())
    payments = result["payments"]
    assert payments["payment_amount"].max() < 1e9


# ------------------------------------------------------ build_dataset


def test_sanctioned_is_the_spine_and_rows_are_not_multiplied(export_dir: Path):
    """
    Work 101 carries two payments. Joining payment rows directly would turn one
    sanctioned work into two and inflate every downstream count.
    """
    result = build(export_dir, IngestConfig())
    works = result["works"]
    # Four sanctioned rows in: one Grand Total and one whose Work Status holds
    # a total figure are both quarantined, leaving two genuine works. Work 101
    # carries two payments and must still be a single row.
    assert len(works) == 2
    assert works["work_id"].is_unique
    assert "WS/MP1/2023-2024/103" not in set(works["work_id"])


def test_payments_aggregate_correctly(export_dir: Path):
    works = build(export_dir, IngestConfig())["works"]
    row = works.loc[works["work_id"] == "WS/MP1/2023-2024/101"].iloc[0]
    assert row["total_expenditure"] == 495000
    assert row["payment_count"] == 2
    assert row["max_single_payment"] == 300000
    assert row["distinct_vendors"] == 1


def test_quarantined_work_is_absent_from_the_dataset(export_dir: Path):
    result = build(export_dir, IngestConfig())
    quarantined = set(result["quarantine"]["work_id"].dropna())
    assert "WS/MP1/2023-2024/103" in quarantined


def test_completion_joins_one_to_one(export_dir: Path):
    works = build(export_dir, IngestConfig())["works"]
    completed = works.loc[works["is_completed"]]
    assert len(completed) == 1
    assert completed.iloc[0]["work_id"] == "WS/MP1/2023-2024/101"


def test_matching_report_counts_are_reported(export_dir: Path):
    report = build(export_dir, IngestConfig())["reports"]["matching"]
    assert report["completed_unmatched"] == 0
    assert report["expenditure_unmatched"] == 0
    assert report["match_rate_completed_pct"] == 100.0


def test_allocation_grand_total_is_dropped(export_dir: Path):
    allocation = build(export_dir, IngestConfig())["allocation"]
    assert len(allocation) == 1


def test_as_of_date_is_configurable(export_dir: Path):
    from datetime import date

    early = build(export_dir, IngestConfig(as_of_date=date(2024, 1, 1)))["works"]
    late = build(export_dir, IngestConfig(as_of_date=date(2026, 1, 1)))["works"]
    open_work = "WS/MP1/2023-2024/102"
    early_age = early.loc[early["work_id"] == open_work, "days_sanction_to_reference"].iloc[0]
    late_age = late.loc[late["work_id"] == open_work, "days_sanction_to_reference"].iloc[0]
    assert late_age > early_age


# ------------------------------------------------- against real files


@pytest.mark.skipif(
    not (REAL_DATA / "Works_Sanctioned.xlsx").exists(),
    reason="real MPLADS exports not present in data/raw",
)
def test_real_exports_reconcile_completely():
    """The claim the whole project rests on, checked against the real files."""
    report = build(REAL_DATA, IngestConfig())["reports"]
    assert report["matching"]["completed_unmatched"] == 0
    assert report["matching"]["expenditure_unmatched"] == 0
    assert report["matching"]["duplicate_ids_in_sanctioned"] == 0
    assert report["coverage"]["works_total"] > 20000
