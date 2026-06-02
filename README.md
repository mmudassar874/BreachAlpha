# BreachAlpha — Cyber-Financial Risk Quantifier

Quantify the financial impact of cybersecurity incidents on publicly traded companies. Uses event study methodology with multi-source stock data, internet breach search, and optional LLM enrichment.

## Architecture

```
breachalpha/              # Python backend (FastAPI + XGBoost)
├── server.py             # FastAPI REST API (20+ endpoints)
├── breach_search.py      # Internet breach search (Yahoo News + DuckDuckGo)
├── breach_loader.py      # Parse HIBP breach CSVs
├── ticker_resolver.py    # Company name → stock ticker (200+ mappings)
├── ticker_search.py      # Ticker search (Yahoo Finance + NSE India)
├── stock_loader.py       # Fetch/cache prices with multi-source fallback
├── data_sources.py       # YFinance, Alpha Vantage, NSE India, Yahoo scrape
├── feature_engine.py     # Event study: AR, CAR, volatility, recovery
├── model.py              # XGBoost severity classifier
├── preprocessor.py       # Dataset preprocessing pipeline
├── explainability.py     # Step-by-step calculation breakdown
├── llm_integration.py    # LM Studio LLM client (optional enrichment)
└── cli.py                # CLI interface

frontend/                 # React + Vite + Tailwind CSS
├── src/
│   ├── App.jsx           # Dashboard with 4 tabs + LLM analysis
│   └── index.css         # Tailwind + custom styles
└── package.json
```

## Quick Start

### Backend

```bash
pip install -e ".[dev]"
uvicorn breachalpha.server:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### Optional: LLM Enrichment

Run [LM Studio](https://lmstudio.ai/) on `192.168.56.1:1234` with a chat model (e.g., qwen3.5-9b) for dataset analysis, risk summaries, and Q&A.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check + model status |
| POST | `/api/score` | Score a single company |
| POST | `/api/score/config` | Score with custom analysis config |
| GET | `/api/search` | Search stock tickers from internet |
| GET | `/api/breach-search` | Search breach incidents from internet |
| GET | `/api/demo` | Run demo with 3 famous breaches |
| POST | `/api/train` | Train model on breach CSV data (admin) |
| POST | `/api/upload` | Upload & preprocess a dataset (CSV/XLSX/Excel) |
| POST | `/api/upload/analyze` | Upload dataset + batch analyze all breaches |
| POST | `/api/explain` | Full explainability report with calculation steps |
| GET | `/api/config/presets` | Analysis configuration presets |
| GET | `/api/data-sources` | Data source status |
| POST | `/api/data-sources/configure` | Configure data sources (admin) |
| GET | `/api/data-sources/test/{source}` | Test a data source |
| GET | `/api/cache` | Stock cache info |
| DELETE | `/api/cache` | Clear stock cache (admin) |
| GET | `/api/llm/status` | LLM availability check |
| POST | `/api/llm/analyze-dataset` | LLM dataset analysis |
| POST | `/api/llm/risk-summary` | LLM risk summary |
| POST | `/api/llm/ask` | LLM Q&A about breach data |
| POST | `/api/llm/enrich` | LLM enrichment of records |

### POST /api/score

```json
{
  "company": "Equifax",
  "breach_type": "data_leak",
  "records_affected": 147000000,
  "breach_date": "2017-09-07"
}
```

Response:
```json
{
  "company": "Equifax",
  "ticker": "EFX",
  "risk_score": 72.5,
  "prediction": "high",
  "confidence": 0.84,
  "probabilities": {"low": 0.02, "medium": 0.10, "high": 0.72, "critical": 0.16},
  "features": {
    "abnormal_return_day0": -0.0921,
    "car_minus5_plus30": -0.1834,
    "volatility_spike": 2.4,
    "time_to_recovery": 45
  }
}
```

## Breach Search Flow

1. Type a company name or ticker (e.g., `TATAPOWER.NS`, `MSFT`, `Reliance`)
2. Click **"Find Breach Data from Internet"** — searches Yahoo Finance News + DuckDuckGo
3. Click a breach incident to auto-fill date, type, and records
4. Click **"Analyze Risk"** — computes event study features and predicts severity

## Data Sources

| Source | Description | Requires |
|--------|-------------|----------|
| yfinance | Primary stock data (Yahoo Finance API) | Nothing |
| curl_cffi (Chrome) | Yahoo Finance with TLS fingerprint bypass | `pip install curl_cffi` |
| Alpha Vantage | Official stock API (fallback) | Free API key |
| NSE India | Indian stocks direct | Nothing |
| Yahoo Finance Scrape | HTML scraping fallback | curl_cffi |

## Testing

```bash
pytest                              # 87+ tests
pytest --cov=breachalpha --cov-report=term-missing
pytest tests/test_server.py -v      # API tests only
```

## Performance

The analysis pipeline (`/api/upload/analyze`) uses parallel processing for speed:

- **Parallel I/O:** Stock data and market data fetched concurrently via `ThreadPoolExecutor(8)`
- **Parallel CPU:** Feature computation uses `ProcessPoolExecutor` (bypasses GIL)
- **Batch prediction:** Single `model.predict()` call instead of per-row loop
- **Event loop:** Full pipeline runs in `asyncio.to_thread()` — doesn't block other requests

Expected speedup: ~4x for 10-row datasets, ~7x for 50 rows, ~10x for 200 rows.

## Security

Admin endpoints (`/api/train`, `/api/data-sources/configure`, `DELETE /api/cache`) require the `BREACHALPHA_ADMIN_KEY` environment variable. When not set, these endpoints return **503 Service Unavailable**.

```bash
export BREACHALPHA_ADMIN_KEY="your-secret-key"
# Then pass via header: X-Admin-Key: your-secret-key
```

## Methodology

Uses the **event study methodology** (MacKinlay, 1997):

1. **Abnormal Return:** `AR = R_stock - R_market` (Market-Adjusted Model)
2. **Cumulative AR:** `CAR = Σ AR` over event window
3. **Features:** AR at Day 0/1/5/30, CAR windows, volatility spike, volume change, recovery time
4. **Model:** XGBoost classifier → severity (Low/Medium/High/Critical)
5. **Risk Score:** Weighted probability sum (0-100)

## License

MIT
