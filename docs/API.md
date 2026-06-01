# API Reference

## breach_loader

```python
from breachalpha.breach_loader import load_breaches, get_breach_summary

# Load breach records from CSV
df = load_breaches("data/breaches.csv")

# Get summary statistics
summary = get_breach_summary(df)
# → {"total_breaches": 500, "date_range": ("2017-01-01", "2024-12-31"), ...}
```

## ticker_resolver

```python
from breachalpha.ticker_resolver import resolve_ticker, resolve_all, load_overrides

# Resolve single company
ticker = resolve_ticker("Equifax")  # → "EFX"

# Resolve with custom overrides
ticker = resolve_ticker("Acme Corp", overrides={"acme corp": "ACME"})

# Batch resolve
resolutions = resolve_all(["Equifax", "Capital One", "Unknown Corp"])
# → {"Equifax": "EFX", "Capital One": "COF", "Unknown Corp": None}
```

## stock_loader

```python
from breachalpha.stock_loader import fetch_stock_data, fetch_market_data

# Fetch stock prices (cached locally)
stock = fetch_stock_data("EFX", start="2015-01-01")

# Fetch S&P 500 market data
market = fetch_market_data(start="2015-01-01")
```

## feature_engine

```python
from breachalpha.feature_engine import (
    BreachEvent,
    compute_features,
    compute_features_batch,
    classify_severity,
)

# Create a breach event
event = BreachEvent(
    company_name="Equifax",
    ticker="EFX",
    breach_date=pd.Timestamp("2017-09-07"),
    pwn_count=147_000_000,
    breach_type="data_leak",
    stock_data=stock_df,
    market_data=market_df,
)

# Compute features
features = compute_features(event)
# → BreachFeatures with AR, CAR, volatility, recovery metrics

# Batch compute
features_df = compute_features_batch([event1, event2])

# Classify severity from CAR
severity = classify_severity(-0.12)  # → "high"
```

## model

```python
from breachalpha.model import train_model, save_model, load_model, predict_severity

# Train model
result = train_model(features_df)
model = result["model"]
metrics = result["metrics"]

# Save/load
save_model(model, metrics, "my_model")
loaded_model = load_model("my_model")

# Predict
prediction = predict_severity(model, features_df.iloc[:1])
# → {"prediction": "high", "risk_score": 65.3, "confidence": 0.82, ...}
```

## CLI

```bash
# Demo with famous breaches
python -m breachalpha demo

# Train on breach data
python -m breachalpha train --data data/breaches.csv

# Score a company
python -m breachalpha score --company "Equifax" --breach-type "data-leak"
```
