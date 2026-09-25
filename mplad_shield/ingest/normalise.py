"""
Converts raw export strings into typed, comparable values.

Two rules govern everything here. Originals are never overwritten -- a
normalised value is added alongside the source text, so a reviewer can always
see what the export actually said. And a value that cannot be parsed becomes
null and is counted, never a silent zero: a zero sanction amount would look like
a finding, while a null is correctly understood as missing.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .settings import DATE_FORMAT, MOJIBAKE_MIN_RATIO, WORK_ID_PATTERN

_WORK_ID_RE = re.compile(WORK_ID_PATTERN)
_IDA_PREFIX_RE = re.compile(r"^([^(]+)\(")
_MP_TENURE_RE = re.compile(r"\s*\((?:\d{4}-\d{2,4}|NaN-NaN)\)")
_NON_NUMERIC_RE = re.compile(r"[^0-9.\-]")


# ---------------------------------------------------------------- amounts


def parse_amount(series: pd.Series) -> pd.Series:
    """
    Parse a rupee column into floats.

    Handles the rupee sign, Indian digit grouping, stray whitespace and
    parenthesised negatives. Anything left unparseable becomes NaN so that
    `validate` can count and report it.
    """
    text = series.astype(str).str.strip()

    negative = text.str.match(r"^\(.*\)$", na=False)
    cleaned = text.str.replace(_NON_NUMERIC_RE, "", regex=True)
    cleaned = cleaned.replace({"": np.nan, "-": np.nan, ".": np.nan})

    values = pd.to_numeric(cleaned, errors="coerce")
    values = values.where(~negative, -values)
    return values


# ------------------------------------------------------------------ dates


def parse_date(series: pd.Series, fmt: str = DATE_FORMAT) -> pd.Series:
    """
    Parse a date column.

    The known format is tried first; anything it rejects gets a second pass with
    pandas' own inference, so an export that changes format part-way through
    degrades to partial parsing rather than losing the whole column.
    """
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format=fmt, errors="coerce")

    unparsed = parsed.isna() & text.notna() & ~text.isin(["", "nan", "NaN", "None"])
    if unparsed.any():
        fallback = pd.to_datetime(text[unparsed], errors="coerce", dayfirst=True)
        parsed.loc[unparsed] = fallback

    return parsed


# -------------------------------------------------------------- work IDs


def extract_work_id(series: pd.Series) -> pd.Series:
    """
    Pull the work ID out of a column.

    Works for both shapes in the supplied data: the sanctioned and completed
    exports prefix the ID to the description inside one `Work` column, while the
    expenditure export has a dedicated `Work ID` column. The same regex handles
    both, so no per-file special case is needed.
    """
    return series.astype(str).str.strip().str.extract(_WORK_ID_RE, expand=False)


def strip_work_id(series: pd.Series) -> pd.Series:
    """Return the descriptive remainder of a `Work` value, ID removed."""
    return (
        series.astype(str)
        .str.replace(_WORK_ID_RE, "", regex=True)
        .str.lstrip(" -\u2013\u2014")
        .str.strip()
        .replace({"": np.nan})
    )


# ------------------------------------------------------- derived entities


def extract_district(ida: pd.Series) -> pd.Series:
    """
    Take the district-like prefix from an IDA string.

    "SAMBHAL(DISTRICT MAGISTRAE BHIMNAGAR SAMBHAL_IDA)" yields "Sambhal".

    This is an inference, not a labelled field. The raw IDA string is always
    kept alongside, and the derived column is documented as "meaning requires
    confirmation" so it is never mistaken for an authoritative district code.
    """
    prefix = ida.astype(str).str.extract(_IDA_PREFIX_RE, expand=False)
    return prefix.str.strip().str.title().replace({"": np.nan, "Nan": np.nan})


def clean_mp_name(series: pd.Series) -> pd.Series:
    """
    Drop the tenure brackets from an MP name.

    "Shri Javed Ali Khan (2022-28) (2022-2028)" becomes "Shri Javed Ali Khan",
    so that the same person recorded with different tenure annotations across
    files groups together.
    """
    return (
        series.astype(str)
        .str.replace(_MP_TENURE_RE, "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan})
    )


# ------------------------------------------------------------------ text


def normalise_text(series: pd.Series) -> pd.Series:
    """Lowercased, whitespace- and punctuation-collapsed text for comparison."""
    return (
        series.astype(str)
        .str.lower()
        .str.replace(r"[^\w\s]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan})
    )


def is_mojibake(series: pd.Series, threshold: float = MOJIBAKE_MIN_RATIO) -> pd.Series:
    """
    Flag descriptions whose original script was lost during export.

    Several records read like "P.C.C ??? ?? ???????" -- Devanagari replaced by
    question marks. Left in, they would match each other on punctuation alone
    and manufacture duplicate findings, so similarity skips them.
    """
    text = series.fillna("").astype(str)
    lengths = text.str.len().replace(0, np.nan)
    ratio = text.str.count(r"\?") / lengths
    return (ratio.fillna(0) >= threshold) & (text.str.len() > 0)
