"""Search for stock tickers from the internet.

Uses Yahoo Finance search API + NSE/BSE lookup to find tickers
for any company name or partial ticker input.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Indian stock suffixes to try
INDIAN_SUFFIXES = [".NS", ".BO", ".NSE", ".BSE"]

# Known Indian exchanges for suffix guessing
INDIAN_EXCHANGES = {
    "NSE": ".NS",
    "BSE": ".BO",
    "NSE India": ".NS",
    "Bombay": ".BO",
    "National Stock Exchange": ".NS",
}


def _get_browser_session():
    """Get curl_cffi session with browser impersonation."""
    try:
        from curl_cffi import requests as curl_requests
        return curl_requests.Session(impersonate="chrome")
    except ImportError:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        return session


def search_yahoo(query: str, limit: int = 10) -> list[dict]:
    """Search Yahoo Finance for a ticker by company name or symbol.

    Returns list of matches with: symbol, name, exchange, type, ticker_full
    """
    session = _get_browser_session()
    results = []

    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q": query,
            "quotesCount": limit,
            "newsCount": 0,
            "listsCount": 0,
            "enableFuzzyQuery": True,
        }

        resp = session.get(url, params=params, timeout=15)

        # Check for valid JSON
        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type or resp.text.startswith("<!"):
            logger.warning("Yahoo search returned HTML for query: %s", query)
            return _search_fallback(query, limit)

        data = resp.json()
        quotes = data.get("quotes", [])

        for q in quotes[:limit]:
            symbol = q.get("symbol", "")
            name = q.get("shortname", "") or q.get("longname", "")
            exchange = q.get("exchange", "")
            quote_type = q.get("quoteType", "")

            # Build full ticker with exchange suffix for Indian stocks
            ticker_full = symbol
            if exchange in ("NSI", "BSE"):
                suffix = ".NS" if exchange == "NSI" else ".BO"
                if not symbol.endswith((".NS", ".BO")):
                    ticker_full = symbol + suffix

            results.append({
                "symbol": symbol,
                "name": name,
                "exchange": exchange,
                "type": quote_type,
                "ticker_full": ticker_full,
            })

    except Exception as e:
        logger.warning("Yahoo search failed for '%s': %s", query, e)
        return _search_fallback(query, limit)

    return results


def _search_fallback(query: str, limit: int = 10) -> list[dict]:
    """Fallback search using Yahoo v6 quote endpoint."""
    session = _get_browser_session()
    results = []

    # Try direct ticker lookup
    try:
        # First try the query as-is
        tickers_to_try = [query.upper()]

        # If it looks like an Indian company, try with suffixes
        if not any(query.upper().endswith(s) for s in [".NS", ".BO", ".L", ".DE", ".TO"]):
            for suffix in INDIAN_SUFFIXES:
                tickers_to_try.append(query.upper() + suffix)

        for ticker in tickers_to_try[:5]:
            url = f"https://query1.finance.yahoo.com/v6/finance/quote"
            params = {"symbols": ticker}
            resp = session.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    quotes = data.get("quoteResponse", {}).get("result", [])
                    for q in quotes:
                        results.append({
                            "symbol": q.get("symbol", ticker),
                            "name": q.get("shortName", "") or q.get("longName", ""),
                            "exchange": q.get("exchange", ""),
                            "type": q.get("quoteType", ""),
                            "ticker_full": q.get("symbol", ticker),
                        })
                except Exception:
                    pass

            if results:
                break
            time.sleep(0.3)

    except Exception as e:
        logger.debug("Fallback search failed: %s", e)

    return results[:limit]


def search_nse(query: str, limit: int = 10) -> list[dict]:
    """Search NSE India for a company name."""
    session = _get_browser_session()
    results = []

    try:
        url = "https://www.nseindia.com/api/search/query"
        params = {"q": query}
        headers = {
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        }

        # Initialize session with NSE cookies
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(0.5)

        resp = session.get(url, params=params, headers=headers, timeout=15)

        if resp.status_code == 200:
            try:
                data = resp.json()
                symbols = data.get("symbols", []) or data.get("data", [])

                for s in symbols[:limit]:
                    symbol = s.get("symbol", "") or s.get("meta", {}).get("symbol", "")
                    name = s.get("name", "") or s.get("meta", {}).get("companyName", "")

                    if symbol:
                        results.append({
                            "symbol": symbol,
                            "name": name,
                            "exchange": "NSE",
                            "type": "EQUITY",
                            "ticker_full": symbol + ".NS",
                        })
            except Exception:
                pass

    except Exception as e:
        logger.debug("NSE search failed for '%s': %s", query, e)

    return results[:limit]


def smart_resolve(query: str, limit: int = 10) -> list[dict]:
    """Intelligently search for a ticker across multiple sources.

    Resolution strategy:
    1. If query looks like a ticker (e.g., "MSFT"), try direct lookup
    2. If query looks like a company name, search Yahoo Finance
    3. If results include Indian exchanges, add .NS/.BO suffixes
    4. Return ranked results by relevance
    """
    query = query.strip()
    if not query:
        return []

    results = []

    # Check if query already has a valid ticker suffix
    has_suffix = any(query.upper().endswith(s) for s in [".NS", ".BO", ".L", ".DE", ".TO", ".HK"])

    # Strategy 1: Direct ticker lookup
    if len(query) <= 10 and not has_suffix:
        # Looks like a ticker symbol
        direct = _search_fallback(query, limit=3)
        results.extend(direct)

    # Strategy 2: Yahoo Finance search
    if len(results) < limit:
        yahoo_results = search_yahoo(query, limit=limit - len(results))
        # Avoid duplicates
        existing_symbols = {r["symbol"] for r in results}
        for r in yahoo_results:
            if r["symbol"] not in existing_symbols:
                results.append(r)
                existing_symbols.add(r["symbol"])

    # Strategy 3: If no results and query might be Indian, try NSE
    if not results:
        nse_results = search_nse(query, limit=limit)
        results.extend(nse_results)

    # Strategy 4: Try with Indian suffixes if no results
    if not results and not has_suffix:
        for suffix in INDIAN_SUFFIXES:
            ticker = query.upper() + suffix
            direct = _search_fallback(ticker, limit=2)
            results.extend(direct)
            if results:
                break

    return results[:limit]


def verify_ticker(ticker: str) -> Optional[dict]:
    """Verify a ticker exists and return its info.

    Returns dict with symbol, name, price, currency or None if invalid.
    """
    session = _get_browser_session()

    try:
        # Try v6 quote endpoint
        url = "https://query1.finance.yahoo.com/v6/finance/quote"
        params = {"symbols": ticker}
        resp = session.get(url, params=params, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            quotes = data.get("quoteResponse", {}).get("result", [])
            if quotes:
                q = quotes[0]
                return {
                    "symbol": q.get("symbol", ticker),
                    "name": q.get("shortName", "") or q.get("longName", ""),
                    "exchange": q.get("exchange", ""),
                    "price": q.get("regularMarketPrice"),
                    "currency": q.get("currency", ""),
                    "valid": True,
                }
    except Exception as e:
        logger.debug("Ticker verification failed for %s: %s", ticker, e)

    return None
