"""Scoring service.

Centralizes the company resolution, data fetching, breach event construction,
and scoring pipeline used by multiple route handlers. Eliminates the duplicated
resolve→validate→fetch→build-event→compute-features→predict pattern.
"""

from __future__ import annotations

import asyncio
import logging
import re

import pandas as pd

from ..feature_engine import BreachEvent, compute_features, classify_severity, AnalysisConfig as FeatureConfig
from ..ticker_resolver import resolve_ticker, detect_benchmark, KNOWN_TICKERS
from ..stock_loader import fetch_stock_data, fetch_market_data
from ..schemas import FeatureDetail, ScoreResponse, AutoScoreResponse
from .model import get_or_train_model, score_features

logger = logging.getLogger(__name__)


def validate_ticker(ticker: str) -> str:
    """Validate and normalize a ticker symbol.

    Returns the cleaned uppercase ticker.

    Raises:
        ValueError: If ticker format is invalid.
    """
    import re as _re
    from ..core.constants import TICKER_RE
    cleaned = ticker.strip().upper()
    if not TICKER_RE.match(cleaned):
        raise ValueError(f"Invalid ticker format: '{ticker}'. Tickers must be 1-15 alphanumeric characters.")
    return cleaned


def resolve_company_name_from_ticker(ticker: str) -> str:
    """Reverse-resolve a human-readable company name from a ticker.

    Uses the KNOWN_TICKERS dictionary in reverse. Returns the original
    ticker as fallback if no match is found.
    """
    try:
        rev = {v.upper(): k for k, v in KNOWN_TICKERS.items() if v}
        bare = re.sub(r"\.(NS|BO|NSE|BSE|L|DE|TO|HK|SS|SZ)$", "", ticker.upper())
        if ticker.upper() in rev:
            return rev[ticker.upper()].title()
        elif bare in rev:
            return rev[bare].title()
    except Exception:
        pass
    return ticker


async def fetch_breach_data(ticker: str, start_date: str = "2015-01-01") -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Fetch stock and market data for a ticker in parallel.

    Returns:
        Tuple of (stock_data, market_data, benchmark).

    Raises:
        ValueError: If stock data is empty.
    """
    benchmark = detect_benchmark(ticker)
    stock_data, market_data = await asyncio.gather(
        asyncio.to_thread(fetch_stock_data, ticker, start_date),
        asyncio.to_thread(fetch_market_data, start_date, benchmark),
    )
    if stock_data.empty:
        raise ValueError(f"No stock data available for {ticker}")
    return stock_data, market_data, benchmark


def build_breach_event(
    company_name: str,
    ticker: str,
    breach_date: str,
    records_affected: int,
    breach_type: str,
    stock_data: pd.DataFrame,
    market_data: pd.DataFrame,
    benchmark: str,
) -> BreachEvent:
    """Construct a BreachEvent from raw inputs."""
    return BreachEvent(
        company_name=company_name,
        ticker=ticker,
        breach_date=pd.Timestamp(breach_date),
        pwn_count=records_affected,
        breach_type=breach_type,
        stock_data=stock_data,
        market_data=market_data,
        benchmark=benchmark,
    )


async def score_company(
    company_name: str,
    breach_date: str,
    records_affected: int,
    breach_type: str,
    start_date: str = "2015-01-01",
    feature_config: FeatureConfig | None = None,
) -> tuple[ScoreResponse, BreachFeatures]:
    """Full scoring pipeline: resolve → fetch → features → predict.

    Returns:
        Tuple of (ScoreResponse, BreachFeatures) for use by callers.

    Raises:
        HTTPException: On resolution failure, missing data, or insufficient data.
    """
    from fastapi import HTTPException

    ticker = resolve_ticker(company_name)
    if ticker is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not resolve ticker for '{company_name}'. Add mapping to data/ticker_overrides.json.",
        )

    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    stock_data, market_data, benchmark = await fetch_breach_data(ticker, start_date)

    event = build_breach_event(
        company_name=company_name, ticker=ticker,
        breach_date=breach_date, records_affected=records_affected,
        breach_type=breach_type, stock_data=stock_data,
        market_data=market_data, benchmark=benchmark,
    )

    features = await asyncio.to_thread(compute_features, event, feature_config) if feature_config else await asyncio.to_thread(compute_features, event)
    if features is None:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data around breach date for {company_name}. Try a different date.",
        )

    model = get_or_train_model()
    features_df = pd.DataFrame([features.to_dict()])
    prediction = score_features(model, features_df)

    severity = classify_severity(features.car_minus5_plus30, feature_config) if feature_config else classify_severity(features.car_minus5_plus30)

    response = ScoreResponse(
        company=company_name,
        ticker=ticker,
        risk_score=prediction["risk_score"],
        prediction=prediction["prediction"],
        confidence=prediction["confidence"],
        probabilities=prediction["probabilities"],
        features=FeatureDetail.from_features(features, severity),
    )
    return response, features


# Re-export BreachFeatures for type hints
from ..feature_engine import BreachFeatures
