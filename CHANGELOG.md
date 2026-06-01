# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] — 2026-05-31

### Added
- **breach_loader**: Parse HIBP breach CSVs, filter by record count, deduplicate
- **ticker_resolver**: Map company names to stock tickers (120+ hardcoded mappings)
- **stock_loader**: Fetch and cache historical stock prices via yfinance
- **feature_engine**: Compute abnormal returns, CAR, volatility spikes, recovery time
- **model**: XGBoost classifier for impact severity (Low/Medium/High/Critical)
- **preprocessor**: Dataset preprocessing pipeline for CSV, XLSX, Excel, TSV files
  - Auto-detect column names (handles 20+ naming variations)
  - Robust date parsing (10+ formats)
  - Numeric parsing (commas, currency symbols, K/M/B suffixes)
  - Automatic ticker resolution
- **explainability**: Step-by-step calculation breakdown with formulas, inputs, outputs
  - Daily return explanation
  - Abnormal return explanation (stock vs market)
  - CAR explanation with window details
  - Volatility spike explanation
  - Volume change explanation
  - Severity classification explanation
  - Risk score formula breakdown
  - Feature contribution analysis
  - Methodology and limitations disclosure
- **server**: FastAPI REST API with 7 endpoints
  - POST /api/score — single company analysis
  - GET /api/demo — famous breach demo
  - POST /api/train — model training
  - POST /api/upload — dataset preprocessing
  - POST /api/upload/analyze — batch analysis
  - POST /api/explain — full explainability report
- **frontend**: React + Vite + Tailwind CSS dashboard
  - Single Analysis tab with company search + demo cards
  - Upload Dataset tab with drag-and-drop + preview + batch results
  - Explain Score tab with step-by-step calculation breakdown
  - Risk gauge, probability bars, feature cards, abnormal returns chart
  - CSV export for batch results
- **cli**: `demo`, `train`, `score` commands
- Test suite: 87 tests across 7 modules
- Documentation: README, ARCHITECTURE, API, TESTING, CONTRIBUTING, DECISIONS
