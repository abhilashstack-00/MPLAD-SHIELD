"""
Generates a synthetic MPLADS project register with ground-truth irregularity
labels.

The point of this module is validation, not realism for its own sake. Because
every injected irregularity is labelled, the engine's precision and recall can
be measured instead of asserted -- which is what turns "our model detects
anomalies" into a number a judge or an auditor can check.

The schema mirrors what the MPLADS portal actually publishes per work, so
swapping this generator for a real CSV loader is a column mapping, not a
rewrite. See `REQUIRED_COLUMNS` for the contract the rest of the engine expects.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import EXPECTED_DURATION_DAYS, INADMISSIBLE_CATEGORIES, SECTORS

REQUIRED_COLUMNS = [
    "project_id",
    "state",
    "district",
    "block",
    "latitude",
    "longitude",
    "mp_name",
    "constituency",
    "sector",
    "work_category",
    "work_description",
    "implementing_agency",
    "sanction_date",
    "expected_completion_date",
    "actual_completion_date",
    "sanctioned_cost",
    "revised_cost",
    "expenditure",
    "physical_progress_pct",
    "status",
]

# District centroids, roughly placed. Coordinates only need to be internally
# consistent for the proximity logic to be exercised.
DISTRICTS = [
    ("Maharashtra", "Pune", 18.52, 73.86),
    ("Maharashtra", "Nashik", 19.99, 73.79),
    ("Maharashtra", "Nagpur", 21.15, 79.09),
    ("Karnataka", "Belagavi", 15.85, 74.50),
    ("Karnataka", "Mysuru", 12.30, 76.64),
    ("Uttar Pradesh", "Varanasi", 25.32, 82.97),
    ("Uttar Pradesh", "Gorakhpur", 26.76, 83.37),
    ("Bihar", "Muzaffarpur", 26.12, 85.39),
    ("Bihar", "Gaya", 24.80, 85.00),
    ("Rajasthan", "Ajmer", 26.45, 74.64),
    ("Tamil Nadu", "Madurai", 9.93, 78.12),
    ("Odisha", "Cuttack", 20.46, 85.88),
]

AGENCY_TYPES = [
    "Zilla Parishad",
    "PWD Division",
    "Municipal Council",
    "Gram Panchayat",
    "Rural Water Supply Dept",
    "District Rural Development Agency",
    "Block Development Office",
]

VILLAGE_STEMS = [
    "Rampur", "Bhilwada", "Kesarpur", "Manjari", "Sultanpur", "Narsinghpur",
    "Chandwad", "Kolhewadi", "Baragaon", "Dhanora", "Jamalpur", "Sirsi",
    "Tikamgarh", "Palodi", "Akola", "Bandhpur", "Hirapur", "Devgaon",
    "Kanhaipur", "Mahuli", "Sonbarsa", "Talegaon", "Pipariya", "Amravati",
    "Chikhali", "Ratanpur", "Basantpur", "Karanja", "Gopalpur", "Nandgaon",
    "Shivpuri", "Jalalpur", "Umred", "Barhi", "Kadegaon", "Lakhanpur",
    "Naugachia", "Sindkhed", "Bhagwanpur", "Wadgaon", "Harpur", "Selu",
    "Pathardi", "Raibag", "Mudhol", "Tirora", "Ashti", "Bilaspur",
    "Chausa", "Dhamnod", "Ekma", "Garhwa", "Hingna", "Isagarh",
    "Jhalod", "Kurduwadi", "Loni", "Mangrul", "Nimbhora", "Osmanpur",
]

LANDMARKS = [
    "the primary school", "the main bazaar", "the bus stand", "the PHC",
    "the panchayat office", "the temple crossing", "the canal bridge",
    "the block office", "the railway gate", "the water tank",
]

# Category-level typical unit costs in rupees (median, spread).
COST_PROFILE = {
    "CC road": (18_00_000, 0.45),
    "Culvert / bridge": (42_00_000, 0.40),
    "Drainage": (14_00_000, 0.45),
    "Toilet block": (7_00_000, 0.35),
    "Drinking water": (11_00_000, 0.40),
    "School building": (55_00_000, 0.35),
    "Library": (24_00_000, 0.40),
    "Anganwadi centre": (19_00_000, 0.35),
    "Health sub-centre": (62_00_000, 0.35),
    "Community hall": (36_00_000, 0.40),
    "Playground": (16_00_000, 0.45),
    "Solar street light": (9_00_000, 0.50),
}

ANOMALY_TYPES = [
    "cost_inflation",
    "excessive_delay",
    "expenditure_mismatch",
    "duplicate_work",
    "inadmissible_work",
]


def _describe(rng: np.random.Generator, category: str) -> str:
    """Build a work description in the register's usual phrasing."""
    village = rng.choice(VILLAGE_STEMS)
    if category in ("CC road", "Drainage"):
        a, b = rng.choice(LANDMARKS, size=2, replace=False)
        return f"Construction of {category.lower()} from {a} to {b} in {village}"
    if category == "Solar street light":
        n = int(rng.integers(8, 40))
        return f"Installation of {n} solar street lights in {village} village"
    if category == "Drinking water":
        return f"Providing drinking water facility with borewell at {village}"
    if category == "Culvert / bridge":
        return f"Construction of culvert near {rng.choice(LANDMARKS)} at {village}"
    return f"Construction of {category.lower()} at {village} village"


def _near_duplicate(rng: np.random.Generator, description: str) -> str:
    """
    Reword a description the way a duplicate sanction usually differs: a synonym
    swap or a filler word, never a full rewrite. This is deliberately hard --
    exact-match dedup would miss all of these.
    """
    swaps = [
        ("Construction of", "Constrn. of"),
        ("Construction of", "Construction work of"),
        ("Installation of", "Instalation of"),
        ("Providing", "Provision of"),
        ("village", "gaon"),
        ("from", "starting from"),
        (" at ", " at village "),
    ]
    out = description
    for old, new in rng.permutation(np.array(swaps, dtype=object)).tolist()[:2]:
        if old in out:
            out = out.replace(old, new, 1)
    return out


def generate(n: int = 1200, seed: int = 42, anomaly_rate: float = 0.07) -> pd.DataFrame:
    """
    Produce `n` works, of which roughly `anomaly_rate` carry an injected
    irregularity. Returns a DataFrame with `REQUIRED_COLUMNS` plus the
    ground-truth columns `is_anomaly` and `anomaly_type`.
    """
    rng = np.random.default_rng(seed)
    categories = list(COST_PROFILE)

    rows = []
    for i in range(n):
        state, district, lat0, lon0 = DISTRICTS[int(rng.integers(len(DISTRICTS)))]
        category = str(rng.choice(categories))
        median_cost, spread = COST_PROFILE[category]

        # Lognormal keeps costs positive and right-skewed, like real tenders.
        cost = float(median_cost * rng.lognormal(mean=0.0, sigma=spread))
        cost = round(cost, -3)

        sanction = pd.Timestamp("2023-01-01") + pd.Timedelta(
            days=int(rng.integers(0, 730))
        )
        expected_days = EXPECTED_DURATION_DAYS[category]
        expected_completion = sanction + pd.Timedelta(days=expected_days)

        # Most works run modestly late; a minority finish early.
        overrun_frac = float(rng.normal(0.12, 0.28))
        overrun_frac = max(overrun_frac, -0.25)
        actual_days = int(expected_days * (1 + overrun_frac))

        progress = float(np.clip(rng.normal(72, 26), 0, 100))
        # Money spent tracks physical progress with ordinary slippage.
        spend_ratio = float(np.clip(progress / 100 + rng.normal(0.02, 0.09), 0, 1.15))

        rows.append(
            {
                "project_id": f"MPLADS-{sanction.year}-{i:05d}",
                "state": state,
                "district": district,
                "block": f"{district} Block-{int(rng.integers(1, 7))}",
                "latitude": lat0 + float(rng.normal(0, 0.22)),
                "longitude": lon0 + float(rng.normal(0, 0.22)),
                "mp_name": f"MP {district}",
                "constituency": f"{district} Lok Sabha",
                "sector": SECTORS[category],
                "work_category": category,
                "work_description": _describe(rng, category),
                "implementing_agency": f"{rng.choice(AGENCY_TYPES)}, {district}",
                "sanction_date": sanction,
                "expected_completion_date": expected_completion,
                "actual_completion_date": sanction + pd.Timedelta(days=actual_days),
                "sanctioned_cost": cost,
                "revised_cost": cost,
                "expenditure": round(cost * spend_ratio, -2),
                "physical_progress_pct": round(progress, 1),
                "status": "Completed" if progress >= 99.5 else "In progress",
                "is_anomaly": False,
                "anomaly_type": "",
            }
        )

    df = pd.DataFrame(rows)
    df = _inject_anomalies(df, rng, anomaly_rate)
    df = _inject_missingness(df, rng)
    return df


def _inject_anomalies(
    df: pd.DataFrame, rng: np.random.Generator, rate: float
) -> pd.DataFrame:
    """Overwrite a random subset of works with labelled irregularities."""
    n_bad = max(1, int(len(df) * rate))
    victims = rng.choice(len(df), size=n_bad, replace=False)

    for pos, idx in enumerate(victims):
        kind = ANOMALY_TYPES[pos % len(ANOMALY_TYPES)]
        row = df.iloc[idx]

        if kind == "cost_inflation":
            # Sanctioned far above peers, then revised upward again.
            factor = float(rng.uniform(2.6, 4.5))
            new_cost = round(row["sanctioned_cost"] * factor, -3)
            df.at[idx, "sanctioned_cost"] = new_cost
            df.at[idx, "revised_cost"] = round(new_cost * rng.uniform(1.15, 1.45), -3)
            df.at[idx, "expenditure"] = round(
                new_cost * float(np.clip(row["physical_progress_pct"] / 100, 0, 1)), -2
            )

        elif kind == "excessive_delay":
            expected_days = EXPECTED_DURATION_DAYS[row["work_category"]]
            blown = int(expected_days * rng.uniform(2.2, 4.0))
            df.at[idx, "actual_completion_date"] = row["sanction_date"] + pd.Timedelta(
                days=blown
            )
            df.at[idx, "physical_progress_pct"] = round(float(rng.uniform(15, 55)), 1)
            df.at[idx, "status"] = "In progress"

        elif kind == "expenditure_mismatch":
            # Money almost fully drawn against very little work on the ground.
            progress = float(rng.uniform(8, 30))
            df.at[idx, "physical_progress_pct"] = round(progress, 1)
            df.at[idx, "expenditure"] = round(
                row["sanctioned_cost"] * float(rng.uniform(0.82, 0.99)), -2
            )
            df.at[idx, "status"] = "In progress"

        elif kind == "duplicate_work":
            # Clone an existing work in the same district: same category, near
            # location, reworded description, similar cost.
            same_district = df.index[
                (df["district"] == row["district"])
                & (df["work_category"] == row["work_category"])
                & (df.index != idx)
            ]
            if len(same_district) == 0:
                df.at[idx, "anomaly_type"] = ""
                continue
            src = df.loc[int(rng.choice(same_district))]
            df.at[idx, "work_description"] = _near_duplicate(rng, src["work_description"])
            df.at[idx, "latitude"] = src["latitude"] + float(rng.normal(0, 0.012))
            df.at[idx, "longitude"] = src["longitude"] + float(rng.normal(0, 0.012))
            df.at[idx, "sanctioned_cost"] = round(
                src["sanctioned_cost"] * float(rng.uniform(0.93, 1.07)), -3
            )
            df.at[idx, "implementing_agency"] = src["implementing_agency"]

        elif kind == "inadmissible_work":
            df.at[idx, "work_category"] = str(rng.choice(INADMISSIBLE_CATEGORIES))
            df.at[idx, "sector"] = "Other"
            df.at[idx, "work_description"] = (
                f"{df.at[idx, 'work_category']} at "
                f"{rng.choice(VILLAGE_STEMS)} village"
            )

        df.at[idx, "is_anomaly"] = True
        df.at[idx, "anomaly_type"] = kind

    # A handful of works also breach the single-work ceiling outright.
    for idx in rng.choice(len(df), size=max(1, int(len(df) * 0.006)), replace=False):
        df.at[idx, "sanctioned_cost"] = float(rng.uniform(1.1e7, 1.8e7))
        df.at[idx, "revised_cost"] = df.at[idx, "sanctioned_cost"]
        df.at[idx, "is_anomaly"] = True
        if not df.at[idx, "anomaly_type"]:
            df.at[idx, "anomaly_type"] = "inadmissible_work"

    return df


def _inject_missingness(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """
    Blank out a few fields at random. Real registers are patchy, and the
    confidence score is meaningless if it never has anything to react to.
    """
    for col, rate in [
        ("physical_progress_pct", 0.04),
        ("implementing_agency", 0.02),
        ("latitude", 0.02),
        ("expenditure", 0.02),
    ]:
        mask = rng.random(len(df)) < rate
        df.loc[mask, col] = np.nan
        if col == "latitude":
            df.loc[mask, "longitude"] = np.nan
    return df
