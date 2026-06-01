# API Reference

## breach_loader

```python
from breachalpha.breach_loader import load_breaches, get_breach_summary

df = load_breaches("data/breaches.csv")
summary = get_breach_summary(df)
# → {"total_breaches": 500, "date_range": ("2017-01-01", "2024-12-31"), ...}
```

## ticker_resolver

```python
from breachalpha.ticker_resolver import resolve_ticker, resolve_all, load_overrides

ticker = resolve_ticker("Equifax")  # → "EFX"
ticker = resolve_ticker("Acme Corp", overrides={"acme corp": "ACME"})
resolutions = resolve_all(["Equifax", "Capital One", "Unknown Corp"])
```

## ticker_search

```python
from breachalpha.ticker_search import smart_resolve, verify_ticker, search_yahoo, search_nse

# Smart search across multiple sources
results = smart_resolve("Tata Power", limit=5)
# → [{"symbol": "TATAPOWER.NS", "name": "Tata Power Company Ltd", ...}]

# Verify a ticker exists
info = verify_ticker("TATAPOWER.NS")
# → {"symbol": "TATAPOWER.NS", "price": 485.5, "currency": "INR", ...}

# Direct Yahoo Finance search
results = search_yahoo("Reliance")

# Direct NSE India search
results = search_nse("Tata Power")
```

## breach_search

```python
from breachalpha.breach_search import search_breach_incidents, BreachIncident

# Search internet for breach incidents
incidents = search_breach_incidents("Tata Power", limit=5)
# → [BreachIncident(date="2022-10-14", breach_type="ransomware", ...)]

# Also works with ticker inputs (resolves to company name)
incidents = search_breach_incidents("TATAPOWER.NS")
incidents = search_breach_incidents("MSFT")
```

## stock_loader

```python
from breachalpha.stock_loader import fetch_stock_data, fetch_market_data, fetch_stock_batch

# Single stock (cached locally)
stock = fetch_stock_data("TATAPOWER.NS", start="2015-01-01")

# Batch fetch (optimized multi-ticker)
cache = fetch_stock_batch(["TCS.NS", "RELIANCE.NS", "WIPRO.NS"])

# Market benchmark (default: ^GSPC; use ^NSEI for Indian stocks)
market = fetch_market_data(start="2015-01-01")
market_in = fetch_market_data(start="2015-01-01", benchmark="^NSEI")
```

## data_sources

```python
from breachalpha.data_sources import DataFetcher, FetcherConfig

# Configure multi-source fetcher
config = FetcherConfig(
    primary_source="yfinance",
    alpha_vantage_key="demo",
    enable_fallback=True,
)
fetcher = DataFetcher(config)

# Auto-fallback chain
df = fetcher.fetch("TATAPOWER.NS", start="2024-01-01")

# Source status
status = fetcher.get_source_status()
# → {"YFinanceSource": {"available": True, "priority": 0}, ...}
```

## feature_engine

```python
from breachalpha.feature_engine import (
    BreachEvent, BreachFeatures, AnalysisConfig,
    compute_features, compute_features_batch, classify_severity,
)

event = BreachEvent(
    company_name="Tata Power",
    ticker="TATAPOWER.NS",
    breach_date=pd.Timestamp("2022-10-14"),
    pwn_count=1_000_000,
    breach_type="ransomware",
    stock_data=stock_df,
    market_data=market_df,
)

# Custom configuration
config = AnalysisConfig(
    estimation_window=250,
    pre_event_window=30,
    post_event_window=60,
    threshold_critical=-0.15,
    threshold_high=-0.07,
    threshold_medium=-0.02,
)

features = compute_features(event, config)
# → BreachFeatures with AR, CAR, volatility, recovery metrics

features_df = compute_features_batch([event1, event2])

severity = classify_severity(-0.12)  # → "high"
```

## model

```python
from breachalpha.model import train_model, save_model, load_model, predict_severity

result = train_model(features_df)
model = result["model"]
metrics = result["metrics"]

save_model(model, metrics, "my_model")
loaded_model = load_model("my_model")

prediction = predict_severity(model, features_df.iloc[:1])
# → {"prediction": "high", "risk_score": 65.3, "confidence": 0.82, ...}
```

## explainability

```python
from breachalpha.explainability import generate_explanation

report = generate_explanation(event, features, model)
# → ExplainabilityReport with steps, formulas, feature contributions
```

## preprocessor

```python
from breachalpha.preprocessor import preprocess_dataset, AnalysisConfig

config = AnalysisConfig(
    column_mapping={"Company": "company_name"},
    records_threshold=1000,
)
result = preprocess_dataset("data/breaches.csv", config)
# → PreprocessingResult with df, preview, warnings
```

## llm_integration

```python
from breachalpha.llm_integration import (
    LLMConfig, check_lm_studio,
    analyze_breach_dataset, generate_risk_summary,
    answer_breach_question, enrich_breach_records,
)

config = LLMConfig(base_url="http://192.168.56.1:1234/v1")

status = check_lm_studio(config)
# → {"available": True, "models": ["qwen3.5-9b"], ...}

analysis = analyze_breach_dataset(dataset_summary, analysis_results)
summary = generate_risk_summary(company, risk_score, prediction, features)
answer = answer_breach_question(question, context)
enriched = enrich_breach_records(records)
```

## CLI

```bash
python -m breachalpha demo
python -m breachalpha train --data data/breaches.csv
python -m breachalpha score --company "Equifax" --breach-type "data-leak"
```
