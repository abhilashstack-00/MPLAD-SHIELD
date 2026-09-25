"""
Ingestion settings.

Everything here is a processing choice rather than an MPLADS rule. Values are
gathered in one place so they can be changed without touching ingestion logic,
and so a reviewer can see exactly what the pipeline assumed.
"""

from dataclasses import dataclass, field
from datetime import date


# The supplied exports put the report title in row 0 and column headers in row 1.
HEADER_ROW = 1

# openpyxl cannot open these files: the exports carry a malformed stylesheet and
# raise `TypeError: Fill() takes no arguments`, which also breaks pandas at its
# default engine. calamine reads them without complaint.
EXCEL_ENGINE = "calamine"

# Dates in every supplied file use this single format.
DATE_FORMAT = "%d-%b-%Y"

# Work IDs look like WS/MP187/2023-2024/1199. In the sanctioned and completed
# exports the ID is prefixed to the description inside one `Work` column; the
# expenditure export has a dedicated `Work ID` column.
WORK_ID_PATTERN = r"(WS/MP\d+/\d{4}-\d{4}/\d+)"

# A single payment larger than this is treated as implausible and quarantined
# rather than scored. The supplied expenditure file contains one payment of
# about Rs 1,276 crore against a maximum sanction anywhere of Rs 7.35 crore,
# which is a total row or a data-entry error, not a real disbursement.
IMPLAUSIBLE_PAYMENT_CEILING = 50_00_00_000  # Rs 50 crore

# Descriptions whose characters are mostly replacement marks lost their original
# script during export ("P.C.C ??? ?? ???????"). They are kept, but excluded
# from text similarity so they do not match each other on punctuation.
MOJIBAKE_MIN_RATIO = 0.30


@dataclass
class IngestConfig:
    """Per-run ingestion configuration, recorded in the output for provenance."""

    # Works still open are aged against this date. Exposed because a screening
    # result changes meaning entirely depending on when "now" is.
    as_of_date: date = date(2026, 9, 24)
    data_mode: str = "official_export"
    source_label: str = "MPLADS portal export supplied by user"
    config_version: str = "v2-ingest-1"
    quarantine_implausible_payments: bool = True
    files: dict = field(
        default_factory=lambda: {
            "sanctioned": "Works_Sanctioned.xlsx",
            "completed": "Works_Completed.xlsx",
            "expenditure": "Expenditure_on_Completed_and_On-going_Works_as_on_Date.xlsx",
            "allocation": "Allocated_Limit_for_Honble_MPs.xlsx",
            "recommended": "Works_Recommended.xlsx",
        }
    )
