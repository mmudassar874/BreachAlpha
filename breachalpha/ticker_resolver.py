"""Resolve company names to stock ticker symbols.

Handles:
- Company name → ticker lookup
- Direct ticker input (e.g., "MSFT" → "MSFT")
- Partial/fuzzy matching
- Indian companies (NSE/BSE)
- User overrides
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OVERRIDES_PATH = Path(__file__).parent.parent / "data" / "ticker_overrides.json"

# ── Known Tickers ───────────────────────────────────────────────────────

KNOWN_TICKERS: dict[str, str] = {
    # ── US Tech ──
    "adobe": "ADBE", "apple": "AAPL", "amazon": "AMZN", "microsoft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "meta": "META", "facebook": "META",
    "netflix": "NFLX", "nvidia": "NVDA", "amd": "AMD", "intel": "INTC",
    "cisco": "CSCO", "ibm": "IBM", "oracle": "ORCL", "salesforce": "CRM",
    "sap": "SAP", "adobe": "ADBE", "spotify": "SPOT", "snap": "SNAP",
    "pinterest": "PINS", "robinhood": "HOOD", "coinbase": "COIN",
    "paypal": "PYPL", "block": "SQ", "shopify": "SHOP", "zoom": "ZM",
    "dell": "DELL", "hp": "HPQ", "qualcomm": "QCOM", "broadcom": "AVGO",
    "ibm": "IBM", "accenture": "ACN", "infosys": "INFY", "wipro": "WIT",
    "tech mahindra": "TECHM.ME", "hcl technologies": "HCLTECH.NS",
    "tata consultancy": "TCS.NS", "tcs": "TCS.NS",

    # ── US Finance ──
    "jpmorgan chase": "JPM", "bank of america": "BAC", "citigroup": "C",
    "wells fargo": "WFC", "goldman sachs": "GS", "morgan stanley": "MS",
    "visa": "V", "mastercard": "MA", "american express": "AXP",
    "berkshire hathaway": "BRK-B", "blackrock": "BLK", "charles schwab": "SCHW",

    # ── US Healthcare ──
    "unitedhealth group": "UNH", "cigna": "CI", "cvs health": "CVS",
    "abbvie": "ABBV", "johnson & johnson": "JNJ", "pfizer": "PFE",
    "merck": "MRK", "moderna": "MRNA", "gilead sciences": "GILD",

    # ── US Retail & Consumer ──
    "walmart": "WMT", "costco": "COST", "target": "TGT", "home depot": "HD",
    "mcdonald's": "MCD", "starbucks": "SBUX", "nike": "NKE",
    "coca cola": "KO", "pepsi": "PEP", "disney": "DIS",

    # ── US Auto & Industrial ──
    "tesla": "TSLA", "ford": "F", "general motors": "GM",
    "boeing": "BA", "caterpillar": "CAT", "ge": "GE", "3m": "MMM",
    "honeywell": "HON", "lockheed martin": "LMT", "raytheon": "RTX",

    # ── US Energy ──
    "exxon mobil": "XOM", "chevron": "CVX", "conocophillips": "COP",
    "shell": "SHEL", "bp": "BP",

    # ── US Telecom & Media ──
    "at&t": "T", "verizon": "VZ", "t-mobile": "TMUS", "comcast": "CMCSA",
    "paramount": "PARA", "warner bros": "WBD", "fox": "FOX",

    # ── US Cybersecurity ──
    "equifax": "EFX", "marriott": "MAR", "capital one": "COF",
    "crowdstrike": "CRWD", "palo alto networks": "PANW", "fortinet": "FTNT",
    "okta": "OKTA", "zscaler": "ZS", "sentinelone": "S", "cloudflare": "NET",
    "rapid7": "RPD", "cyberark": "CYBR", "qualys": "QLYS",
    "microsoft defender": "MSFT",

    # ── US Ride-hailing & Food ──
    "uber": "UBER", "lyft": "LYFT", "doordash": "DASH", "airbnb": "ABNB",

    # ── Japanese ──
    "sony": "SONY", "nintendo": "NTDOY", "toyota": "TM", "honda": "HMC",
    "softbank": "SFTBY", "mitsubishi": "MSBHF",

    # ── European ──
    "sap": "SAP", "siemens": "SIEGY", "bmw": "BAMXY", "volkswagen": "VWAGY",
    "nestle": "NSRGY", "unilever": "UL", "asml": "ASML",
    "novartis": "NVS", "roche": "RHHBY", "astrazeneca": "AZN",

    # ── Indian (NSE tickers with .NS suffix for yfinance) ──
    # IT Services
    "tata consultancy services": "TCS.NS", "tata consultancy": "TCS.NS",
    "infosys": "INFY.NS", "wipro": "WIT.NS", "hcl technologies": "HCLTECH.NS",
    "tech mahindra": "TECHM.NS", "mindtree": "MINDTREE.NS",
    "ltimindtree": "LTIM.NS", "mphasis": "MPHASIS.NS",
    "persistentsystems": "PERSISTENT.NS", "persistent systems": "PERSISTENT.NS",
    "cognizant": "CTSH",  # US-listed

    # Mining & Metals
    "vedanta": "VEDL.NS", "vedl": "VEDL.NS", "tata steel": "TATASTEEL.NS",
    "jsw steel": "JSWSTEEL.NS", "hindalco": "HINDALCO.NS",
    "coal india": "COALINDIA.NS", "nmdc": "NMDC.NS",
    "hindustan zinc": "HINDZINC.NS", "hindustan copper": "HINDCOPPER.NS",
    "national aluminium": "NATIONALUM.NS", "nalco": "NATIONALUM.NS",
    "jindal steel": "JINDALSTEL.NS", "jsw energy": "JSWENERGY.NS",

    # Banking & Finance
    "hdfc bank": "HDFCBANK.NS", "icici bank": "ICICIBANK.NS",
    "state bank of india": "SBIN.NS", "sbi": "SBIN.NS",
    "kotak mahindra bank": "KOTAKBANK.NS", "axis bank": "AXISBANK.NS",
    "bajaj finance": "BAJFINANCE.NS", "bajaj finserv": "BAJAJFINSV.NS",
    "hdfc life": "HDFCLIFE.NS", "sbin": "SBIN.NS",
    "indusind bank": "INDUSINDBK.NS", "bank of baroda": "BANKBARODA.NS",
    "punjab national bank": "PNB.NS", "pnb": "PNB.NS",
    "idbi bank": "IDBI.NS", "federal bank": "FEDERALBNK.NS",

    # Conglomerates & Industrial
    "reliance industries": "RELIANCE.NS", "reliance": "RELIANCE.NS",
    "tata sons": "TATAELXSI.NS", "tata motors": "TATAMOTORS.NS",
    "tata steel": "TATASTEEL.NS", "tata power": "TATAPOWER.NS",
    "tata consumers": "TATACONSUM.NS", "tata communications": "TATA COMM.NS",
    "tata chemicals": "TATACHEM.NS", "tata investment": "TATAINVEST.NS",
    "adani enterprises": "ADANIENT.NS", "adani ports": "ADANIPORTS.NS",
    "adani green": "ADANIGREEN.NS", "adani power": "ADANIPOWER.NS",
    "adani total gas": "ATGL.NS", "adani wilmar": "AWL.NS",
    "larsen toubro": "LT.NS", "l&t": "LT.NS",
    "hindustan unilever": "HINDUNILVR.NS", "itc": "ITC.NS",
    "asian paints": "ASIANPAINT.NS", "bajaj auto": "BAJAJ-AUTO.NS",
    "mahindra & mahindra": "M&M.NS", "hero motocorp": "HEROMOTOCO.NS",
    "maruti suzuki": "MARUTI.NS", "eicher motors": "EICHERMOT.NS",

    # Energy
    "oil and natural gas corporation": "ONGC.NS", "ongc": "ONGC.NS",
    "ntpc": "NTPC.NS", "power grid corporation": "POWERGRID.NS",
    "coal india": "COALINDIA.NS", "hindustan petroleum": "HINDPETRO.NS",
    "bharat petroleum": "BPCL.NS", "gail": "GAIL.NS",
    "tata power": "TATAPOWER.NS", "adani green energy": "ADANIGREEN.NS",

    # Telecom
    "bharti airtel": "BHARTIARTL.NS", "airtel": "BHARTIARTL.NS",
    "reliance jio": "RELIANCE.NS", "vodafone idea": "IDEA.NS",
    "jio": "RELIANCE.NS",

    # Pharma
    "sun pharma": "SUNPHARMA.NS", "dr reddy's": "DRREDDY.NS",
    "cipla": "CIPLA.NS", "apollo hospitals": "APOLLOHOSP.NS",
    "divi's laboratories": "DIVISLAB.NS", "biocon": "BIOCON.NS",

    # Cement & Materials
    "ultratech cement": "ULTRACEMCO.NS", "ambuja cements": "AMBUJACEM.NS",
    "acc": "ACC.NS", "dalmia bharat": "DALBHARAT.NS",

    # Insurance
    "life insurance corporation": "LIC.NS", "lic": "LIC.NS",
    "sbi life insurance": "SBILIFE.NS", "icici prudential": "ICICIPRULI.NS",

    # Indian IT (BSE tickers as fallback)
    "tcs": "TCS.NS", "wipro": "WIT.NS", "infosys": "INFY.NS",

    # ── Chinese ──
    "alibaba": "BABA", "tencent": "TCEHY", "jd.com": "JD",
    "baidu": "BIDU", "nio": "NIO", "xiaomi": "XIACF",

    # ── Korean ──
    "samsung": "SSNLF", "sk hynix": "HXSCL", "lg": "LGLG.DE",

    # ── Private / Acquired ──
    "colonial pipeline": None, "moveit": None,
    "twitter": None, "myspace": None,
}

# Reverse map: ticker → company name (for validation)
TICKER_TO_COMPANY: dict[str, str] = {v: k for k, v in KNOWN_TICKERS.items() if v}

# Valid ticker patterns
TICKER_WITH_SUFFIX = re.compile(r"^[A-Z]{1,10}\.[A-Z]{1,3}$")  # e.g., TATAPOWER.NS, RELIANCE.BO
TICKER_BARE = re.compile(r"^[A-Z]{1,10}$")  # e.g., MSFT, TCS, VEDL


def is_likely_ticker(name: str) -> bool:
    """Check if input looks like a stock ticker symbol.

    Accepts:
    - Bare tickers: MSFT, TCS, VEDL (1-10 uppercase letters)
    - With suffix: TATAPOWER.NS, RELIANCE.BO, VEDL.NS
    - Known formats: .NS, .BO, .L, .DE, .TO, .HK, .T, .SS, .SZ
    """
    cleaned = name.strip().upper()
    if TICKER_WITH_SUFFIX.match(cleaned):
        return True
    if TICKER_BARE.match(cleaned):
        return True
    return False


def load_overrides() -> dict[str, str]:
    """Load manual ticker overrides from JSON file."""
    if OVERRIDES_PATH.exists():
        with open(OVERRIDES_PATH) as f:
            data = json.load(f)
        logger.info("Loaded %d ticker overrides from %s", len(data), OVERRIDES_PATH.name)
        return {k.lower(): v for k, v in data.items()}
    return {}


def save_overrides(overrides: dict[str, str]) -> None:
    """Save ticker overrides to JSON file."""
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDES_PATH, "w") as f:
        json.dump(overrides, f, indent=2)
    logger.info("Saved %d ticker overrides to %s", len(overrides), OVERRIDES_PATH.name)


def resolve_ticker(company_name: str, overrides: Optional[dict[str, str]] = None) -> Optional[str]:
    """Resolve a company name to a stock ticker symbol.

    Resolution order:
    1. Manual overrides (user-provided)
    2. Hardcoded KNOWN_TICKERS (exact match)
    3. Partial/fuzzy match
    4. Direct ticker with suffix (e.g., TATAPOWER.NS) — return as-is
    5. Direct bare ticker (e.g., MSFT, VEDL) — return as-is
    6. Returns None if unresolved
    """
    name_lower = company_name.lower().strip()
    name_upper = company_name.strip().upper()

    # Step 1: Check overrides first (highest priority)
    if overrides and name_lower in overrides:
        return overrides[name_lower]

    # Step 2: Exact match in known tickers (company name lookup)
    if name_lower in KNOWN_TICKERS:
        return KNOWN_TICKERS[name_lower]

    # Step 3: Partial match (company name contains known name or vice versa)
    for key, ticker in KNOWN_TICKERS.items():
        if key in name_lower or name_lower in key:
            return ticker

    # Step 4: Direct ticker with suffix (e.g., TATAPOWER.NS, RELIANCE.BO) — trust user
    if TICKER_WITH_SUFFIX.match(name_upper):
        return name_upper

    # Step 5: Bare ticker (e.g., MSFT, VEDL) — trust user
    if TICKER_BARE.match(name_upper):
        return name_upper
    for key, ticker in KNOWN_TICKERS.items():
        if len(key) > 3 and key in name_lower:
            return ticker

    return None


def resolve_all(
    company_names: list[str],
    overrides: Optional[dict[str, str]] = None,
) -> dict[str, Optional[str]]:
    """Resolve a list of company names to tickers."""
    if overrides is None:
        overrides = load_overrides()

    results = {}
    unresolved = []

    for name in company_names:
        ticker = resolve_ticker(name, overrides)
        results[name] = ticker
        if ticker is None:
            unresolved.append(name)

    if unresolved:
        logger.warning("Unresolved %d companies: %s", len(unresolved), unresolved[:10])

    resolved_count = sum(1 for v in results.values() if v is not None)
    logger.info("Resolved %d/%d companies to tickers", resolved_count, len(results))

    return results
