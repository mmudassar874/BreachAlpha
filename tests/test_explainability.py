"""Tests for explainability module."""

import pandas as pd
import pytest
from breachalpha.explainability import (
    explain_abnormal_return,
    explain_car,
    explain_daily_return,
    explain_risk_score,
    explain_severity_classification,
    explain_volatility,
    explain_volume_change,
)
from breachalpha.feature_engine import classify_severity


class TestExplainDailyReturn:
    def test_known_values(self):
        prices = pd.Series([100, 110, 105, 108])
        step = explain_daily_return(prices, 1, "Day 0")
        assert step.name == "Daily Return (Day 0)"
        assert abs(step.output - 0.10) < 1e-6
        assert "rose" in step.interpretation

    def test_negative_return(self):
        prices = pd.Series([100, 90, 95])
        step = explain_daily_return(prices, 1, "Day 0")
        assert step.output < 0
        assert "fell" in step.interpretation

    def test_boundary(self):
        prices = pd.Series([100])
        step = explain_daily_return(prices, 0, "Day 0")
        assert "Insufficient" in step.description


class TestExplainAbnormalReturn:
    def test_positive_abnormal(self):
        step = explain_abnormal_return(0.05, 0.02, "Day 0")
        assert abs(step.output - 0.03) < 1e-6
        assert "abnormal gain" in step.interpretation

    def test_negative_abnormal(self):
        step = explain_abnormal_return(-0.05, 0.01, "Day 0")
        assert abs(step.output - (-0.06)) < 1e-6
        assert "abnormal loss" in step.interpretation


class TestExplainCAR:
    def test_basic(self):
        step = explain_car([0.01, -0.02, 0.03], "3-day", -1, 1)
        assert abs(step.output - 0.02) < 1e-6

    def test_negative_car(self):
        step = explain_car([-0.05, -0.03, -0.02], "3-day", -1, 1)
        assert step.output < 0
        assert "loss" in step.interpretation


class TestExplainVolatility:
    def test_increased(self):
        step = explain_volatility(0.01, 0.05)
        assert step.output == 5.0
        assert "increased" in step.interpretation

    def test_stable(self):
        step = explain_volatility(0.02, 0.02)
        assert step.output == 1.0


class TestExplainVolume:
    def test_spike(self):
        step = explain_volume_change(1_000_000, 5_000_000)
        assert step.output == 5.0
        assert "selling pressure" in step.interpretation


class TestExplainSeverityClassification:
    def test_critical(self):
        step = explain_severity_classification(-0.20)
        assert step.output == "critical"

    def test_low(self):
        step = explain_severity_classification(-0.01)
        assert step.output == "low"


class TestExplainRiskScore:
    def test_known_probs(self):
        probs = {"low": 0.1, "medium": 0.2, "high": 0.3, "critical": 0.4}
        step = explain_risk_score(probs)
        expected = 0.1*10 + 0.2*35 + 0.3*65 + 0.4*95
        assert abs(step.output - expected) < 0.1
