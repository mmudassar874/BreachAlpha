"""Optimized preprocessing pipeline with streaming, validation, and user controls."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from .ticker_resolver import resolve_ticker

logger = logging.getLogger(__name__)

COLUMN_ALIASES = {
    "company": "company_name", "company_name": "company_name", "name": "company_name",
    "organization": "company_name", "org": "company_name", "entity": "company_name",
    "covered_entity": "company_name", "name_of_covered_entity": "company_name",
    "breached_entity": "company_name",
    "breach_date": "breach_date", "date": "breach_date", "date_of_breach": "breach_date",
    "incident_date": "breach_date", "disclosure_date": "breach_date",
    "discovered_date": "breach_date", "breachdate": "breach_date",
    "records": "records_affected", "records_affected": "records_affected",
    "individuals_affected": "records_affected", "people_affected": "records_affected",
    "users_affected": "records_affected", "pwn_count": "records_affected",
    "pwncount": "records_affected", "affected_count": "records_affected",
    "num_records": "records_affected", "number_of_individuals": "records_affected",
    "breach_type": "breach_type", "type": "breach_type", "type_of_breach": "breach_type",
    "attack_type": "breach_type", "incident_type": "breach_type", "category": "breach_type",
    "ticker": "ticker", "stock_ticker": "ticker", "symbol": "ticker", "ticker_symbol": "ticker",
}

REQUIRED_COLUMNS = {"company_name", "breach_date"}
DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S",
    "%m-%d-%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y", "%Y/%m/%d",
]


@dataclass
class PreprocessConfig:
    """User-configurable preprocessing options."""
    column_mapping: dict[str, str] = field(default_factory=dict)
    date_format: Optional[str] = None
    records_threshold: int = 1000
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    ticker_overrides: dict[str, str] = field(default_factory=dict)
    skip_ticker_resolution: bool = False
    max_rows: Optional[int] = None


@dataclass
class PreprocessingResult:
    """Result of preprocessing an uploaded dataset."""
    success: bool
    original_rows: int
    cleaned_rows: int
    columns_detected: list[str]
    column_mapping: dict[str, str]
    ticker_resolution_rate: float
    preview: list[dict]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    df: Optional[pd.DataFrame] = None
    validation: Optional[dict] = None


def normalize_column_name(col: str) -> str:
    normalized = col.lower().strip()
    normalized = re.sub(r"[\s\-]+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def map_columns(df: pd.DataFrame, user_mapping: dict[str, str] = None) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """Map column names with user override support."""
    mapping = {}
    warnings = []

    for col in df.columns:
        # Check user mapping first
        if user_mapping and col in user_mapping:
            canonical = user_mapping[col]
            if canonical not in mapping.values():
                mapping[col] = canonical
            continue

        normalized = normalize_column_name(col)
        if normalized in COLUMN_ALIASES:
            canonical = COLUMN_ALIASES[normalized]
            if canonical not in mapping.values():
                mapping[col] = canonical
        else:
            warnings.append(f"Unknown column '{col}' — kept as-is")

    renamed = df.rename(columns=mapping)
    return renamed, mapping, warnings


def parse_dates_robust(series: pd.Series, preferred_format: str = None) -> pd.Series:
    """Parse dates with optional preferred format."""
    if preferred_format:
        try:
            result = pd.to_datetime(series, format=preferred_format, errors="coerce")
            if result.notna().sum() / len(series) > 0.5:
                return result
        except Exception:
            pass

    for fmt in DATE_FORMATS:
        try:
            result = pd.to_datetime(series, format=fmt, errors="coerce")
            if result.notna().sum() / len(series) > 0.5:
                return result
        except Exception:
            continue

    return pd.to_datetime(series, format="mixed", errors="coerce")


def parse_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    cleaned = series.astype(str).str.replace(r"[\$,]", "", regex=True).str.strip()
    cleaned = cleaned.str.replace(r"[Kk]$", "e3", regex=True).str.replace(r"[Mm]$", "e6", regex=True).str.replace(r"[Bb]$", "e9", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def validate_dataset(df: pd.DataFrame) -> dict:
    """Validate dataset quality and return validation report."""
    report = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "missing_company": int(df["company_name"].isna().sum()) if "company_name" in df.columns else len(df),
        "missing_date": int(df["breach_date"].isna().sum()) if "breach_date" in df.columns else len(df),
        "missing_records": int(df["records_affected"].isna().sum()) if "records_affected" in df.columns else 0,
        "date_range": None,
        "unique_companies": df["company_name"].nunique() if "company_name" in df.columns else 0,
        "quality_score": 0.0,
    }

    if "breach_date" in df.columns and df["breach_date"].notna().any():
        dates = df["breach_date"].dropna()
        report["date_range"] = [str(dates.min())[:10], str(dates.max())[:10]]

    # Quality score: based on completeness
    completeness = 1.0
    if "company_name" in df.columns:
        completeness *= df["company_name"].notna().mean()
    if "breach_date" in df.columns:
        completeness *= df["breach_date"].notna().mean()
    if "records_affected" in df.columns:
        completeness *= max(0.5, df["records_affected"].notna().mean())

    report["quality_score"] = round(completeness, 3)
    return report


def resolve_tickers(df: pd.DataFrame, overrides: dict[str, str] = None, skip: bool = False) -> tuple[pd.DataFrame, float]:
    """Resolve tickers with user override support.

    Uses ThreadPoolExecutor for parallel ticker resolution when rows > 5.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .ticker_resolver import is_likely_ticker

    if skip:
        return df, 0.0

    has_ticker_col = "ticker" in df.columns
    has_company_col = "company_name" in df.columns

    def _resolve_row(idx, row):
        ticker = row.get("ticker") if has_ticker_col else None

        if ticker is None or (isinstance(ticker, str) and not ticker.strip()) or (isinstance(ticker, float) and pd.isna(ticker)):
            ticker = None
        elif isinstance(ticker, str) and not is_likely_ticker(ticker.strip()):
            ticker = None

        if ticker is None and has_company_col:
            name_str = str(row.get("company_name", ""))
            if overrides and name_str.lower() in {k.lower(): v for k, v in overrides.items()}:
                ticker = next(v for k, v in overrides.items() if k.lower() == name_str.lower())
            else:
                ticker = resolve_ticker(name_str)

        return idx, ticker if ticker else None

    tickers_out = [None] * len(df)

    if len(df) > 5:
        # Parallel resolution for larger datasets
        with ThreadPoolExecutor(max_workers=min(8, len(df))) as pool:
            futures = {
                pool.submit(_resolve_row, idx, row): idx
                for idx, row in df.iterrows()
            }
            for future in as_completed(futures):
                idx, ticker = future.result()
                tickers_out[idx] = ticker
    else:
        # Sequential for small datasets (avoids thread overhead)
        for idx, row in df.iterrows():
            _, ticker = _resolve_row(idx, row)
            tickers_out[idx] = ticker

    df["ticker"] = tickers_out
    resolved = sum(1 for t in tickers_out if t is not None)
    return df, resolved / len(df) if len(df) > 0 else 0


def _sanitize_formula_injection(df: pd.DataFrame) -> None:
    """Prefix formula characters in string columns to prevent CSV injection.

    Cells starting with =, +, -, @ are interpreted as formulas by Excel.
    Prefixing with a tab character neutralizes them while keeping the data readable.
    """
    formula_prefixes = ("=", "+", "-", "@")
    for col in df.columns:
        if df[col].dtype == object:  # string columns only
            mask = df[col].astype(str).str.strip().str.startswith(formula_prefixes, na=False)
            if mask.any():
                df.loc[mask, col] = "\t" + df.loc[mask, col].astype(str)


def preprocess_dataset(
    file_path: str | Path,
    config: PreprocessConfig = None,
) -> PreprocessingResult:
    """Full preprocessing pipeline with user controls.

    Steps:
    1. Read file (CSV/XLSX/Excel/TSV)
    2. Apply user column mapping or auto-detect
    3. Parse dates and numeric columns
    4. Filter by date range and record threshold
    5. Resolve stock tickers
    6. Validate dataset quality
    7. Return cleaned dataset + metadata
    """
    if config is None:
        config = PreprocessConfig()

    path = Path(file_path)
    errors = []
    warnings = []

    # Step 1: Read file
    try:
        suffix = path.suffix.lower()
        read_kwargs = {}

        if suffix == ".csv":
            # Detect encoding
            try:
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip", nrows=config.max_rows)
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip", nrows=config.max_rows)
        elif suffix in (".xlsx", ".xls"):
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            df = pd.read_excel(path, engine=engine, nrows=config.max_rows)
        elif suffix == ".tsv":
            df = pd.read_csv(path, sep="\t", encoding="utf-8", on_bad_lines="skip", nrows=config.max_rows)
        else:
            return PreprocessingResult(
                success=False, original_rows=0, cleaned_rows=0,
                columns_detected=[], column_mapping={}, ticker_resolution_rate=0,
                preview=[], errors=[f"Unsupported file format: {suffix}"],
            )
    except Exception as e:
        return PreprocessingResult(
            success=False, original_rows=0, cleaned_rows=0,
            columns_detected=[], column_mapping={}, ticker_resolution_rate=0,
            preview=[], errors=[f"Failed to read file: {e}"],
        )

    original_rows = len(df)
    columns_detected = list(df.columns)

    if original_rows == 0:
        return PreprocessingResult(
            success=False, original_rows=0, cleaned_rows=0,
            columns_detected=columns_detected, column_mapping={},
            ticker_resolution_rate=0, preview=[], errors=["File is empty"],
        )

    # Sanitize CSV formula injection: prefix formula characters to prevent
    # Excel/Google Sheets from executing them as formulas
    _sanitize_formula_injection(df)

    # Step 2: Map columns
    df, column_mapping, map_warnings = map_columns(df, config.column_mapping)
    warnings.extend(map_warnings)

    # Step 3: Parse dates
    if "breach_date" in df.columns:
        df["breach_date"] = parse_dates_robust(df["breach_date"], config.date_format)
        null_dates = df["breach_date"].isna().sum()
        if null_dates > 0:
            warnings.append(f"{null_dates} rows have unparseable dates — dropped")
            df = df.dropna(subset=["breach_date"])

    # Step 4: Parse numeric columns
    if "records_affected" in df.columns:
        df["records_affected"] = parse_numeric(df["records_affected"])
        df["records_affected"] = df["records_affected"].fillna(0).astype(int)

    # Step 5: Filter by record threshold
    if "records_affected" in df.columns and config.records_threshold > 0:
        before = len(df)
        df = df[df["records_affected"] >= config.records_threshold]
        filtered = before - len(df)
        if filtered > 0:
            warnings.append(f"Filtered {filtered} rows with < {config.records_threshold} records")

    # Step 6: Filter by date range
    if "breach_date" in df.columns:
        if config.start_date:
            df = df[df["breach_date"] >= pd.Timestamp(config.start_date)]
        if config.end_date:
            df = df[df["breach_date"] <= pd.Timestamp(config.end_date)]

    # Step 7: Resolve tickers
    df, ticker_rate = resolve_tickers(df, config.ticker_overrides, config.skip_ticker_resolution)
    unresolved = (df["ticker"].isna() | (df["ticker"] == "")).sum() if "ticker" in df.columns else 0
    if unresolved > 0:
        warnings.append(f"{unresolved} companies could not be mapped to stock tickers")

    # Step 8: Final cleanup
    if "company_name" in df.columns:
        df = df.dropna(subset=["company_name"])
    if "breach_date" in df.columns:
        df = df[df["breach_date"].notna()]

    cleaned_rows = len(df)

    # Step 9: Validate
    validation = validate_dataset(df)

    # Generate preview
    preview_cols = [c for c in ["company_name", "breach_date", "records_affected", "breach_type", "ticker"] if c in df.columns]
    preview_df = df[preview_cols].head(10) if preview_cols else df.head(10)
    preview = preview_df.fillna("").to_dict(orient="records")
    for row in preview:
        for k, v in row.items():
            if isinstance(v, pd.Timestamp):
                row[k] = v.strftime("%Y-%m-%d")

    success = cleaned_rows > 0 and "company_name" in df.columns and "breach_date" in df.columns

    if not success:
        if "company_name" not in df.columns:
            errors.append("No company name column detected. Expected: company, name, entity, organization")
        if "breach_date" not in df.columns:
            errors.append("No breach date column detected. Expected: date, breach_date, incident_date")

    return PreprocessingResult(
        success=success,
        original_rows=original_rows,
        cleaned_rows=cleaned_rows,
        columns_detected=columns_detected,
        column_mapping=column_mapping,
        ticker_resolution_rate=ticker_rate,
        preview=preview,
        errors=errors,
        warnings=warnings,
        df=df if success else None,
        validation=validation,
    )
