# Architecture Decisions

## Why This Stack

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.10+ | Standard for data science, largest ecosystem |
| Data | pandas + numpy | De facto standard, battle-tested |
| Stock data | yfinance | 19M+ monthly downloads, Apache-2.0, active maintenance |
| Model | XGBoost | Conservative defaults for small datasets (~5K records), excellent regularization |
| Metrics | scikit-learn | Industry standard for model evaluation |
| Interface | CLI | MVP-first; no web framework overhead |

## Why Not...

| Alternative | Rejected Because |
|---|---|
| LightGBM | Leaf-wise growth overfits more on small datasets |
| FastAPI/web UI | No users yet; CLI is sufficient for MVP |
| PostgreSQL/SQLite | CSVs + in-memory pandas handles 5K records fine |
| Docker | Local dev first; add when deploying |
| Cloud APIs | yfinance is free; cloud stock APIs cost money |
| SEC EDGAR integration | Not needed for MVP — breach dates + stock prices are sufficient |

## Data Flow

```
breaches.csv
    ↓
breach_loader.py (filter public companies)
    ↓
ticker_resolver.py (company name → ticker)
    ↓
stock_loader.py (fetch + cache prices)
    ↓
feature_engine.py (compute AR, CAR, volatility, recovery)
    ↓
model.py (train XGBoost, predict severity)
    ↓
CLI output (risk score + explanation)
```

## Separation of Concerns

- **Data ingestion** (breach_loader, stock_loader) is isolated from analysis
- **Feature engineering** (feature_engine) is pure functions — easy to test
- **Model** (model.py) consumes features, produces scores — no data fetching
- **CLI** (cli.py) is thin — just parses args and calls the right functions

## Trade-offs

### Accepted
- yfinance is a scraper, not an official API — could break. Mitigated by local caching.
- Market-Adjusted Model (AR = stock - market) is simpler than OLS market model. Acceptable for MVP; upgrade path exists.
- Manual ticker mapping for ~200 public companies. One-time cost.

### Deferred
- SEC filing text analysis (8-K Item 1.05 disclosures)
- International stock exchanges
- Real-time scoring
- Web interface
- Authentication / multi-user
