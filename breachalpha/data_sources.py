"""Multi-source stock data fetcher.

Fetches real-time and historical stock data from multiple sources:
1. yfinance (primary — uses curl_cffi for browser impersonation)
2. Alpha Vantage (official API, free tier)
3. NSE India / BSE India (Indian stocks)
4. Web scraping fallback (Yahoo Finance)

Usage:
    fetcher = DataFetcher(alpha_vantage_key="YOUR_KEY")
    df = fetcher.fetch("MSFT", start="2020-01-01")
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data" / "stock_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_browser_session():
    """Get a curl_cffi session that impersonates Chrome browser.

    curl_cffi bypasses TLS fingerprinting blocks that regular requests cannot.
    """
    try:
        from curl_cffi import requests as curl_requests
        session = curl_requests.Session(impersonate="chrome")
        return session, True
    except ImportError:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        })
        return session, False


# ── Data Source Interface ───────────────────────────────────────────────


class DataSource(ABC):
    """Abstract base class for stock data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name."""

    @abstractmethod
    def fetch(
        self,
        ticker: str,
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Fetch historical stock data. Returns DataFrame with OHLCV columns."""

    @abstractmethod
    def supports_ticker(self, ticker: str) -> bool:
        """Check if this source can handle the given ticker."""

    def fetch_batch(
        self,
        tickers: list[str],
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple tickers. Default: sequential calls."""
        return {t: self.fetch(t, start, end) for t in tickers}


# ── yfinance Source ─────────────────────────────────────────────────────


class YFinanceSource(DataSource):
    """Primary source using direct HTTP with browser impersonation.

    Uses curl_cffi to impersonate Chrome at the TLS fingerprint level.
    This bypasses Yahoo Finance's anti-bot measures that block regular requests.
    """

    ENDPOINTS = [
        "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        "https://query2.finance.yahoo.com/v8/finance/chart/{ticker}",
    ]

    @property
    def name(self) -> str:
        return "yfinance"

    def supports_ticker(self, ticker: str) -> bool:
        return True

    def fetch(
        self,
        ticker: str,
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        start_ts = int(pd.Timestamp(start).timestamp())
        end_ts = int(pd.Timestamp(end).timestamp()) if end else int(time.time())

        params = {
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
            "events": "history",
        }

        session, is_curl = _get_browser_session()

        for endpoint in self.ENDPOINTS:
            url = endpoint.format(ticker=quote(ticker))
            for attempt in range(2):
                try:
                    if is_curl:
                        resp = session.get(url, params=params, timeout=20)
                    else:
                        resp = session.get(
                            url, params=params, timeout=20,
                            headers={
                                "Referer": f"https://finance.yahoo.com/quote/{ticker}",
                                "Accept": "*/*",
                            },
                        )

                    # Check for HTML error page
                    content_type = resp.headers.get("content-type", "")
                    text = resp.text[:200]
                    if "text/html" in content_type or text.startswith("<!"):
                        logger.debug("Yahoo returned HTML from %s", endpoint)
                        break  # Try next endpoint

                    data = resp.json()
                    result = data.get("chart", {}).get("result", [])
                    if not result:
                        break

                    timestamps = result[0].get("timestamp")
                    if not timestamps:
                        break

                    q = result[0].get("indicators", {}).get("quote", [{}])
                    if not q:
                        break

                    df = pd.DataFrame({
                        "Open": q[0].get("open", []),
                        "High": q[0].get("high", []),
                        "Low": q[0].get("low", []),
                        "Close": q[0].get("close", []),
                        "Volume": q[0].get("volume", []),
                    }, index=pd.to_datetime(timestamps, unit="s"))

                    df = df.dropna()
                    if len(df) > 0:
                        return df

                except Exception as e:
                    logger.debug("Yahoo attempt failed: %s", e)
                    time.sleep(1)

        return pd.DataFrame()

    def fetch_batch(
        self,
        tickers: list[str],
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Batch download multiple tickers using Yahoo Finance multi-ticker API.

        Uses the chart endpoint with multiple symbols for faster downloads.
        """
        if not tickers:
            return {}

        session, _ = _get_browser_session()
        start_ts = int(pd.Timestamp(start).timestamp())
        end_ts = int(pd.Timestamp(end).timestamp()) if end else int(time.time())

        results = {}

        # Try batch download first (single request for all tickers)
        try:
            from urllib.parse import quote
            symbols = ",".join(quote(t) for t in tickers)
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbols}"
            params = {
                "period1": start_ts,
                "period2": end_ts,
                "interval": "1d",
                "events": "history",
            }
            resp = session.get(url, params=params, timeout=30)

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and not resp.text.startswith("<!"):
                data = resp.json()
                chart = data.get("chart", {})

                # Handle single vs multi-ticker response
                if "result" in chart:
                    for result in chart["result"]:
                        symbol = result.get("meta", {}).get("symbol", "")
                        timestamps = result.get("timestamp")
                        if not symbol or not timestamps:
                            continue

                        q = result.get("indicators", {}).get("quote", [{}])
                        if not q:
                            continue

                        df = pd.DataFrame({
                            "Open": q[0].get("open", []),
                            "High": q[0].get("high", []),
                            "Low": q[0].get("low", []),
                            "Close": q[0].get("close", []),
                            "Volume": q[0].get("volume", []),
                        }, index=pd.to_datetime(timestamps, unit="s")).dropna()

                        if len(df) > 0:
                            results[symbol] = df
                            self._write_cache(symbol, "yfinance", df)

                if results:
                    logger.info("Batch downloaded %d tickers", len(results))
                    return results

        except Exception as e:
            logger.warning("Batch download failed, falling back to sequential: %s", e)

        # Fallback: sequential with caching
        for ticker in tickers:
            cached = self._read_cache(ticker, "yfinance") if hasattr(self, '_read_cache') else None
            if cached is not None:
                results[ticker] = cached
            else:
                df = self.fetch(ticker, start, end)
                if not df.empty:
                    results[ticker] = df

        return results


# ── Alpha Vantage Source ────────────────────────────────────────────────


class AlphaVantageSource(DataSource):
    """Official Alpha Vantage API — free tier: 25 calls/day, 5/min."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ALPHA_VANTAGE_API_KEY", "")

    @property
    def name(self) -> str:
        return "alphavantage"

    def supports_ticker(self, ticker: str) -> bool:
        return bool(self.api_key)

    def fetch(
        self,
        ticker: str,
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        if not self.api_key:
            logger.warning("Alpha Vantage: No API key configured")
            return pd.DataFrame()

        try:
            params = {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": "full",
                "apikey": self.api_key,
            }
            resp = requests.get(self.BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if "Time Series (Daily)" not in data:
                logger.warning("Alpha Vantage: No data for %s — %s", ticker, data.get("Note", "unknown error"))
                return pd.DataFrame()

            ts = data["Time Series (Daily)"]
            df = pd.DataFrame.from_dict(ts, orient="index")
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # Rename columns
            col_map = {
                "1. open": "Open", "2. high": "High", "3. low": "Low",
                "4. close": "Close", "5. adjusted close": "Adj Close",
                "6. volume": "Volume",
            }
            df = df.rename(columns=col_map)
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Filter by date range
            start_dt = pd.Timestamp(start)
            df = df[df.index >= start_dt]
            if end:
                df = df[df.index <= pd.Timestamp(end)]

            return df[["Open", "High", "Low", "Close", "Volume"]].dropna()

        except Exception as e:
            logger.warning("Alpha Vantage failed for %s: %s", ticker, e)
            return pd.DataFrame()


# ── NSE India Source ────────────────────────────────────────────────────


class NSEIndiaSource(DataSource):
    """Direct NSE India API for Indian stocks."""

    BASE_URL = "https://www.nseindia.com/api/historical/cm/equity"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        self._initialized = False

    @property
    def name(self) -> str:
        return "nse_india"

    def supports_ticker(self, ticker: str) -> bool:
        return ticker.endswith(".NS") or ticker.endswith(".BO") or re.match(r"^[A-Z]{2,10}$", ticker)

    def _init_session(self):
        """Initialize session with NSE cookies."""
        if self._initialized:
            return
        try:
            self.session.get("https://www.nseindia.com", timeout=10)
            self._initialized = True
            time.sleep(0.5)
        except Exception as e:
            logger.warning("NSE session init failed: %s", e)

    def fetch(
        self,
        ticker: str,
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        self._init_session()

        # Extract symbol from ticker (remove .NS/.BO suffix)
        symbol = re.sub(r"\.(NS|BO)$", "", ticker).upper()

        try:
            params = {
                "symbol": symbol,
                "from": pd.Timestamp(start).strftime("%d-%m-%Y"),
                "to": (pd.Timestamp(end) if end else pd.Timestamp.now()).strftime("%d-%m-%Y"),
            }
            resp = self.session.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if "data" not in data or not data["data"]:
                return pd.DataFrame()

            records = []
            for item in data["data"]:
                records.append({
                    "Date": pd.Timestamp(item["date"]),
                    "Open": float(item["open"]),
                    "High": float(item["high"]),
                    "Low": float(item["low"]),
                    "Close": float(item["close"]),
                    "Volume": int(item.get("totalTradedVolume", 0)),
                })

            df = pd.DataFrame(records).set_index("Date").sort_index()
            return df

        except Exception as e:
            logger.warning("NSE India failed for %s: %s", symbol, e)
            return pd.DataFrame()


# ── Web Scraping Fallback ───────────────────────────────────────────────


class YahooFinanceScrapeSource(DataSource):
    """Scrape Yahoo Finance using curl_cffi browser impersonation.

    Fallback source when yfinance source fails.
    Uses the same API but with a fresh session.
    """

    ENDPOINTS = [
        "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        "https://query2.finance.yahoo.com/v8/finance/chart/{ticker}",
    ]

    @property
    def name(self) -> str:
        return "yahoo_scrape"

    def supports_ticker(self, ticker: str) -> bool:
        return True

    def fetch(
        self,
        ticker: str,
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        start_ts = int(pd.Timestamp(start).timestamp())
        end_ts = int(pd.Timestamp(end).timestamp()) if end else int(time.time())

        params = {
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
            "events": "history",
        }

        # Use a fresh session with different impersonation
        try:
            from curl_cffi import requests as curl_requests
            session = curl_requests.Session(impersonate="chrome110")
        except ImportError:
            session = requests.Session()
            session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

        for endpoint in self.ENDPOINTS:
            url = endpoint.format(ticker=quote(ticker))
            try:
                resp = session.get(url, params=params, timeout=20)

                content_type = resp.headers.get("content-type", "")
                text = resp.text[:200]
                if "text/html" in content_type or text.startswith("<!"):
                    continue

                data = resp.json()
                result = data.get("chart", {}).get("result", [])
                if not result:
                    continue

                timestamps = result[0].get("timestamp")
                if not timestamps:
                    continue

                q = result[0].get("indicators", {}).get("quote", [{}])
                if not q:
                    continue

                df = pd.DataFrame({
                    "Open": q[0].get("open", []),
                    "High": q[0].get("high", []),
                    "Low": q[0].get("low", []),
                    "Close": q[0].get("close", []),
                    "Volume": q[0].get("volume", []),
                }, index=pd.to_datetime(timestamps, unit="s"))

                df = df.dropna()
                if len(df) > 0:
                    return df

            except Exception as e:
                logger.debug("Yahoo scrape failed: %s", e)

        return pd.DataFrame()


# ── Multi-Source Fetcher ────────────────────────────────────────────────


@dataclass
class FetcherConfig:
    """Configuration for the multi-source fetcher."""
    primary_source: str = "yfinance"
    alpha_vantage_key: str = ""
    enable_fallback: bool = True
    cache_ttl_hours: int = 24
    sources_priority: list[str] = field(default_factory=lambda: [
        "yfinance", "alphavantage", "nse_india", "yahoo_scrape",
    ])


class DataFetcher:
    """Multi-source stock data fetcher with automatic fallback.

    Tries sources in priority order until one succeeds.
    Caches results locally to avoid repeated API calls.
    """

    def __init__(self, config: Optional[FetcherConfig] = None):
        if config is None:
            config = FetcherConfig()

        self.config = config
        self.sources: dict[str, DataSource] = {}

        # Initialize all sources
        yf_source = YFinanceSource()
        av_source = AlphaVantageSource(config.alpha_vantage_key)
        nse_source = NSEIndiaSource()
        yahoo_scrape = YahooFinanceScrapeSource()

        self.sources = {
            "yfinance": yf_source,
            "alphavantage": av_source,
            "nse_india": nse_source,
            "yahoo_scrape": yahoo_scrape,
        }

    def _cache_path(self, ticker: str, source: str) -> Path:
        safe_ticker = ticker.replace(".", "_").replace("^", "_")
        return CACHE_DIR / f"{safe_ticker}_{source}.csv"

    def _read_cache(self, ticker: str, source: str) -> Optional[pd.DataFrame]:
        path = self._cache_path(ticker, source)
        if not path.exists():
            return None
        try:
            age_hours = (time.time() - path.stat().st_mtime) / 3600
            if age_hours > self.config.cache_ttl_hours:
                return None
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            return df if not df.empty else None
        except Exception:
            return None

    def _write_cache(self, ticker: str, source: str, df: pd.DataFrame) -> None:
        try:
            df.to_csv(self._cache_path(ticker, source))
        except Exception as e:
            logger.warning("Cache write failed: %s", e)

    def fetch(
        self,
        ticker: str,
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Fetch stock data with automatic fallback across sources.

        Resolution strategy:
        1. Check cache (unless force_refresh)
        2. Try ticker as-is across all sources
        3. If ticker has no suffix, try .NS and .BO (Indian stocks)
        4. If ticker has .NS, also try .BO and vice versa
        """
        # Build list of tickers to try
        tickers_to_try = [ticker]

        # Auto-detect: if no known suffix, try Indian suffixes
        known_suffixes = (".NS", ".BO", ".L", ".DE", ".TO", ".HK", ".T", ".SS", ".SZ")
        if not any(ticker.upper().endswith(s) for s in known_suffixes):
            tickers_to_try.extend([ticker + ".NS", ticker + ".BO"])
        elif ticker.upper().endswith(".NS"):
            tickers_to_try.append(ticker[:-3] + ".BO")
        elif ticker.upper().endswith(".BO"):
            tickers_to_try.append(ticker[:-3] + ".NS")

        for try_ticker in tickers_to_try:
            result = self._fetch_single(try_ticker, start, end, force_refresh)
            if not result.empty:
                # Cache under original ticker too
                if try_ticker != ticker:
                    self._write_cache(ticker, "auto_resolved", result)
                return result

        logger.error("All sources failed for %s (tried: %s)", ticker, tickers_to_try)
        return pd.DataFrame()

    def _fetch_single(
        self,
        ticker: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp | None,
        force_refresh: bool,
    ) -> pd.DataFrame:
        """Fetch data for a single ticker across all sources."""
        # Check cache first
        if not force_refresh:
            for source_name in self.config.sources_priority:
                cached = self._read_cache(ticker, source_name)
                if cached is not None:
                    logger.debug("Cache hit for %s from %s", ticker, source_name)
                    return cached

        # Try each source in priority order
        for source_name in self.config.sources_priority:
            source = self.sources.get(source_name)
            if source is None or not source.supports_ticker(ticker):
                continue

            try:
                logger.info("Fetching %s from %s...", ticker, source_name)
                df = source.fetch(ticker, start, end)

                if df is not None and not df.empty:
                    self._write_cache(ticker, source_name, df)
                    logger.info("Success: %s from %s (%d rows)", ticker, source_name, len(df))
                    return df
                else:
                    logger.warning("No data from %s for %s", source_name, ticker)

            except Exception as e:
                logger.warning("Source %s failed for %s: %s", source_name, ticker, e)

            if not self.config.enable_fallback:
                break

        return pd.DataFrame()

    def fetch_market(
        self,
        benchmark: str = "^GSPC",
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Fetch market benchmark data."""
        return self.fetch(benchmark, start, end)

    def fetch_batch(
        self,
        tickers: list[str],
        start: str | pd.Timestamp = "2010-01-01",
        end: str | pd.Timestamp | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple tickers using batch download when possible."""
        if not tickers:
            return {}

        # Try primary source batch first
        primary = self.sources.get(self.config.sources_priority[0])
        if primary:
            try:
                results = primary.fetch_batch(tickers, start, end)
                if results:
                    return results
            except Exception as e:
                logger.warning("Primary batch failed: %s", e)

        # Fallback to sequential
        results = {}
        for ticker in tickers:
            results[ticker] = self.fetch(ticker, start, end)
        return results

    def get_source_status(self) -> dict:
        """Return status of all data sources."""
        status = {}
        for name, source in self.sources.items():
            status[name] = {
                "name": source.name,
                "available": True,
                "priority": self.config.sources_priority.index(name) if name in self.config.sources_priority else -1,
            }

        # Check Alpha Vantage key
        if not self.config.alpha_vantage_key:
            status["alphavantage"]["available"] = False
            status["alphavantage"]["reason"] = "No API key configured"

        return status

    def clear_cache(self, older_than_hours: Optional[int] = None) -> int:
        """Clear cached data."""
        count = 0
        for f in CACHE_DIR.glob("*.csv"):
            if older_than_hours is not None:
                age_hours = (time.time() - f.stat().st_mtime) / 3600
                if age_hours < older_than_hours:
                    continue
            f.unlink()
            count += 1
        return count


# ── Singleton instance ──────────────────────────────────────────────────

_default_fetcher: Optional[DataFetcher] = None


def get_fetcher(alpha_vantage_key: str = "") -> DataFetcher:
    """Get or create the default fetcher instance."""
    global _default_fetcher
    if _default_fetcher is None or (alpha_vantage_key and _default_fetcher.config.alpha_vantage_key != alpha_vantage_key):
        config = FetcherConfig(alpha_vantage_key=alpha_vantage_key)
        _default_fetcher = DataFetcher(config)
    return _default_fetcher
