"""Search for cybersecurity breach incidents from the internet.

Uses web search to find breach dates, types, and affected records
for any company.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# Hardcoded reverse ticker -> company name for well-known companies
TICKER_TO_NAME: dict[str, str] = {
    "TATAPOWER": "Tata Power",
    "TATAMOTORS": "Tata Motors",
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "SBIN.NS": "State Bank of India",
    "WIPRO": "Wipro",
    "ITC": "ITC",
    "LT": "Larsen & Toubro",
    "BHARTIARTL": "Bharti Airtel",
    "MARUTI": "Maruti Suzuki",
    "VEDL": "Vedanta",
    "VEDL.NS": "Vedanta",
    "HINDUNILVR": "Hindustan Unilever",
    "AXISBANK": "Axis Bank",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "BAJFINANCE": "Bajaj Finance",
    "ONGC": "Oil & Natural Gas Corporation",
    "NTPC": "NTPC",
    "POWERGRID": "Power Grid Corporation",
    "SUNPHARMA": "Sun Pharma",
    "ASIANPAINT": "Asian Paints",
    "ULTRACEMCO": "UltraTech Cement",
    "HCLTECH": "HCL Technologies",
    "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports",
    "JSWSTEEL": "JSW Steel",
    "TATASTEEL": "Tata Steel",
    "COALINDIA": "Coal India",
    "BANKBARODA": "Bank of Baroda",
    "PNB": "Punjab National Bank",
    "LIC": "Life Insurance Corporation",
    "HAL": "Hindustan Aeronautics",
    "BEL": "Bharat Electronics",
    "ZOMATO": "Zomato",
    "MSFT": "Microsoft",
    "AAPL": "Apple",
    "GOOGL": "Google",
    "AMZN": "Amazon",
    "META": "Meta",
    "EFX": "Equifax",
    "COF": "Capital One",
    "MAR": "Marriott",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "JPM": "JPMorgan Chase",
    "BAC": "Bank of America",
    "WMT": "Walmart",
    "NFLX": "Netflix",
    "DIS": "Disney",
    "V": "Visa",
    "MA": "Mastercard",
    "XOM": "Exxon Mobil",
    "CVX": "Chevron",
    "T": "AT&T",
    "VZ": "Verizon",
}


def _resolve_company_name(input_str: str) -> str:
    """Try to resolve a ticker-like input to a proper company name."""
    import re
    cleaned = input_str.strip().upper()
    # Strip exchange suffix
    bare = re.sub(r"\.(NS|BO|NSE|BSE|L|DE|TO|HK|SS|SZ)$", "", cleaned)

    # Try full input first
    if cleaned in TICKER_TO_NAME:
        return TICKER_TO_NAME[cleaned]

    # Try bare ticker
    if bare in TICKER_TO_NAME:
        return TICKER_TO_NAME[bare]

    # Try importing KNOWN_TICKERS reverse map from ticker_resolver
    try:
        from .ticker_resolver import KNOWN_TICKERS
        rev: dict[str, str] = {}
        for name, ticker in KNOWN_TICKERS.items():
            if ticker:
                rev[ticker.upper()] = name.title()
                t_bare = re.sub(r"\.(NS|BO|NSE|BSE|L|DE|TO|HK|SS|SZ)$", "", ticker.upper())
                rev[t_bare] = name.title()
        if cleaned in rev:
            return rev[cleaned]
        if bare in rev:
            return rev[bare]
    except Exception:
        pass

    return input_str


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


@dataclass
class BreachIncident:
    """A found breach incident."""
    company: str
    date: str
    breach_type: str
    records_affected: int
    source: str
    description: str
    confidence: float  # 0-1, how confident we are in this data


def search_breach_incidents(company: str, limit: int = 5) -> list[BreachIncident]:
    """Search the internet for breach incidents for a company.

    Searches multiple sources:
    1. News search for "[company] data breach"
    2. Direct web scraping of known breach databases
    3. SEC EDGAR for US companies

    Returns list of BreachIncident sorted by date (most recent first).
    """
    # First try to resolve ticker input to a company name
    company_name = _resolve_company_name(company)
    logger.info("Breach search for '%s' (resolved from '%s')", company_name, company)

    incidents = []

    # Source 1: Search news for breach reports (try multiple query variations)
    queries = [company_name]
    if company_name != company:
        queries.append(company)
    # Always also try just the bare company name (without exchange suffix)
    import re
    bare = re.sub(r"\.(NS|BO|NSE|BSE|L|DE|TO|HK|SS|SZ)$", "", company.strip().upper())
    if bare not in queries and bare not in [q.upper() for q in queries]:
        queries.append(bare)

    for q in queries:
        news_results = _search_news_breaches(q, limit)
        incidents.extend(news_results)
        if len(incidents) >= limit:
            break

    # Source 2: Search HIBP-like breach databases
    hibp_results = _search_hibp(company_name, limit)
    incidents.extend(hibp_results)

    # Source 3: Search SEC filings for 8-K cybersecurity disclosures
    sec_results = _search_sec_filings(company_name, limit)
    incidents.extend(sec_results)

    # Deduplicate by date+description
    seen = set()
    unique = []
    for inc in incidents:
        key = f"{inc.date}_{inc.description[:50]}"
        if key not in seen:
            seen.add(key)
            unique.append(inc)

    # Sort by date (most recent first)
    unique.sort(key=lambda x: x.date, reverse=True)

    return unique[:limit]


def _search_hibp(company: str, limit: int) -> list[BreachIncident]:
    """Search HaveIBeenPwned for breach data."""
    session = _get_browser_session()
    results = []

    try:
        # HIBP has a public breach list page
        url = "https://haveibeenpwned.com/unifiedsearch/{company}"
        # Note: HIBP API requires API key, but we can scrape the public page
        # For now, return empty - this is a placeholder
        pass
    except Exception as e:
        logger.debug("HIBP search failed for %s: %s", company, e)

    return results


def _extract_date_from_text(text: str) -> str:
    """Extract a date string from text, returning YYYY-MM-DD or empty string."""
    # Pattern 1: ISO format (2022-10-14)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # Pattern 2: "14 October 2022" or "October 14, 2022"
    months_map = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
        "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    month_names = "|".join(months_map.keys())
    m = re.search(r"(\d{1,2})\s+(" + month_names + r")\s+(\d{4})", text, re.IGNORECASE)
    if m:
        d = m.group(1).zfill(2)
        mo = months_map.get(m.group(2).lower(), "01")
        y = m.group(3)
        return f"{y}-{mo}-{d}"

    m = re.search(r"(" + month_names + r")\s+(\d{1,2}),?\s*(\d{4})", text, re.IGNORECASE)
    if m:
        d = m.group(2).zfill(2)
        mo = months_map.get(m.group(1).lower(), "01")
        y = m.group(3)
        return f"{y}-{mo}-{d}"

    return ""


def _search_web_breaches(company: str, limit: int) -> list[BreachIncident]:
    """Fallback: scrape web search results for breach info.
    
    Uses DuckDuckGo HTML search to find breach-related articles.
    This works when Yahoo Finance news has no relevant results.
    """
    session = _get_browser_session()
    results = []
    seen_urls = set()

    try:
        search_query = f"{company} data breach cyber attack ransomware incident"
        url = "https://html.duckduckgo.com/html"
        params = {"q": search_query, "kl": "wt-wt"}

        resp = session.post(url, data=params, timeout=20)
        if resp.status_code != 200:
            return results

        html = resp.text

        # Extract all result links
        link_pattern = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
        snippet_pattern = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (link, title_html) in enumerate(links[:limit * 5]):
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            text = (title + " " + snippet).lower()
            breach_keywords = [
                "breach", "hack", "hacked", "cyberattack", "cyber attack",
                "ransomware", "data leak", "data breach", "security incident",
                "compromised", "exposed", "stolen", "unauthorized access",
                "cyber security", "cybersecurity",
            ]
            if not any(kw in text for kw in breach_keywords):
                continue

            date_str = _extract_date_from_text(text)
            if not date_str:
                continue

            records = _extract_records_from_text(text)
            breach_type = _detect_breach_type(text)

            link_clean = link[:80]
            if link_clean in seen_urls:
                continue
            seen_urls.add(link_clean)

            results.append(BreachIncident(
                company=company, date=date_str,
                breach_type=breach_type, records_affected=records,
                source=f"web:{link_clean}",
                description=title[:200], confidence=0.5,
            ))

    except Exception as e:
        logger.debug("Web search failed for %s: %s", company, e)

    return results[:limit]


def _search_news_breaches(company: str, limit: int) -> list[BreachIncident]:
    """Search news articles for breach reports.

    Uses multiple strategies:
    1. Yahoo Finance news search with explicit breach keywords
    2. DuckDuckGo web search fallback
    """
    session = _get_browser_session()
    results = []

    # Strategy 1: Yahoo Finance news search
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        queries = [
            f"{company} data breach",
            f"{company} cyber attack ransomware",
            f"{company} hack security incident",
        ]

        for q in queries:
            params = {"q": q, "quotesCount": 0, "newsCount": limit * 3}
            resp = session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                continue

            try:
                data = resp.json()
                news = data.get("news", [])
            except Exception:
                continue

            for article in news:
                title = article.get("title", "")
                snippet = article.get("snippet", "")
                pub_date = article.get("providerPublishTime", 0)
                link = article.get("link", "")

                text = (title + " " + snippet).lower()
                breach_keywords = [
                    "breach", "hack", "hacked", "cyberattack", "cyber attack",
                    "ransomware", "data leak", "data breach", "security incident",
                    "compromised", "exposed", "stolen", "unauthorized access",
                    "cyber security", "cybersecurity",
                ]
                is_breach = any(kw in text for kw in breach_keywords)

                if is_breach and pub_date:
                    date_str = time.strftime("%Y-%m-%d", time.gmtime(pub_date))
                    records = _extract_records_from_text(snippet + " " + title)
                    breach_type = _detect_breach_type(text)

                    is_dup = any(r.date == date_str and r.description[:50] == title[:50] for r in results)
                    if not is_dup:
                        results.append(BreachIncident(
                            company=company, date=date_str,
                            breach_type=breach_type, records_affected=records,
                            source=f"news:{link[:80]}",
                            description=title[:200], confidence=0.6,
                        ))

            if len(results) >= limit:
                break

    except Exception as e:
        logger.debug("Yahoo news search failed for %s: %s", company, e)

    # Strategy 2: Web search fallback (if not enough results from Yahoo)
    if len(results) < limit:
        try:
            web_results = _search_web_breaches(company, limit - len(results))
            results.extend(web_results)
        except Exception as e:
            logger.debug("Web search fallback failed: %s", e)

    return results[:limit]


def _search_sec_filings(company: str, limit: int) -> list[BreachIncident]:
    """Search SEC EDGAR for 8-K cybersecurity disclosures."""
    session = _get_browser_session()
    results = []

    try:
        # Search EDGAR for 8-K filings mentioning "cybersecurity"
        url = "https://efts.sec.gov/LATEST/search-index?q=%22cybersecurity+incident%22&dateRange=custom&startdt=2020-01-01&forms=8-K"

        # Use the full-text search API
        search_url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": f'"{company}" AND "cybersecurity incident"',
            "dateRange": "custom",
            "startdt": "2020-01-01",
            "forms": "8-K",
        }

        resp = session.get(search_url, params=params, timeout=15, headers={
            "User-Agent": "BreachAlpha Research Bot",
        })

        if resp.status_code == 200:
            try:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])

                for hit in hits[:limit]:
                    source = hit.get("_source", {})
                    filing_date = source.get("file_date", "")
                    title = source.get("display_names", [""])[0] if source.get("display_names") else ""

                    if filing_date:
                        results.append(BreachIncident(
                            company=company,
                            date=filing_date[:10],
                            breach_type="data_leak",
                            records_affected=0,  # Unknown from SEC filing
                            source=f"sec:{source.get('file_num', '')}",
                            description=f"SEC 8-K cybersecurity disclosure: {title}",
                            confidence=0.7,
                        ))
            except Exception:
                pass

    except Exception as e:
        logger.debug("SEC search failed for %s: %s", company, e)

    return results[:limit]


def _extract_records_from_text(text: str) -> int:
    """Extract number of records affected from text."""
    text = text.lower()

    # Match patterns like "10 million records", "50,000 accounts", "1.5B users"
    patterns = [
        (r"(\d+[\d,\.]*)\s*(?:million|m)\s*(?:records?|accounts?|users?|people)", 1_000_000),
        (r"(\d+[\d,\.]*)\s*(?:billion|b)\s*(?:records?|accounts?|users?|people)", 1_000_000_000),
        (r"(\d+[\d,\.]*)\s*(?:thousand|k)\s*(?:records?|accounts?|users?|people)", 1_000),
        (r"(\d+[\d,\.]*)\s*(?:records?|accounts?|users?|people)\s*(?:breached|exposed|stolen|compromised)", 1),
    ]

    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            num_str = match.group(1).replace(",", "").replace(".", "")
            try:
                return int(num_str) * multiplier
            except ValueError:
                continue

    return 0


def _detect_breach_type(text: str) -> str:
    """Detect breach type from text."""
    text = text.lower()

    if any(w in text for w in ["ransomware", "ransom", "encrypt"]):
        return "ransomware"
    elif any(w in text for w in ["phishing", "social engineering"]):
        return "phishing"
    elif any(w in text for w in ["insider", "employee", "former"]):
        return "insider"
    elif any(w in text for w in ["hack", "hacked", "breach", "compromised"]):
        return "hack"
    elif any(w in text for w in ["leak", "exposed", "unsecured"]):
        return "data_leak"
    else:
        return "data_leak"
