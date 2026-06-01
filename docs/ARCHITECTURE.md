# Architecture

## Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.12 + FastAPI | REST API server |
| Data | pandas + numpy + scikit-learn | Data processing |
| Model | XGBoost | Severity classification |
| Stock Data | YFinance (primary) + Alpha Vantage + NSE India + Yahoo scrape | Multi-source fallback |
| Stock Fetch | curl_cffi (Chrome impersonation) | Bypass TLS fingerprint blocking |
| Breach Search | Yahoo Finance News + DuckDuckGo HTML search | Internet breach lookup |
| LLM | LM Studio (local, qwen3.5-9b) | Optional enrichment layer |
| Frontend | React + Vite + Tailwind CSS + Chart.js | Web dashboard |
| Testing | pytest + pytest-cov | 87+ tests |

## Data Flow

```
User Input (company/ticker/file)
    ↓
┌─────────────────────────────────────────────────────────┐
│  ticker_search.py (Yahoo Finance + NSE India search)    │
│  breach_search.py (Yahoo News + DuckDuckGo web crawl)   │
│  ticker_resolver.py (local mapping + fuzzy match)       │
├─────────────────────────────────────────────────────────┤
│  data_sources.py / stock_loader.py (multi-source fetch) │
│    ├─ YFinance (primary, via curl_cffi)                 │
│    ├─ Alpha Vantage (API fallback)                      │
│    ├─ NSE India (Indian stocks)                         │
│    └─ Yahoo Finance Scrape (HTML fallback)              │
├─────────────────────────────────────────────────────────┤
│  feature_engine.py (event study: AR, CAR, volatility)   │
│    → Date-normalized indices for cross-exchange stocks  │
├─────────────────────────────────────────────────────────┤
│  model.py (XGBoost → severity prediction)               │
│  explainability.py (step-by-step breakdown)             │
├─────────────────────────────────────────────────────────┤
│  llm_integration.py (LM Studio enrichment) [optional]   │
└─────────────────────────────────────────────────────────┘
    ↓
Response (risk score, features, severity, probabilities)
```

## Module Dependencies

```
server.py
  ├── ticker_resolver.py
  ├── ticker_search.py
  ├── breach_search.py
  ├── stock_loader.py → data_sources.py
  │     └── YFinanceSource, AlphaVantageSource, NSEIndiaSource, YahooFinanceScrapeSource
  ├── feature_engine.py
  ├── model.py
  ├── preprocessor.py
  ├── explainability.py
  └── llm_integration.py
```

## Key Design Decisions

### Multi-Source Stock Data
- Primary: YFinance via curl_cffi with Chrome impersonation (bypasses Yahoo blocking)
- Fallback chain: NSE India → Alpha Vantage → Yahoo Finance HTML scrape
- Batch endpoint for multi-ticker fast download

### Cross-Exchange Stock Handling
- Timestamps normalized to date-only before common-date intersection
- Supports US stocks (S&P 500 benchmark) and Indian stocks (NIFTY 50)

### Internet Breach Search
- Sources: Yahoo Finance News + DuckDuckGo HTML search
- Resolves ticker inputs to company names automatically
- Extracts breach type, date, records affected from result snippets

### LLM Integration (Optional)
- Local LM Studio at 192.168.56.1:1234
- Graceful fallback when unavailable
- Used for: dataset analysis, risk summaries, Q&A, record enrichment

### Security
- Path traversal protection in SPA and training endpoints
- CORS restricted to localhost:3000
- Temp file cleanup via try/finally + os.unlink
- Thread-safe config via app.state (no global env mutation)
