"""Optimized feature engineering engine.

Vectorized operations, parallel processing, and robust edge case handling.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Configuration defaults
DEFAULT_ESTIMATION_WINDOW = 250
DEFAULT_PRE_EVENT_WINDOW = 30
DEFAULT_POST_EVENT_WINDOW = 60
MAX_WORKERS = 4


@dataclass
class BreachEvent:
    """A single breach event with stock data."""
    company_name: str
    ticker: str
    breach_date: pd.Timestamp
    pwn_count: int
    breach_type: str
    stock_data: pd.DataFrame
    market_data: pd.DataFrame
    benchmark: str = "^GSPC"


@dataclass
class AnalysisConfig:
    """User-configurable analysis parameters."""
    estimation_window: int = DEFAULT_ESTIMATION_WINDOW
    pre_event_window: int = DEFAULT_PRE_EVENT_WINDOW
    post_event_window: int = DEFAULT_POST_EVENT_WINDOW
    recovery_max_days: int = 90
    min_data_days: int = 30
    # Severity thresholds (CAR values)
    threshold_critical: float = -0.15
    threshold_high: float = -0.07
    threshold_medium: float = -0.02
    # Event windows for CAR
    car_short_start: int = -1
    car_short_end: int = 1
    car_long_start: int = -5
    car_long_end: int = 30
    # AR calculation days
    ar_days: list = None

    def __post_init__(self):
        if self.ar_days is None:
            self.ar_days = [0, 1, 5, 30]


@dataclass
class BreachFeatures:
    """Computed features for a single breach event."""
    company_name: str
    ticker: str
    breach_date: str
    pwn_count: int
    breach_type: str
    abnormal_return_day0: float
    abnormal_return_day1: float
    abnormal_return_day5: float
    abnormal_return_day30: float
    car_minus1_plus1: float
    car_minus5_plus30: float
    volatility_spike: float
    volume_change: float
    time_to_recovery: Optional[int]

    def to_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "ticker": self.ticker,
            "breach_date": self.breach_date,
            "pwn_count": self.pwn_count,
            "breach_type": self.breach_type,
            "abnormal_return_day0": self.abnormal_return_day0,
            "abnormal_return_day1": self.abnormal_return_day1,
            "abnormal_return_day5": self.abnormal_return_day5,
            "abnormal_return_day30": self.abnormal_return_day30,
            "car_minus1_plus1": self.car_minus1_plus1,
            "car_minus5_plus30": self.car_minus5_plus30,
            "volatility_spike": self.volatility_spike,
            "volume_change": self.volume_change,
            "time_to_recovery": self.time_to_recovery,
        }


# ── Vectorized Core Functions ───────────────────────────────────────────


def compute_daily_returns(prices: pd.Series) -> pd.Series:
    """Vectorized daily returns: R_t = (P_t - P_{t-1}) / P_{t-1}"""
    return prices.pct_change().dropna()


def compute_abnormal_returns_vec(
    stock_returns: pd.Series,
    market_returns: pd.Series,
) -> pd.Series:
    """Vectorized abnormal returns via index alignment."""
    aligned = pd.concat([stock_returns, market_returns], axis=1, join="inner")
    aligned.columns = ["stock", "market"]
    return aligned["stock"] - aligned["market"]


def compute_car_vec(abnormal_returns: pd.Series, start: int, end: int, event_idx: int) -> float:
    """Vectorized CAR computation."""
    s = max(0, event_idx + start)
    e = min(len(abnormal_returns), event_idx + end + 1)
    if s >= e:
        return 0.0
    return float(abnormal_returns.iloc[s:e].sum())


def compute_volatility_ratio_vec(
    stock_returns: pd.Series,
    event_idx: int,
    pre_window: int = 30,
    post_window: int = 30,
) -> float:
    """Vectorized volatility ratio."""
    pre_start = max(0, event_idx - pre_window)
    pre_returns = stock_returns.iloc[pre_start:event_idx]
    post_end = min(len(stock_returns), event_idx + post_window)
    post_returns = stock_returns.iloc[event_idx:post_end]

    if len(pre_returns) < 5 or len(post_returns) < 5:
        return 1.0

    pre_vol = pre_returns.std()
    if pre_vol == 0:
        return 1.0

    return float(post_returns.std() / pre_vol)


def compute_volume_change_vec(
    volume: pd.Series,
    event_idx: int,
    pre_window: int = 5,
    post_window: int = 5,
) -> float:
    """Vectorized volume change."""
    pre_start = max(0, event_idx - pre_window)
    pre_vol = volume.iloc[pre_start:event_idx]
    post_end = min(len(volume), event_idx + post_window)
    post_vol = volume.iloc[event_idx:post_end]

    if len(pre_vol) < 2 or len(post_vol) < 2:
        return 1.0

    pre_avg = pre_vol.mean()
    if pre_avg == 0:
        return 1.0

    return float(post_vol.mean() / pre_avg)


def compute_recovery_time_vec(
    prices: pd.Series,
    event_idx: int,
    pre_breach_price: float,
    max_days: int = 90,
) -> Optional[int]:
    """Vectorized recovery time computation."""
    post_prices = prices.iloc[event_idx:]
    search_window = post_prices.head(max_days)

    recovered = search_window[search_window >= pre_breach_price]
    if recovered.empty:
        return None

    delta = recovered.index[0] - prices.index[event_idx]
    if hasattr(delta, "days"):
        return delta.days
    return int(delta)


def classify_severity(car: float, config: AnalysisConfig = None) -> str:
    """Classify breach impact severity based on CAR."""
    if config is None:
        config = AnalysisConfig()

    if car < config.threshold_critical:
        return "critical"
    elif car < config.threshold_high:
        return "high"
    elif car < config.threshold_medium:
        return "medium"
    else:
        return "low"


# ── Optimized Feature Computation ───────────────────────────────────────


def normalize_datetimelike_index(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a DataFrame's index to date-only timestamps.

    Strips timezone, removes time components, and deduplicates.
    Returns a copy — the original is not mutated.
    """
    idx = pd.DatetimeIndex([d if isinstance(d, pd.Timestamp) else pd.Timestamp(d) for d in df.index])
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    idx = pd.DatetimeIndex([d.replace(hour=0, minute=0, second=0, microsecond=0) for d in idx])
    out = df.copy()
    out.index = idx
    return out[~out.index.duplicated(keep='last')]


def compute_features(
    event: BreachEvent,
    config: AnalysisConfig = None,
) -> Optional[BreachFeatures]:
    """Compute all features for a single breach event.

    Optimized with:
    - Early exit on insufficient data
    - Vectorized operations
    - Pre-aligned indices
    """
    if config is None:
        config = AnalysisConfig()

    stock = event.stock_data
    market = event.market_data

    if stock.empty or market.empty:
        return None

    # Normalize timezone-naive datetimes to date-only for cross-exchange alignment
    stock = normalize_datetimelike_index(stock)
    market = normalize_datetimelike_index(market)

    # Pre-align on common dates (single intersection, cached)
    common_dates = stock.index.intersection(market.index)
    if len(common_dates) < config.min_data_days:
        return None

    stock = stock.loc[common_dates]
    market = market.loc[common_dates]

    # Find event date index
    event_date = pd.Timestamp(event.breach_date)
    event_idx = common_dates.get_indexer([event_date], method="nearest")[0]

    if event_idx < config.pre_event_window:
        return None

    # Compute returns once (vectorized)
    stock_returns = compute_daily_returns(stock["Close"])
    market_returns = compute_daily_returns(market["Close"])

    # Align returns on common dates
    common_return_dates = stock_returns.index.intersection(market_returns.index)
    stock_returns = stock_returns.loc[common_return_dates]
    market_returns = market_returns.loc[common_return_dates]

    event_idx_returns = common_return_dates.get_indexer([event_date], method="nearest")[0]

    # Compute abnormal returns once (vectorized)
    abnormal_returns = compute_abnormal_returns_vec(stock_returns, market_returns)

    # AR at specific days (vectorized slice)
    ar_values = {}
    for day in config.ar_days:
        idx = event_idx_returns + day
        if 0 <= idx < len(abnormal_returns):
            ar_values[day] = float(abnormal_returns.iloc[idx])
        else:
            ar_values[day] = 0.0

    # CAR (vectorized)
    car_short = compute_car_vec(abnormal_returns, config.car_short_start, config.car_short_end, event_idx_returns)
    car_long = compute_car_vec(abnormal_returns, config.car_long_start, config.car_long_end, event_idx_returns)

    # Volatility and volume (vectorized)
    vol_ratio = compute_volatility_ratio_vec(stock_returns, event_idx_returns)
    vol_change = compute_volume_change_vec(stock["Volume"], event_idx_returns)

    # Recovery time
    pre_prices = stock["Close"].iloc[max(0, event_idx - 5):event_idx]
    pre_breach_price = float(pre_prices.mean()) if not pre_prices.empty else 0.0
    recovery = compute_recovery_time_vec(stock["Close"], event_idx, pre_breach_price, config.recovery_max_days)

    return BreachFeatures(
        company_name=event.company_name,
        ticker=event.ticker,
        breach_date=event.breach_date.strftime("%Y-%m-%d"),
        pwn_count=event.pwn_count,
        breach_type=event.breach_type,
        abnormal_return_day0=ar_values.get(0, 0.0),
        abnormal_return_day1=ar_values.get(1, 0.0),
        abnormal_return_day5=ar_values.get(5, 0.0),
        abnormal_return_day30=ar_values.get(30, 0.0),
        car_minus1_plus1=car_short,
        car_minus5_plus30=car_long,
        volatility_spike=vol_ratio,
        volume_change=vol_change,
        time_to_recovery=recovery,
    )


def compute_features_batch(
    events: list[BreachEvent],
    config: AnalysisConfig = None,
    max_workers: int = MAX_WORKERS,
) -> pd.DataFrame:
    """Compute features for a batch of breach events.

    Uses ThreadPoolExecutor for I/O-bound stock data processing.
    Falls back to sequential if parallel fails.
    """
    if not events:
        return pd.DataFrame()

    if config is None:
        config = AnalysisConfig()

    # Use parallel processing for large batches
    if len(events) > 5 and max_workers > 1:
        try:
            results = []
            with ThreadPoolExecutor(max_workers=min(max_workers, len(events))) as executor:
                future_to_event = {
                    executor.submit(compute_features, event, config): event
                    for event in events
                }
                for future in as_completed(future_to_event):
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result.to_dict())
                    except Exception as e:
                        event = future_to_event[future]
                        logger.warning("Feature computation failed for %s: %s", event.company_name, e)

            if results:
                return pd.DataFrame(results)
        except Exception as e:
            logger.warning("Parallel computation failed, falling back to sequential: %s", e)

    # Sequential fallback
    results = []
    for event in events:
        try:
            features = compute_features(event, config)
            if features is not None:
                results.append(features.to_dict())
        except Exception as e:
            logger.warning("Feature computation failed for %s: %s", event.company_name, e)

    return pd.DataFrame(results) if results else pd.DataFrame()
