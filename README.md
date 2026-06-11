# BreachAlpha

Quantify the financial impact of cybersecurity incidents on publicly traded companies.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)](https://react.dev/)
[![XGBoost](https://img.shields.io/badge/XGBoost-EC4B3E?)](https://xgboost.readthedocs.io/)
[![Tests](https://img.shields.io/badge/tests-144%20passing-brightgreen)](https://github.com/AshayK003/BreachAlpha)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/AshayK003/BreachAlpha?logo=github)](https://github.com/AshayK003/BreachAlpha)

BreachAlpha uses **event study methodology** (MacKinlay, 1997) to measure how breaches move stock prices.

```
Company: Equifax (EFX)          Breach: 2017-09-07
Risk Score: 72.5/100             Severity: HIGH
CAR (-5,+30): -18.34%            Volatility Spike: 2.4x
```

---

## Table of Contents

- [Why](#why)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Methodology](#methodology)
- [Data Sources](#data-sources)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Why

Security teams struggle to quantify breach impact in financial terms. Board members ask "how much will this cost?" and get vague answers. BreachAlpha provides a data-driven number grounded in how the market actually prices in breach events.

The approach is borrowed from event study methodology in financial economics — the same technique regulators and academics use to measure the impact of earnings announcements, mergers, and litigation on stock prices.

---

## Architecture

```
breachalpha/                  # Python backend (FastAPI + XGBoost)
├── server.py                 # FastAPI app, middleware, SPA catch-all
├── schemas.py                # 30+ Pydantic request/response models
├── core/
│   ├── constants.py          # Risk weights, feature columns, severity labels
│   ├── exceptions.py         # Domain exceptions (decoupled from HTTPException)
│   └── http.py               # Shared HTTP session, SSRF validation
├── services/
│   ├── model.py              # Model loading, synthetic training, batch scoring
│   ├── scoring.py            # Ticker validation, breach search, scoring pipeline
│   └── file_upload.py        # Upload validation, temp file management
├── routes/
│   ├── meta.py               # Health, demo, cache, data sources
│   ├── score.py              # /api/score, /api/score/auto, /api/score/config
│   ├── upload.py             # /api/upload, /api/upload/analyze
│   ├── explain.py            # /api/explain, /api/explain/auto
│   ├── search.py             # /api/search, /api/breach-search
│   ├── llm.py                # /api/llm/* (optional LLM enrichment)
│   └── admin.py              # /api/train, /api/data-sources/configure
├── breach_search.py          # Internet breach search (Yahoo News + DuckDuckGo)
├── ticker_resolver.py        # Company name → stock ticker (200+ mappings)
├── ticker_search.py          # Live ticker search (Yahoo Finance + NSE India)
├── stock_loader.py           # Multi-source stock data fetcher with caching
├── data_sources.py           # YFinance, Alpha Vantage, NSE India, Yahoo scrape
├── feature_engine.py         # Event study: AR, CAR, volatility, recovery
├── model.py                  # XGBoost severity classifier
├── preprocessor.py           # CSV/XLSX/Excel preprocessing pipeline
├── explainability.py         # Step-by-step calculation breakdown
├── llm_integration.py        # LM Studio client (optional)
└── cli.py                    # CLI: demo, train, score

frontend/                     # React + Vite + Tailwind CSS
├── src/
│   ├── App.jsx               # Dashboard: 4 tabs + LLM panel
│   ├── index.css             # Tailwind + terminal aesthetic
│   └── components/
│       ├── score/            # ScoreForm, RiskGauge, ProbabilityBar, FeaturesChart
│       ├── upload/           # FileUpload, DatasetPreview, BatchResults
│       ├── explain/          # ExplainabilityPanel
│       ├── llm/              # LLMAnalysisPanel
│       ├── demos/            # DemoCard
│       ├── settings/         # SettingsPanel
│       ├── layout/           # Header, TabBar, Footer
│       └── ui/               # shadcn/ui primitives
└── package.json

tests/                        # 144 tests across 11 modules
```

### Key design decisions

- **Domain exceptions decoupled from HTTP.** Services raise `BreachAlphaError` subclasses. A global handler in `server.py` translates them to HTTP status codes. This keeps business logic framework-agnostic.
- **Route modules are factory functions.** `create_score_routes(limiter) -> APIRouter` — the limiter is injected, not global.
- **Multi-source stock data.** If Yahoo Finance fails, the system falls back through Alpha Vantage → NSE India → Yahoo scraping. Each source has a `supports_ticker()` gate.
- **ProcessPoolExecutor for feature computation.** CPU-bound work bypasses the GIL via multiprocessing, not threading.
- **No TypeScript.** Matches the existing codebase. No added build complexity.

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm

### Optional

- [LM Studio](https://lmstudio.ai/) running on `192.168.56.1:1234` with a chat model (e.g., qwen3.5-9b) for LLM enrichment features.

---

## Setup

### Backend

```bash
# Clone the repo
git clone https://github.com/AshayK003/BreachAlpha.git
cd BreachAlpha

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Start the backend
uvicorn breachalpha.server:app --reload --port 8000
```

The API is now at `http://localhost:8000`. The model trains on synthetic data on first use (~2s).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:3000`. Vite proxies `/api` requests to `localhost:8000`.

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BREACHALPHA_ADMIN_KEY` | `""` (disabled) | Required for admin endpoints (`/api/train`, `/api/data-sources/configure`, `DELETE /api/cache`). When empty, these return 503. |
| `BREACHALPHA_LLM_URL` | `http://192.168.56.1:1234` | LM Studio server URL for optional LLM features. |
| `BREACHALPHA_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed CORS origins. |
| `ALPHA_VANTAGE_API_KEY` | `""` | Optional Alpha Vantage API key for stock data fallback. Free tier: 25 calls/day. |

---

## Local Development

### Running both servers

```bash
# Terminal 1: Backend (hot-reload)
uvicorn breachalpha.server:app --reload --port 8000

# Terminal 2: Frontend (hot-reload)
cd frontend && npm run dev
```

The frontend dev server at `:3000` proxies API calls to `:8000` via Vite config.

### CLI usage

```bash
# Run demo with 3 famous breaches (Equifax, Capital One, Marriott)
breachalpha demo

# Score a company
breachalpha score --company Equifax

# Train on a real breach dataset
breachalpha train --data data/breaches.csv
```

### Loading the model

The model trains automatically on synthetic data if no trained model exists. This takes ~2 seconds and produces a basic classifier. For better accuracy, train on real breach data via the admin endpoint or CLI.

---

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=breachalpha --cov-report=term-missing

# Run a specific test file
pytest tests/test_routes_api.py -v

# Run a specific test
pytest tests/test_routes_api.py::test_score_company -v
```

The test suite covers:
- Data loading, preprocessing, and feature computation
- Model training, prediction, and batch scoring
- Ticker resolution and validation
- API endpoint behavior (via httpx AsyncClient)
- File upload validation
- Security middleware (admin auth, rate limiting)

### Coverage threshold

The project enforces a minimum of 60% coverage (`pyproject.toml`). Run with `--cov-fail-under=60` in CI.

---

## API Reference

### Core Endpoints

| Method | Endpoint | Rate Limit | Description |
|--------|----------|------------|-------------|
| GET | `/api/health` | — | Health check + model status |
| POST | `/api/score` | 10/min | Score a single company |
| POST | `/api/score/config` | 10/min | Score with custom analysis config |
| POST | `/api/score/auto` | 5/min | Auto-search breach data and score |
| GET | `/api/search` | 30/min | Search stock tickers |
| GET | `/api/breach-search` | 10/min | Search breach incidents |
| GET | `/api/demo` | — | Demo with 3 famous breaches |
| POST | `/api/explain` | 10/min | Explainability report |
| POST | `/api/explain/auto` | 5/min | Auto-search + explain |

### Upload Endpoints

| Method | Endpoint | Rate Limit | Description |
|--------|----------|------------|-------------|
| POST | `/api/upload` | 10/min | Upload & preprocess dataset |
| POST | `/api/upload/analyze` | 5/min | Upload + batch analyze |

### LLM Endpoints (requires LM Studio)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/llm/status` | Check LLM availability |
| POST | `/api/llm/analyze-dataset` | AI analysis of batch results |
| POST | `/api/llm/risk-summary` | AI risk summary |
| POST | `/api/llm/ask` | Q&A about breach data |
| POST | `/api/llm/enrich` | Enrich records with LLM |

### Admin Endpoints (requires `X-Admin-Key` header)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/train` | Train model on breach CSV |
| POST | `/api/data-sources/configure` | Configure data sources |
| DELETE | `/api/cache` | Clear stock cache |

### Example: Score a Company

```bash
curl -X POST http://localhost:8000/api/score \
  -H "Content-Type: application/json" \
  -d '{"company": "Equifax", "breach_type": "data_leak", "records_affected": 147000000, "breach_date": "2017-09-07"}'
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

---

## Methodology

### Event Study (MacKinlay, 1997)

1. **Abnormal Return:** `AR = R_stock - R_market` — isolate breach-specific impact from market movement
2. **Cumulative AR:** `CAR = Σ AR` over event window — total breach impact over time
3. **Features:** AR at Day 0/1/5/30, CAR windows (-1,+1) and (-5,+30), volatility spike, volume change, recovery time, breach size
4. **Model:** XGBoost classifier trained to predict severity (Low/Medium/High/Critical)
5. **Risk Score:** Weighted probability sum mapped to 0-100: `Low(10)×P(low) + Medium(35)×P(medium) + High(65)×P(high) + Critical(95)×P(critical)`

### Why Event Study?

The market aggregates all available information into stock prices. When a breach is disclosed, the price change reflects the market's assessment of the financial damage — accounting for company size, sector, market conditions, and breach specifics. This is more robust than estimating costs from headline numbers alone.

---

## Data Sources

| Source | Tickers | Fallback Priority | Notes |
|--------|---------|-------------------|-------|
| yfinance (curl_cffi) | All | 1 (primary) | Uses Chrome TLS fingerprint to bypass blocks |
| Alpha Vantage | All | 2 | Requires free API key. 25 calls/day. |
| NSE India | `.NS`, `.BO` | 3 | Direct API for Indian stocks |
| Yahoo Finance scrape | All | 4 | HTML scraping fallback |

The system automatically tries each source in priority order. Stock data is cached locally in `data/stock_cache/` (24h TTL).

### Ticker Resolution

BreachAlpha maps company names to tickers using:
1. A hardcoded dictionary of 200+ companies (US, India, Europe, Asia)
2. Live search via Yahoo Finance and NSE India
3. Indian stock suffix detection (`.NS`, `.BO`)

---

## Deployment

### Production build

```bash
# Build frontend
cd frontend
npm run build
cd ..

# Start backend (serves SPA from frontend/dist)
uvicorn breachalpha.server:app --host 0.0.0.0 --port 8000
```

When `frontend/dist/` exists, the backend serves it as static files with SPA catch-all routing.

### Docker (recommended)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"
RUN cd frontend && npm install && npm run build
EXPOSE 8000
CMD ["uvicorn", "breachalpha.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production considerations

- **Admin auth:** Set `BREACHALPHA_ADMIN_KEY` to a strong secret. Admin endpoints return 503 without it.
- **CORS:** Set `BREACHALPHA_CORS_ORIGINS` to your production domain.
- **Rate limiting:** Default 120 req/min per IP. Adjust in `server.py` if needed.
- **Stock cache:** Stored in `data/stock_cache/`. Persist this volume across deployments to avoid re-fetching.
- **Model:** Trains on synthetic data if no trained model exists. Train on real data in production for better accuracy.
- **LLM:** Optional. Requires LM Studio running separately. The backend works fully without it.

---

## Troubleshooting

### "No stock data available for TICKER"

The ticker couldn't be resolved or Yahoo Finance returned no data. Check:
- Is the ticker valid? Try `curl localhost:8000/api/search?q=COMPANY`
- Is the company in `KNOWN_TICKERS` (`ticker_resolver.py`)? Add it if missing.
- For Indian stocks, use `.NS` suffix (e.g., `TCS.NS`).

### "Insufficient data around breach date"

Fewer than 30 trading days of stock data around the breach date. Common causes:
- Breach date is too recent (not enough post-breach data)
- Company is thinly traded or delisted
- Try extending `start_date` in Settings

### Admin endpoints return 503

`BREACHALPHA_ADMIN_KEY` is not set. Set it:

```bash
export BREACHALPHA_ADMIN_KEY="your-secret-key"
curl -H "X-Admin-Key: your-secret-key" -X POST http://localhost:8000/api/train ...
```

### LLM features not working

The LLM panel shows "Connect LM Studio" — the backend can't reach `BREACHALPHA_LLM_URL`. Ensure:
1. LM Studio is running
2. A model is loaded
3. The URL is correct (`http://192.168.56.1:1234` by default)

### Frontend build fails

```bash
cd frontend
rm -rf node_modules
npm install
npm run build
```

### Tests fail with import errors

```bash
pip install -e ".[dev]"
```

Make sure you're in the project root and the virtual environment is activated.

---

## Contributing

### Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make changes and add tests
4. Run `pytest` — all 144 tests must pass
5. Run `pytest --cov=breachalpha --cov-fail-under=60` — coverage must not drop
6. Submit a pull request

### Code conventions

- **Python:** Follow existing style. No type annotations on internal helpers unless they add clarity.
- **Frontend:** Plain JavaScript (no TypeScript). Functional components with hooks. shadcn/ui primitives.
- **Tests:** Write tests for new features. Aim for behavior coverage, not line coverage.
- **Commit messages:** Short imperative: "add SSRF validation", "fix CSV injection", "remove dead code"

### Adding a new API endpoint

1. Create a route function in the appropriate `routes/*.py` file
2. Add request/response models to `schemas.py`
3. Add domain exceptions to `core/exceptions.py` if needed
4. Register the route in `server.py` via the factory pattern
5. Write tests in `tests/test_routes_api.py`

### Adding a new data source

1. Subclass `DataSource` in `data_sources.py`
2. Implement `fetch()`, `supports_ticker()`, and `name`
3. Add it to `DataFetcher.sources` and `FetcherConfig.sources_priority`
4. Write tests in a new `test_data_sources.py`

---

## License

MIT
