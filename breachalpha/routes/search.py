"""Ticker search and breach search endpoints."""

from __future__ import annotations

import asyncio

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Request

from ..ticker_resolver import resolve_ticker
from ..schemas import SearchResponse, SearchResult, BreachSearchResponse, BreachIncidentResult
from ..core.constants import TICKER_RE

_search_cache: TTLCache = TTLCache(maxsize=1000, ttl=300)


def _validate_breach_search_query(q: str) -> str:
    q = q.strip()
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters.")
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="Query too long (max 100 characters).")
    return q


def create_search_routes(limiter) -> APIRouter:
    router = APIRouter()

    @router.get("/api/search", response_model=SearchResponse)
    @limiter.limit("30/minute")
    async def search_ticker(request: Request, q: str = "", limit: int = 10):
        from ..ticker_resolver import KNOWN_TICKERS

        if not q or len(q.strip()) < 1:
            return SearchResponse(query=q, results=[], count=0)

        query = q.strip()
        if len(query) > 100:
            raise HTTPException(status_code=400, detail="Query too long (max 100 characters).")

        query = q.strip()
        query_lower = query.lower()
        limit = max(1, min(limit, 20))

        local_results = []
        seen = set()

        if query_lower in KNOWN_TICKERS and KNOWN_TICKERS[query_lower]:
            ticker = KNOWN_TICKERS[query_lower]
            local_results.append(SearchResult(symbol=ticker, name=query.title(), ticker_full=ticker, source="local"))
            seen.add(ticker)

        if len(local_results) < limit:
            for name, ticker in KNOWN_TICKERS.items():
                if not ticker or ticker in seen:
                    continue
                if query_lower in name or name.startswith(query_lower):
                    local_results.append(SearchResult(symbol=ticker, name=name.title(), ticker_full=ticker, source="local"))
                    seen.add(ticker)
                    if len(local_results) >= limit:
                        break

        if len(local_results) < limit:
            query_upper = query.upper()
            for name, ticker in KNOWN_TICKERS.items():
                if not ticker or ticker in seen:
                    continue
                bare = ticker.split(".")[0]
                if query_upper == bare or query_upper == ticker:
                    local_results.append(SearchResult(symbol=ticker, name=name.title(), ticker_full=ticker, source="local"))
                    seen.add(ticker)
                    if len(local_results) >= limit:
                        break

        if len(local_results) >= limit:
            return SearchResponse(query=query, results=local_results[:limit], count=len(local_results))

        cached = _search_cache.get(query_lower)
        if cached is not None:
            network_results = cached
        else:
            from ..ticker_search import smart_resolve
            network_results = await asyncio.to_thread(smart_resolve, query, limit)
            _search_cache[query_lower] = network_results

        for r in network_results:
            ticker = r.get("ticker_full", r.get("symbol", ""))
            if ticker and ticker not in seen:
                local_results.append(SearchResult(
                    symbol=r.get("symbol", ticker),
                    name=r.get("name", ""),
                    ticker_full=ticker,
                    source="network",
                ))
                seen.add(ticker)

        return SearchResponse(query=query, results=local_results[:limit], count=len(local_results))

    @router.get("/api/breach-search", response_model=BreachSearchResponse)
    @limiter.limit("10/minute")
    async def search_breach(request: Request, q: str = "", limit: int = 5):
        from ..breach_search import search_breach_incidents

        q = _validate_breach_search_query(q)
        limit = max(1, min(limit, 20))

        incidents = await asyncio.to_thread(search_breach_incidents, q, limit)

        return BreachSearchResponse(
            query=q,
            incidents=[
                BreachIncidentResult(
                    company=inc.company, date=inc.date,
                    breach_type=inc.breach_type, records_affected=inc.records_affected,
                    source=inc.source, description=inc.description,
                    confidence=inc.confidence,
                )
                for inc in incidents
            ],
            count=len(incidents),
        )

    return router
