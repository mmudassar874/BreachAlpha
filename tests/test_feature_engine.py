"""Tests for feature_engine module — core financial calculations."""

import numpy as np
import pandas as pd
import pytest

from breachalpha.feature_engine import (
    BreachEvent,
    compute_daily_returns,
    compute_abnormal_returns_vec,
    compute_car_vec,
    compute_volatility_ratio_vec,
    compute_volume_change_vec,
    compute_recovery_time_vec,
    classify_severity,
    compute_features,
)


def _make_stock_data(days: int = 200, breach_day: int = 100, drop_pct: float = -0.10) -> pd.DataFrame:
    """Create synthetic stock data with a drop at breach_day."""
    dates = pd.bdate_range("2020-01-01", periods=days)
    np.random.seed(42)

    # Random walk with a drop at breach_day
    returns = np.random.normal(0.001, 0.02, days)
    returns[breach_day] = drop_pct  # Sharp drop on breach day
    returns[breach_day + 1] = drop_pct * 0.5  # Continued drop

    prices = 100 * np.cumprod(1 + returns)
    volume = np.random.randint(1_000_000, 10_000_000, days)

    return pd.DataFrame({
        "Open": prices * 0.99,
        "High": prices * 1.01,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": volume,
        "Dividends": 0.0,
        "Stock Splits": 0.0,
    }, index=dates)


def _make_market_data(days: int = 200) -> pd.DataFrame:
    """Create synthetic S&P 500 data (no drop — market unaffected)."""
    dates = pd.bdate_range("2020-01-01", periods=days)
    np.random.seed(99)
    returns = np.random.normal(0.0005, 0.01, days)
    prices = 3000 * np.cumprod(1 + returns)
    volume = np.random.randint(2_000_000, 4_000_000, days)

    return pd.DataFrame({
        "Open": prices * 0.99,
        "High": prices * 1.01,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": volume,
        "Dividends": 0.0,
        "Stock Splits": 0.0,
    }, index=dates)


class TestDailyReturns:
    def test_returns_length(self):
        prices = pd.Series([100, 102, 101, 105])
        returns = compute_daily_returns(prices)
        assert len(returns) == 3

    def test_known_values(self):
        prices = pd.Series([100, 110, 99])
        returns = compute_daily_returns(prices)
        assert abs(returns.iloc[0] - 0.10) < 1e-10
        assert abs(returns.iloc[1] - (-0.10)) < 1e-10

    def test_empty_series(self):
        returns = compute_daily_returns(pd.Series([]))
        assert len(returns) == 0


class TestAbnormalReturns:
    def test_no_abnormal_when_aligned(self):
        stock_r = pd.Series([0.01, 0.02, -0.01])
        market_r = pd.Series([0.01, 0.02, -0.01])
        ar = compute_abnormal_returns_vec(stock_r, market_r)
        assert all(abs(ar) < 1e-10)

    def test_negative_abnormal_on_drop(self):
        stock_r = pd.Series([-0.05, 0.01, 0.02])
        market_r = pd.Series([0.01, 0.01, 0.01])
        ar = compute_abnormal_returns_vec(stock_r, market_r)
        assert ar.iloc[0] < 0  # Stock dropped more than market


class TestCAR:
    def test_car_basic(self):
        ar = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
        # Window [-1, +1] around index 2: values at 1,2,3 = -0.02, 0.03, -0.01
        car = compute_car_vec(ar, -1, 1, 2)
        assert abs(car - 0.0) < 1e-10

    def test_car_full_window(self):
        ar = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
        car = compute_car_vec(ar, 0, 4, 0)
        assert abs(car - 0.15) < 1e-10


class TestVolatilityRatio:
    def test_equal_volatility(self):
        # Constant returns = zero volatility
        returns = pd.Series([0.01] * 60)
        ratio = compute_volatility_ratio_vec(returns, 30)
        assert ratio == 1.0

    def test_increased_volatility(self):
        np.random.seed(42)
        pre = np.random.normal(0, 0.01, 30)
        post = np.random.normal(0, 0.05, 30)
        returns = pd.Series(np.concatenate([pre, post]))
        ratio = compute_volatility_ratio_vec(returns, 30)
        assert ratio > 1.5  # Post vol should be much higher


class TestVolumeChange:
    def test_equal_volume(self):
        volume = pd.Series([1_000_000] * 20)
        change = compute_volume_change_vec(volume, 10)
        assert change == 1.0

    def test_volume_spike(self):
        volume = pd.Series([1_000_000] * 10 + [5_000_000] * 10)
        change = compute_volume_change_vec(volume, 10)
        assert change > 4.0


class TestRecoveryTime:
    def test_quick_recovery(self):
        prices = pd.Series([100, 95, 90, 92, 95, 98, 100, 101])
        recovery = compute_recovery_time_vec(prices, 1, 100.0)
        assert recovery == 5  # Index 6 (price=100) - Index 1 (event) = 5 steps

    def test_no_recovery(self):
        prices = pd.Series([100, 90, 80, 70, 60])
        recovery = compute_recovery_time_vec(prices, 1, 100.0, max_days=4)
        assert recovery is None


class TestClassifySeverity:
    def test_critical(self):
        assert classify_severity(-0.20) == "critical"

    def test_high(self):
        assert classify_severity(-0.10) == "high"

    def test_medium(self):
        assert classify_severity(-0.05) == "medium"

    def test_low(self):
        assert classify_severity(-0.01) == "low"

    def test_positive(self):
        assert classify_severity(0.05) == "low"


class TestComputeFeatures:
    def test_full_pipeline(self):
        stock = _make_stock_data(200, breach_day=100, drop_pct=-0.10)
        market = _make_market_data(200)
        breach_date = stock.index[100]

        event = BreachEvent(
            company_name="TestCorp",
            ticker="TEST",
            breach_date=breach_date,
            pwn_count=1_000_000,
            breach_type="data_leak",
            stock_data=stock,
            market_data=market,
        )

        features = compute_features(event)
        assert features is not None
        assert features.company_name == "TestCorp"
        assert features.ticker == "TEST"
        assert features.abnormal_return_day0 < 0  # Should be negative (stock dropped)
        assert features.volatility_spike >= 0
        assert features.volume_change >= 0

    def test_returns_none_on_empty_data(self):
        event = BreachEvent(
            company_name="Empty",
            ticker="EMP",
            breach_date=pd.Timestamp("2020-06-01"),
            pwn_count=1000,
            breach_type="hack",
            stock_data=pd.DataFrame(),
            market_data=pd.DataFrame(),
        )
        assert compute_features(event) is None

    def test_returns_none_on_short_data(self):
        stock = _make_stock_data(10, breach_day=5)
        market = _make_market_data(10)
        event = BreachEvent(
            company_name="Short",
            ticker="SHR",
            breach_date=stock.index[5],
            pwn_count=1000,
            breach_type="hack",
            stock_data=stock,
            market_data=market,
        )
        assert compute_features(event) is None
