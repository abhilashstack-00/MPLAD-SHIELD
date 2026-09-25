"""
Reads the supplied MPLADS workbooks into DataFrames, with provenance attached.

Nothing here interprets the data. The job of this module is to get bytes off
disk correctly and to record where every row came from, so that any figure the
system later reports can be traced back to a file, a sheet and a row number.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .settings import EXCEL_ENGINE, HEADER_ROW


class IngestError(RuntimeError):
    """Raised when a source file cannot be read or is not shaped as expected."""


def read_workbook(
    path: str | Path,
    *,
    header_row: int = HEADER_ROW,
    sheet: str | int = 0,
) -> pd.DataFrame:
    """
    Load one sheet of an MPLADS export.

    Everything is read as string. The exports mix rupee formatting, stray total
    rows and inconsistent blanks into otherwise numeric columns, and letting
    pandas infer types would silently coerce those into NaN before anyone could
    see and report them. Parsing happens later, deliberately, in `normalise`.
    """
    path = Path(path)
    if not path.exists():
        raise IngestError(f"Source file not found: {path}")

    try:
        frame = pd.read_excel(
            path,
            engine=EXCEL_ENGINE,
            sheet_name=sheet,
            header=header_row,
            dtype=str,
        )
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise IngestError(
            "The calamine engine is required to read these exports. "
            "Install it with `pip install python-calamine`. openpyxl cannot "
            "open them: the files carry a malformed stylesheet."
        ) from exc
    except Exception as exc:
        raise IngestError(f"Could not read {path.name}: {exc}") from exc

    if frame.empty:
        raise IngestError(f"{path.name} contains no rows below the header")

    frame.columns = [str(c).strip() for c in frame.columns]

    # Source row number in the original spreadsheet, 1-based as a human would
    # count it in Excel: header row, plus one for the title row above it.
    frame["source_row"] = range(header_row + 2, header_row + 2 + len(frame))
    frame["source_file"] = path.name
    frame["source_sheet"] = str(sheet)
    frame["ingested_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    return frame


def sheet_names(path: str | Path) -> list[str]:
    """List the sheets in a workbook without loading their contents."""
    try:
        from python_calamine import CalamineWorkbook

        return list(CalamineWorkbook.from_path(str(path)).sheet_names)
    except Exception as exc:  # pragma: no cover - diagnostic helper
        raise IngestError(f"Could not list sheets in {Path(path).name}: {exc}") from exc


def require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    """
    Fail loudly and by name when an export is missing a column.

    A missing column surfacing later as a KeyError inside a detector is far
    harder to diagnose than one reported here against the file it came from.
    """
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise IngestError(
            f"{label} is missing expected column(s): {', '.join(missing)}. "
            f"Found: {', '.join(frame.columns[:15])}"
        )
