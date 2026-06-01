# Decision Log

## 2026-06-01: curl_cffi over yfinance

**Decision:** Use curl_cffi with Chrome impersonation as primary Yahoo Finance fetcher instead of pure yfinance.

**Rationale:**
- Yahoo Finance started TLS fingerprint blocking yfinance
- curl_cffi bypasses via Chrome TLS + HTTP/2 fingerprint impersonation
- Same data source, same API, different HTTP layer
- Falls back to requests if curl_cffi not installed

---

## 2026-06-01: DuckDuckGo Web Search for Breach Data

**Decision:** Add DuckDuckGo HTML search as fallback for breach discovery when Yahoo Finance News returns no results.

**Rationale:**
- Yahoo Finance News has limited coverage of non-US breaches
- DuckDuckGo requires no API key, no rate limits for moderate usage
- HTML scraping is fragile but acceptable for optional enrichment
- Falls back gracefully on failure

---

## 2026-06-01: Date-Normalized Index Intersection

**Decision:** Normalize stock and market index timestamps to date-only (hour=0, minute=0) before intersection.

**Rationale:**
- Indian stocks (TATAPOWER.NS) have `03:45:00` timestamps (IST)
- US stocks/markets (^GSPC) have `14:30:00` timestamps (US/Eastern)
- Raw intersection returns 0 common dates → feature computation fails
- Normalization enables cross-exchange event studies

---

## 2026-05-31: LM Studio for LLM Enrichment

**Decision:** Add optional LLM layer via local LM Studio server.

**Rationale:**
- Enables natural language analysis of breach datasets
- Local inference, no API costs, no data leaving the machine
- Fully optional — core analysis works without it
- Graceful fallback when LM Studio is offline

---

## 2026-05-31: Initial Architecture

**Decision:** Build as FastAPI + React web app with modular Python backend.

**Rationale:**
- Web interface needed for dataset upload and visual results
- FastAPI provides auto-docs, validation, async request handling
- React + Tailwind for modern, responsive dashboard
- Business logic in pure Python modules, transport-agnostic

---

## 2026-05-31: Preprocessor with Auto-Column Detection

**Decision:** Build dataset preprocessor that auto-detects column names from 20+ naming variations.

**Rationale:**
- Breach datasets come from various sources with inconsistent column names
- Manual mapping is error-prone and annoying
- Auto-detection handles "Company", "Name", "Organization", "Victim", etc.
- Users can still override with column_mapping config

---

## 2026-05-31: Dataset Choice — HIBP via Kaggle

**Decision:** Use "Cyber Breach Analysis Dataset" from Kaggle (HIBP data, MIT license).

**Rationale:**
- Free, MIT licensed, well-structured CSV
- Has breach dates, company names, record counts
- Missing: ticker symbols (solved by ticker_resolver.py)

---

## 2026-05-31: Abnormal Return Model

**Decision:** Market-Adjusted Model (`AR = R_stock - R_market`) instead of OLS Market Model.

**Rationale:**
- Simpler — no estimation window regression required
- Used in ~15% of published event studies
- Good enough for MVP; OLS upgrade path exists

---

## 2026-05-31: XGBoost over LightGBM

**Decision:** XGBoost for severity classification.

**Rationale:**
- Level-wise growth less prone to overfitting on small datasets (~5K records)
- Better regularization options (gamma, min_child_weight, reg_alpha, reg_lambda)
- Larger community, more production use

---

## 2026-05-31: Batch Stock Fetching

**Decision:** Multi-ticker batch download via Yahoo Finance chart API.

**Rationale:**
- Sequential per-ticker fetching is slow for batch analysis
- Yahoo Finance chart API supports multi-symbol queries
- Falls back to sequential per-ticker on batch failure
