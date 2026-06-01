"""Command-line interface for BreachAlpha."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from . import __version__
from .breach_loader import load_breaches, get_breach_summary
from .ticker_resolver import resolve_all, load_overrides
from .stock_loader import fetch_stock_data, fetch_market_data
from .feature_engine import BreachEvent, compute_features, classify_severity
from .model import train_model, save_model, load_model, predict_severity, prepare_training_data


def cmd_demo(args: argparse.Namespace) -> int:
    """Run demo with three famous breaches."""
    print("=" * 60)
    print("  BreachAlpha — Cyber-Financial Risk Quantifier — Demo")
    print("=" * 60)

    demo_cases = [
        {
            "company": "Equifax",
            "ticker": "EFX",
            "breach_date": "2017-09-07",
            "pwn_count": 147_000_000,
            "breach_type": "data_leak",
            "description": "Massive credit data breach exposing SSNs, birth dates, addresses",
        },
        {
            "company": "Capital One",
            "ticker": "COF",
            "breach_date": "2019-07-29",
            "pwn_count": 106_000_000,
            "breach_type": "data_leak",
            "description": "Cloud misconfiguration exposed credit card applications",
        },
        {
            "company": "Marriott",
            "ticker": "MAR",
            "breach_date": "2018-11-30",
            "pwn_count": 500_000_000,
            "breach_type": "data_leak",
            "description": "Starwood reservation system breach (4 years undetected)",
        },
    ]

    print(f"\nFetching market data (S&P 500)...")
    market_data = fetch_market_data(start="2015-01-01")

    model = load_model()
    if model is None:
        print("No trained model found. Training on synthetic data...")
        result = _train_synthetic()
        model = result["model"]

    print()

    for case in demo_cases:
        print(f"\n{'─' * 60}")
        print(f"  {case['company']} ({case['ticker']})")
        print(f"  Breach: {case['breach_date']} — {case['description']}")
        print(f"  Records affected: {case['pwn_count']:,}")
        print(f"{'─' * 60}")

        stock_data = fetch_stock_data(
            case["ticker"],
            start="2015-01-01",
        )

        if stock_data.empty:
            print(f"  ⚠ No stock data available for {case['ticker']}")
            continue

        event = BreachEvent(
            company_name=case["company"],
            ticker=case["ticker"],
            breach_date=pd.Timestamp(case["breach_date"]),
            pwn_count=case["pwn_count"],
            breach_type=case["breach_type"],
            stock_data=stock_data,
            market_data=market_data,
        )

        features = compute_features(event)
        if features is None:
            print(f"  ⚠ Could not compute features (insufficient data)")
            continue

        features_df = pd.DataFrame([features.to_dict()])
        result = predict_severity(model, features_df)

        print(f"\n  Risk Score:    {result['risk_score']}/100")
        print(f"  Prediction:    {result['prediction'].upper()}")
        print(f"  Confidence:    {result['confidence']:.1%}")
        print(f"\n  Probability breakdown:")
        for label, prob in sorted(result["probabilities"].items(), key=lambda x: -x[1]):
            bar = "█" * int(prob * 30)
            print(f"    {label:>10}: {prob:.1%} {bar}")

        print(f"\n  Feature analysis:")
        print(f"    AR (Day 0):     {features.abnormal_return_day0:+.4f}")
        print(f"    AR (Day +1):    {features.abnormal_return_day1:+.4f}")
        print(f"    AR (Day +5):    {features.abnormal_return_day5:+.4f}")
        print(f"    CAR (-1,+1):    {features.car_minus1_plus1:+.4f}")
        print(f"    CAR (-5,+30):   {features.car_minus5_plus30:+.4f}")
        print(f"    Vol Spike:      {features.volatility_spike:.2f}x")
        print(f"    Volume Change:  {features.volume_change:.2f}x")
        recovery = f"{features.time_to_recovery} days" if features.time_to_recovery else "Not recovered"
        print(f"    Recovery:       {recovery}")

    print(f"\n{'=' * 60}")
    print("  Demo complete.")
    print("=" * 60)
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    """Train the model on breach data."""
    csv_path = Path(args.data)
    if not csv_path.exists():
        print(f"Error: Data file not found: {csv_path}")
        return 1

    print(f"Loading breaches from {csv_path}...")
    breaches = load_breaches(csv_path)
    summary = get_breach_summary(breaches)
    print(f"  {summary['total_breaches']} breaches, {summary['date_range'][0]} to {summary['date_range'][1]}")

    print(f"Resolving tickers...")
    overrides = load_overrides()
    resolutions = resolve_all(breaches["Name"].tolist(), overrides)

    resolved = breaches[breaches["Name"].map(resolutions).notna()].copy()
    resolved["ticker"] = resolved["Name"].map(resolutions)
    print(f"  Resolved {len(resolved)}/{len(breaches)} companies to tickers")

    if len(resolved) < 20:
        print(f"Error: Need at least 20 resolved companies to train (got {len(resolved)})")
        return 1

    print(f"Fetching stock data...")
    market_data = fetch_market_data(start="2010-01-01")

    features_list = []
    for _, row in resolved.iterrows():
        ticker = row["ticker"]
        print(f"  Processing {row['Name']} ({ticker})...", end=" ")
        stock_data = fetch_stock_data(ticker, start="2010-01-01")
        if stock_data.empty:
            print("no data, skipping")
            continue

        event = BreachEvent(
            company_name=row["Name"],
            ticker=ticker,
            breach_date=row["BreachDate"],
            pwn_count=int(row["PwnCount"]),
            breach_type="data_leak",  # Default; HIBP doesn't classify type
            stock_data=stock_data,
            market_data=market_data,
        )
        features = compute_features(event)
        if features is not None:
            features_list.append(features.to_dict())
            print("OK")
        else:
            print("insufficient data, skipping")

    if not features_list:
        print("Error: No features computed. Check data quality.")
        return 1

    df = pd.DataFrame(features_list)
    print(f"\nTraining model on {len(df)} samples...")
    result = train_model(df)

    model_path = save_model(result["model"], result["metrics"])
    print(f"Model saved to {model_path}")
    print(f"CV Accuracy: {result['metrics']['cv_accuracy_mean']:.1%} (+/- {result['metrics']['cv_accuracy_std']:.1%})")

    print(f"\nFeature importance:")
    for feat, imp in result["metrics"]["feature_importance"].items():
        bar = "█" * int(imp * 50)
        print(f"  {feat:>25}: {imp:.3f} {bar}")

    return 0


def _train_synthetic() -> dict:
    """Train on synthetic data for demo purposes."""
    import numpy as np

    np.random.seed(42)
    n = 100
    synthetic = pd.DataFrame({
        "abnormal_return_day0": np.random.normal(-0.02, 0.05, n),
        "abnormal_return_day1": np.random.normal(-0.01, 0.04, n),
        "abnormal_return_day5": np.random.normal(-0.005, 0.03, n),
        "abnormal_return_day30": np.random.normal(0.001, 0.02, n),
        "car_minus1_plus1": np.random.normal(-0.03, 0.08, n),
        "car_minus5_plus30": np.random.normal(-0.05, 0.12, n),
        "volatility_spike": np.random.uniform(0.8, 3.0, n),
        "volume_change": np.random.uniform(0.5, 5.0, n),
        "time_to_recovery": np.random.choice([5, 10, 20, 30, 60, None], n),
        "pwn_count": np.random.lognormal(15, 2, n).astype(int),
    })
    return train_model(synthetic)


def cmd_score(args: argparse.Namespace) -> int:
    """Score a single company for breach impact."""
    company = args.company
    breach_type = args.breach_type or "data_leak"
    pwn_count = args.records or 1_000_000
    breach_date = args.date or "2024-01-01"

    print(f"Scoring {company} (breach type: {breach_type})...")

    from .ticker_resolver import resolve_ticker
    ticker = resolve_ticker(company)
    if ticker is None:
        print(f"Error: Could not resolve ticker for '{company}'")
        print(f"Tip: Add the mapping to data/ticker_overrides.json")
        return 1

    print(f"  Resolved ticker: {ticker}")

    stock_data = fetch_stock_data(ticker, start="2015-01-01")
    if stock_data.empty:
        print(f"Error: No stock data for {ticker}")
        return 1

    market_data = fetch_market_data(start="2015-01-01")

    event = BreachEvent(
        company_name=company,
        ticker=ticker,
        breach_date=pd.Timestamp(breach_date),
        pwn_count=pwn_count,
        breach_type=breach_type,
        stock_data=stock_data,
        market_data=market_data,
    )

    features = compute_features(event)
    if features is None:
        print("Error: Could not compute features (insufficient data around breach date)")
        return 1

    model = load_model()
    if model is None:
        print("No trained model found. Training on synthetic data first...")
        result = _train_synthetic()
        model = result["model"]

    features_df = pd.DataFrame([features.to_dict()])
    result = predict_severity(model, features_df)

    print(f"\n{'─' * 40}")
    print(f"  Risk Score:  {result['risk_score']}/100")
    print(f"  Severity:    {result['prediction'].upper()}")
    print(f"  Confidence:  {result['confidence']:.1%}")
    print(f"{'─' * 40}")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="breachalpha",
        description="BreachAlpha — Cyber-Financial Risk Quantifier",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # demo
    subparsers.add_parser("demo", help="Run demo with famous breaches")

    # train
    train_parser = subparsers.add_parser("train", help="Train the model")
    train_parser.add_argument("--data", required=True, help="Path to breach CSV")

    # score
    score_parser = subparsers.add_parser("score", help="Score a company")
    score_parser.add_argument("--company", required=True, help="Company name")
    score_parser.add_argument("--breach-type", help="Breach type (ransomware, data_leak, etc.)")
    score_parser.add_argument("--records", type=int, help="Number of records affected")
    score_parser.add_argument("--date", help="Breach date (YYYY-MM-DD)")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "demo": cmd_demo,
        "train": cmd_train,
        "score": cmd_score,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
