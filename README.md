# BreachAlpha — Cyber-Financial Risk Quantifier

Quantify the financial impact of cybersecurity incidents on publicly traded companies.

## Architecture

```
breachalpha/              # Python backend (FastAPI + XGBoost)
├── breach_loader.py      # Parse HIBP breach CSVs
├── ticker_resolver.py    # Company name → stock ticker
├── stock_loader.py       # Fetch/cache prices via yfinance
├── feature_engine.py     # Event study: AR, CAR, volatility
├── model.py              # XGBoost severity classifier
├── preprocessor.py       # Dataset preprocessing pipeline
├── explainability.py     # Step-by-step calculation breakdown
├── server.py             # FastAPI REST API
└── cli.py                # CLI interface

frontend/                 # React + Vite + Tailwind CSS
├── src/
│   ├── App.jsx           # Full dashboard with 3 tabs
│   └── index.css         # Tailwind + custom styles
└── package.json
```

## Quick Start

### Backend

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the API server
uvicorn breachalpha.server:app --reload --port 8000

# Or use CLI
python -m breachalpha demo
python -m breachalpha score --company "Equifax" --breach-type "data-leak"
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### Run Both

```bash
# Terminal 1: Backend
uvicorn breachalpha.server:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check + model status |
| POST | `/api/score` | Score a single company |
| GET | `/api/demo` | Run demo with 3 famous breaches |
| POST | `/api/train` | Train model on breach CSV data |
| POST | `/api/upload` | Upload & preprocess a dataset (CSV/XLSX/Excel) |
| POST | `/api/upload/analyze` | Upload dataset + analyze all breaches |
| POST | `/api/explain` | Full explainability report with calculation steps |

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

## Testing

```bash
# Run all tests (87 tests)
pytest

# With coverage
pytest --cov=breachalpha --cov-report=term-missing

# Run API tests only
pytest tests/test_server.py -v
```

## Data Sources

| Dataset | Source | License |
|---------|--------|---------|
| Breach Records | [HIBP via Kaggle](https://www.kaggle.com/datasets/gojoyuno/cyber-breach-analysis-dataset) | MIT |
| Stock Prices | Yahoo Finance (yfinance) | Free |
| Market Benchmark | S&P 500 (`^GSPC`) | via yfinance |

## Methodology

Uses the **event study methodology** (MacKinlay, 1997):

1. **Abnormal Return:** `AR = R_stock - R_market` (Market-Adjusted Model)
2. **Cumulative AR:** `CAR = Σ AR` over event window
3. **Features:** AR at Day 0/1/5/30, CAR windows, volatility spike, volume change, recovery time
4. **Model:** XGBoost classifier → severity (Low/Medium/High/Critical)
5. **Risk Score:** Weighted probability sum (0-100)

## Development

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for development guide.

## License

MIT
