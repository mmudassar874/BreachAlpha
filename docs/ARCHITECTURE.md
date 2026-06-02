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
│    └─ All fetches parallelized (ThreadPoolExecutor)     │
├─────────────────────────────────────────────────────────┤
│  feature_engine.py (event study: AR, CAR, volatility)   │
│    → ProcessPoolExecutor (true parallelism, GIL-free)   │
│    → Date-normalized indices for cross-exchange stocks  │
├─────────────────────────────────────────────────────────┤
│  model.py (XGBoost → severity prediction)               │
│    → Batch prediction (single predict() call)           │
│  explainability.py (step-by-step breakdown)             │
├─────────────────────────────────────────────────────────┤
│  llm_integration.py (LM Studio enrichment) [optional]   │
└─────────────────────────────────────────────────────────┘
    ↓
Response (risk score, features, severity, probabilities)
```

## Performance Architecture

The `/api/upload/analyze` endpoint runs the full pipeline in `asyncio.to_thread()` to avoid blocking the FastAPI event loop. Inside the pipeline thread:

```
_run_analysis_pipeline():
  1. Ticker resolution    → ThreadPoolExecutor(8)   [I/O-bound, parallel]
  2. Stock batch fetch     → ThreadPoolExecutor(8)   [I/O-bound, parallel]
  3. Market data fetch     → ThreadPoolExecutor(8)   [I/O-bound, parallel]
  4. Feature computation   → ProcessPoolExecutor(4)  [CPU-bound, GIL-free]
  5. Severity prediction   → Batch predict() call    [single model call]
```

Thread/process limits: max 8 I/O threads, max 4 CPU processes. All parallel paths have sequential fallbacks for safety.

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

### Accessibility
- WCAG AA compliant contrast ratios (`text-dim` at `#708096` on dark backgrounds)
- Semantic HTML: `role="button"`, `aria-label`, `aria-expanded`, `aria-live`
- Keyboard navigation: all interactive elements respond to Enter and Space
- Responsive grids: `grid-cols-2 sm:grid-cols-4` for mobile breakpoints
- Form labels associated with inputs via `htmlFor`/`id` pairs
