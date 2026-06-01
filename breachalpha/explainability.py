"""Explainability engine for BreachAlpha risk calculations.

Provides step-by-step breakdown of how the risk score is computed,
making the entire calculation transparent to the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .feature_engine import (
    BreachEvent,
    classify_severity,
    compute_abnormal_returns_vec,
    compute_car_vec,
    compute_daily_returns,
    compute_recovery_time_vec,
    normalize_datetimelike_index,
)

BENCHMARK_NAMES = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ Composite",
    "^DJI": "Dow Jones Industrial Average",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
    "^NSEI": "NIFTY 50",
    "^BSESN": "BSE SENSEX",
    "^HSI": "Hang Seng Index",
    "^GDAXI": "DAX",
    "^FCHI": "CAC 40",
    "^STOXX50E": "EURO STOXX 50",
}
from .model import SEVERITY_LABELS, predict_severity


@dataclass
class CalculationStep:
    """A single step in the risk calculation."""
    step_number: int
    name: str
    description: str
    formula: str
    inputs: dict
    output: float | str | dict
    interpretation: str


@dataclass
class ExplainabilityReport:
    """Full explainability report for a risk score."""
    company: str
    ticker: str
    breach_date: str
    steps: list[CalculationStep]
    final_score: float
    final_prediction: str
    confidence: float
    probabilities: dict[str, float]
    feature_contributions: dict[str, float]
    methodology: str
    limitations: list[str]


def explain_daily_return(prices: pd.Series, date_idx: int, date_label: str) -> CalculationStep:
    """Explain the daily return calculation for a specific date."""
    if date_idx <= 0 or date_idx >= len(prices):
        return CalculationStep(
            step_number=0, name=f"Daily Return ({date_label})",
            description="Insufficient data",
            formula="N/A", inputs={}, output=0.0,
            interpretation="No data available for this date",
        )

    p_t = float(prices.iloc[date_idx])
    p_t1 = float(prices.iloc[date_idx - 1])
    ret = (p_t - p_t1) / p_t1 if p_t1 != 0 else 0.0

    return CalculationStep(
        step_number=0,
        name=f"Daily Return ({date_label})",
        description=f"Calculate stock return on {date_label}",
        formula="R_t = (P_t - P_{t-1}) / P_{t-1}",
        inputs={"P_t": round(p_t, 2), "P_{t-1}": round(p_t1, 2)},
        output=round(ret, 6),
        interpretation=(
            f"Stock {'fell' if ret < 0 else 'rose'} {abs(ret)*100:.2f}% on this day"
            f" (from ${p_t1:.2f} to ${p_t:.2f})"
        ),
    )


def explain_abnormal_return(stock_ret: float, market_ret: float, date_label: str) -> CalculationStep:
    """Explain the abnormal return calculation."""
    ar = stock_ret - market_ret

    return CalculationStep(
        step_number=0,
        name=f"Abnormal Return ({date_label})",
        description=f"Isolate the breach-specific impact from market movement",
        formula="AR = R_stock - R_market",
        inputs={
            "R_stock": round(stock_ret, 6),
            "R_market": round(market_ret, 6),
        },
        output=round(ar, 6),
        interpretation=(
            f"Stock moved {abs(stock_ret)*100:.2f}% while market moved {abs(market_ret)*100:.2f}%. "
            f"The {'abnormal loss' if ar < 0 else 'abnormal gain'} was {abs(ar)*100:.2f}% — "
            f"this is the breach-specific impact."
        ),
    )


def explain_car(ar_values: list[float], window_name: str, start: int, end: int) -> CalculationStep:
    """Explain cumulative abnormal return."""
    car = sum(ar_values)

    return CalculationStep(
        step_number=0,
        name=f"CAR ({window_name})",
        description=f"Cumulative abnormal return over {window_name} window",
        formula=f"CAR = Σ AR from day {start} to day {end}",
        inputs={"ar_values": [round(v, 6) for v in ar_values], "window": f"[{start}, {end}]"},
        output=round(car, 6),
        interpretation=(
            f"Over the {window_name} window, the stock experienced a cumulative "
            f"{'loss' if car < 0 else 'gain'} of {abs(car)*100:.2f}% beyond market expectations."
        ),
    )


def explain_volatility(pre_vol: float, post_vol: float) -> CalculationStep:
    """Explain volatility spike calculation."""
    ratio = post_vol / pre_vol if pre_vol > 0 else 1.0

    return CalculationStep(
        step_number=0,
        name="Volatility Spike",
        description="Compare pre- and post-breach price volatility",
        formula="Ratio = σ_post / σ_pre",
        inputs={"σ_pre": round(pre_vol, 6), "σ_post": round(post_vol, 6)},
        output=round(ratio, 3),
        interpretation=(
            f"Volatility increased {ratio:.1f}x after the breach. "
            + (f"This indicates significant market uncertainty." if ratio > 1.5
               else f"Market remained relatively stable.")
        ),
    )


def explain_volume_change(pre_vol: float, post_vol: float) -> CalculationStep:
    """Explain trading volume change."""
    ratio = post_vol / pre_vol if pre_vol > 0 else 1.0

    return CalculationStep(
        step_number=0,
        name="Volume Spike",
        description="Compare pre- and post-breach trading volume",
        formula="Ratio = V_post / V_pre",
        inputs={"V_pre": round(pre_vol, 0), "V_post": round(post_vol, 0)},
        output=round(ratio, 3),
        interpretation=(
            f"Trading volume increased {ratio:.1f}x after the breach. "
            + (f"Heavy selling pressure detected." if ratio > 2.0
               else f"Moderate trading activity change.")
        ),
    )


def explain_severity_classification(car: float) -> CalculationStep:
    """Explain how severity is classified from CAR."""
    severity = classify_severity(car)

    thresholds = {
        "critical": "CAR < -15%",
        "high": "-15% ≤ CAR < -7%",
        "medium": "-7% ≤ CAR < -2%",
        "low": "CAR ≥ -2%",
    }

    return CalculationStep(
        step_number=0,
        name="Severity Classification",
        description="Map CAR to impact severity category",
        formula="severity = f(CAR) based on academic thresholds",
        inputs={"car": round(car, 6), "thresholds": thresholds},
        output=severity,
        interpretation=(
            f"A CAR of {car*100:.2f}% falls in the '{severity}' category. "
            f"Threshold: {thresholds[severity]}"
        ),
    )


def explain_risk_score(probabilities: dict[str, float]) -> CalculationStep:
    """Explain the risk score calculation."""
    weights = {"low": 10, "medium": 35, "high": 65, "critical": 95}
    score = sum(probabilities.get(label, 0) * weights[label] for label in SEVERITY_LABELS)

    breakdown = {label: f"{probabilities.get(label, 0)*100:.1f}% × {weights[label]} = {probabilities.get(label, 0)*weights[label]:.1f}"
                 for label in SEVERITY_LABELS}

    return CalculationStep(
        step_number=0,
        name="Risk Score",
        description="Weighted probability sum → final 0-100 score",
        formula="Score = Σ P(severity) × weight(severity)",
        inputs={"weights": weights, "breakdown": breakdown},
        output=round(score, 1),
        interpretation=(
            f"The risk score is {score:.1f}/100. "
            f"This is computed as a weighted sum: "
            f"Low(10)×{probabilities.get('low', 0)*100:.0f}% + "
            f"Medium(35)×{probabilities.get('medium', 0)*100:.0f}% + "
            f"High(65)×{probabilities.get('high', 0)*100:.0f}% + "
            f"Critical(95)×{probabilities.get('critical', 0)*100:.0f}%"
        ),
    )


def generate_explanation(
    event: BreachEvent,
    features,
    model,
) -> ExplainabilityReport:
    """Generate a full explainability report for a breach analysis.

    Walks through every step of the calculation with formulas,
    inputs, outputs, and human-readable interpretations.
    """
    steps = []

    # Normalize indices to date-only for cross-exchange alignment
    stock = normalize_datetimelike_index(event.stock_data)
    market = normalize_datetimelike_index(event.market_data)

    # Find event date in stock data
    common_dates = stock.index.intersection(market.index)
    if len(common_dates) < 30:
        return ExplainabilityReport(
            company=event.company_name, ticker=event.ticker,
            breach_date=event.breach_date.strftime("%Y-%m-%d"),
            steps=[], final_score=0, final_prediction="unknown",
            confidence=0, probabilities={}, feature_contributions={},
            methodology="Insufficient data for analysis",
            limitations=["Need at least 30 trading days of data around the breach date"],
        )

    stock = stock.loc[common_dates]
    market = market.loc[common_dates]
    stock_returns = compute_daily_returns(stock["Close"])
    market_returns = compute_daily_returns(market["Close"])

    common_return_dates = stock_returns.index.intersection(market_returns.index)
    stock_returns = stock_returns.loc[common_return_dates]
    market_returns = market_returns.loc[common_return_dates]

    event_date = pd.Timestamp(event.breach_date)
    event_idx_stock = common_dates.get_indexer([event_date], method="nearest")[0]
    event_idx_returns = common_return_dates.get_indexer([event_date], method="nearest")[0]

    # Step 1: Daily returns around event
    for offset, label in [(-1, "Day -1"), (0, "Day 0 (Event)"), (1, "Day +1"), (5, "Day +5")]:
        idx = event_idx_returns + offset
        if 0 < idx < len(stock_returns):
            step = explain_daily_return(stock["Close"], event_idx_stock + offset, label)
            step.step_number = len(steps) + 1
            steps.append(step)

    # Step 2: Market returns for same days
    for offset, label in [(0, "Day 0"), (1, "Day +1")]:
        idx = event_idx_returns + offset
        if 0 < idx < len(market_returns):
            sr = float(stock_returns.iloc[idx])
            mr = float(market_returns.iloc[idx])
            step = explain_abnormal_return(sr, mr, label)
            step.step_number = len(steps) + 1
            steps.append(step)

    # Step 3: CAR calculation
    from .feature_engine import compute_abnormal_returns_vec as _car_helper
    abnormal_returns = _car_helper(stock_returns, market_returns)

    for (start, end, label) in [(-1, 1, "3-day"), (-5, 30, "36-day")]:
        s = max(0, event_idx_returns + start)
        e = min(len(abnormal_returns), event_idx_returns + end + 1)
        ar_slice = abnormal_returns.iloc[s:e].tolist()
        step = explain_car(ar_slice, label, start, end)
        step.step_number = len(steps) + 1
        steps.append(step)

    # Step 4: Volatility
    pre_vol = stock_returns.iloc[max(0, event_idx_returns-30):event_idx_returns].std()
    post_vol = stock_returns.iloc[event_idx_returns:min(len(stock_returns), event_idx_returns+30)].std()
    step = explain_volatility(float(pre_vol), float(post_vol))
    step.step_number = len(steps) + 1
    steps.append(step)

    # Step 5: Volume
    pre_v = float(stock["Volume"].iloc[max(0, event_idx_stock-5):event_idx_stock].mean())
    post_v = float(stock["Volume"].iloc[event_idx_stock:min(len(stock), event_idx_stock+5)].mean())
    step = explain_volume_change(pre_v, post_v)
    step.step_number = len(steps) + 1
    steps.append(step)

    # Step 6: Severity classification
    car_36 = features.car_minus5_plus30
    step = explain_severity_classification(car_36)
    step.step_number = len(steps) + 1
    steps.append(step)

    # Step 7: Model prediction
    features_df = pd.DataFrame([features.to_dict()])
    prediction = predict_severity(model, features_df)

    # Step 8: Risk score
    step = explain_risk_score(prediction["probabilities"])
    step.step_number = len(steps) + 1
    steps.append(step)

    # Feature contributions (SHAP-like approximation)
    feature_contributions = {}
    importance_weights = {
        "abnormal_return_day0": 0.25,
        "car_minus1_plus1": 0.20,
        "car_minus5_plus30": 0.20,
        "volatility_spike": 0.15,
        "volume_change": 0.10,
        "abnormal_return_day5": 0.05,
        "abnormal_return_day30": 0.03,
        "time_to_recovery": 0.02,
    }
    for feat, weight in importance_weights.items():
        val = getattr(features, feat, 0)
        if val is None:
            val = 0
        contribution = float(val) * weight
        feature_contributions[feat] = round(contribution, 6)

    return ExplainabilityReport(
        company=event.company_name,
        ticker=event.ticker,
        breach_date=event.breach_date.strftime("%Y-%m-%d"),
        steps=steps,
        final_score=prediction["risk_score"],
        final_prediction=prediction["prediction"],
        confidence=prediction["confidence"],
        probabilities=prediction["probabilities"],
        feature_contributions=feature_contributions,
        methodology=(
            "Event Study Methodology (MacKinlay, 1997) using Market-Adjusted Model. "
            f"Abnormal Return = Stock Return - Market Return ({BENCHMARK_NAMES.get(event.benchmark, event.benchmark)}). "
            "Severity classified by CAR thresholds from academic literature. "
            "Risk Score = weighted probability sum across severity categories."
        ),
        limitations=[
            "Market-Adjusted Model assumes alpha=0, beta=1 (simpler than OLS market model)",
            "Abnormal returns may be confounded by other news on the same day",
            "Recovery time assumes no subsequent breaches or major events",
            "Model trained on synthetic data — needs real breach data for production use",
            "Stock price impacts vary by company size, sector, and market conditions",
        ],
    )
