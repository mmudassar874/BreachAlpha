# Changelog

## [0.2.0] — 2026-06-01

### Added
- **breach_search**: Internet breach search via Yahoo Finance News + DuckDuckGo web crawl
  - Ticker-to-company name resolution (TATAPOWER.NS → "Tata Power")
  - Extracts breach type, date, records affected from search snippets
  - Multiple query variations for better coverage
- **ticker_search**: Real-time ticker search (Yahoo Finance + NSE India + fallback chain)
  - Debounced frontend search with client-side cache
  - Live price verification
- **llm_integration**: LM Studio LLM client for optional enrichment
  - Dataset analysis, risk summaries, Q&A, record enrichment
  - Graceful fallback when LM Studio is offline
- **data_sources**: Multi-source stock data fetcher with fallback chain
  - YFinance (via curl_cffi Chrome impersonation)
  - Alpha Vantage, NSE India, Yahoo Finance HTML scrape
  - Batch multi-ticker download via Yahoo Finance chart API
- **server endpoints**: 12 new REST endpoints
  - `/api/search` — ticker search
  - `/api/breach-search` — breach incident search
  - `/api/llm/*` — LLM analysis, risk summary, Q&A, enrichment
  - `/api/data-sources/*` — data source config, test, status
  - `/api/cache` — stock cache info, clear
  - `/api/config/presets` — analysis configuration presets
- **frontend features**:
  - Settings tab with analysis presets and data source configuration
  - LLM analysis panel in upload results
  - Breach search with auto-fill date/type/records
  - Ticker search with debounce and live price display

### Fixed
- **feature_engine**: Cross-exchange timestamp normalization
  - Stock and market indices normalized to date-only before intersection
  - Fixes "Insufficient data around breach date" for Indian stocks (TATAPOWER.NS)
  - Common dates: 0 → 2728 (TATAPOWER.NS vs ^GSPC)
- **server**: Path traversal protection in SPA catch-all and training endpoint
- **server**: CORS restricted to localhost:3000
- **server**: Thread-safe config via app.state (replaced global env mutation)
- **server**: Temp file cleanup across all upload endpoints

### Changed
- YFinance fetcher uses curl_cffi with Chrome impersonation by default
- Batch stock download replaces sequential per-ticker fetching
- Preprocessor validates dataset presence before batch analysis

## [0.1.0] — 2026-05-31

### Added
- **breach_loader**: Parse HIBP breach CSVs, filter by record count, deduplicate
- **ticker_resolver**: Map company names to stock tickers (200+ mappings)
- **stock_loader**: Fetch and cache historical stock prices via yfinance
- **feature_engine**: Compute abnormal returns, CAR, volatility spikes, recovery time
- **model**: XGBoost classifier for impact severity (Low/Medium/High/Critical)
- **preprocessor**: Dataset preprocessing pipeline for CSV, XLSX, Excel, TSV files
- **explainability**: Step-by-step calculation breakdown with formulas, inputs, outputs
- **server**: FastAPI REST API with 9 endpoints
- **frontend**: React + Vite + Tailwind CSS dashboard with 4 tabs
- **cli**: `demo`, `train`, `score` commands
- Test suite: 87 tests across 7 modules
- Documentation: README, ARCHITECTURE, API, TESTING, CONTRIBUTING, DECISIONS
