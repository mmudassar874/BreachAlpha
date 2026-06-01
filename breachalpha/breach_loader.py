"""Load and filter cybersecurity breach records from HIBP CSV data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Minimum threshold: ignore breaches with fewer than this many records
MIN_RECORDS_AFFECTED = 1000

# Columns that may contain dates to parse
DATE_COLS = ["BreachDate", "AddedDate", "ModifiedDate"]


def load_breaches(csv_path: str | Path) -> pd.DataFrame:
    """Load breach records from HIBP-format CSV.

    Expected columns from the Kaggle HIBP dataset:
      Name, Title, Domain, BreachDate, AddedDate, ModifiedDate,
      PwnCount, Description, IsVerified, IsFabricated, IsSensitive,
      IsRetired, IsSpamList, IsMalware, IsSubscriptionFree

    Args:
        csv_path: Path to the breach CSV file.

    Returns:
        DataFrame with cleaned breach records.

    Raises:
        FileNotFoundError: If csv_path does not exist.
        ValueError: If required columns are missing.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Breach data not found: {path}")

    # Check required columns before parsing dates
    peek = pd.read_csv(path, nrows=0)
    required_cols = {"Name", "BreachDate", "PwnCount"}
    missing = required_cols - set(peek.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Parse only date columns that actually exist
    parseable = [c for c in DATE_COLS if c in peek.columns]
    df = pd.read_csv(path, parse_dates=parseable)

    initial_count = len(df)
    logger.info("Loaded %d breach records from %s", initial_count, path.name)

    # Clean
    df = df.dropna(subset=["Name", "BreachDate"])
    df["PwnCount"] = pd.to_numeric(df["PwnCount"], errors="coerce").fillna(0).astype(int)
    df["Name"] = df["Name"].str.strip()

    # Filter out fabricated, spam, and malware entries
    for col in ["IsFabricated", "IsSpamList", "IsMalware"]:
        if col in df.columns:
            df = df[df[col] == False]  # noqa: E712

    # Filter small breaches
    df = df[df["PwnCount"] >= MIN_RECORDS_AFFECTED]

    # Deduplicate: keep most recent breach per company
    df = df.sort_values("BreachDate", ascending=False).drop_duplicates(subset="Name", keep="first")

    logger.info(
        "Filtered to %d breaches (from %d) with >= %d records",
        len(df), initial_count, MIN_RECORDS_AFFECTED,
    )
    return df.reset_index(drop=True)


def get_breach_summary(df: pd.DataFrame) -> dict:
    """Return summary statistics of the breach dataset."""
    if df.empty:
        return {
            "total_breaches": 0,
            "date_range": (None, None),
            "total_records_affected": 0,
            "median_records_affected": 0,
            "unique_companies": 0,
        }
    return {
        "total_breaches": len(df),
        "date_range": (
            df["BreachDate"].min().strftime("%Y-%m-%d"),
            df["BreachDate"].max().strftime("%Y-%m-%d"),
        ),
        "total_records_affected": int(df["PwnCount"].sum()),
        "median_records_affected": int(df["PwnCount"].median()),
        "unique_companies": df["Name"].nunique(),
    }
