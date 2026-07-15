"""Tests for Yahoo Finance and NSE/BSE ticker search helpers."""

from __future__ import annotations

from typing import Any

import pytest

from breachalpha import ticker_search


class FakeResponse:
    """Small response double for ticker_search HTTP calls."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.headers = headers if headers is not None else {"content-type": "application/json"}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    """Session double with configurable responses and captured calls."""

    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"unexpected GET call to {url}")
        return self.responses.pop(0)


class RaisingSession:
    """Session double that raises on every request."""

    def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        raise TimeoutError("network timed out")


def test_search_yahoo_returns_results_and_resolves_indian_suffixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "quotes": [
                        {
                            "symbol": "AAPL",
                            "shortname": "Apple Inc.",
                            "exchange": "NMS",
                            "quoteType": "EQUITY",
                        },
                        {
                            "symbol": "RELIANCE",
                            "longname": "Reliance Industries Limited",
                            "exchange": "NSI",
                            "quoteType": "EQUITY",
                        },
                        {
                            "symbol": "TCS",
                            "shortname": "Tata Consultancy Services",
                            "exchange": "BSE",
                            "quoteType": "EQUITY",
                        },
                    ]
                }
            )
        ]
    )
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)

    results = ticker_search.search_yahoo("apple", limit=3)

    assert results == [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NMS",
            "type": "EQUITY",
            "ticker_full": "AAPL",
        },
        {
            "symbol": "RELIANCE",
            "name": "Reliance Industries Limited",
            "exchange": "NSI",
            "type": "EQUITY",
            "ticker_full": "RELIANCE.NS",
        },
        {
            "symbol": "TCS",
            "name": "Tata Consultancy Services",
            "exchange": "BSE",
            "type": "EQUITY",
            "ticker_full": "TCS.BO",
        },
    ]
    assert session.calls[0]["params"]["q"] == "apple"
    assert session.calls[0]["params"]["quotesCount"] == 3


def test_search_yahoo_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "quotes": [
                        {"symbol": "AAA", "shortname": "AAA", "exchange": "NMS"},
                        {"symbol": "BBB", "shortname": "BBB", "exchange": "NMS"},
                    ]
                }
            )
        ]
    )
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)

    results = ticker_search.search_yahoo("a", limit=1)

    assert [result["symbol"] for result in results] == ["AAA"]


def test_search_yahoo_uses_fallback_for_html_response(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            FakeResponse(
                headers={"content-type": "text/html; charset=utf-8"},
                text="<!doctype html><html></html>",
            )
        ]
    )
    fallback = [{"symbol": "MSFT", "ticker_full": "MSFT"}]
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)
    monkeypatch.setattr(ticker_search, "_search_fallback", lambda query, limit: fallback)

    assert ticker_search.search_yahoo("microsoft", limit=5) == fallback


def test_search_yahoo_uses_fallback_for_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = [{"symbol": "TSLA", "ticker_full": "TSLA"}]
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: RaisingSession())
    monkeypatch.setattr(ticker_search, "_search_fallback", lambda query, limit: fallback)

    assert ticker_search.search_yahoo("tesla", limit=2) == fallback


def test_search_yahoo_uses_fallback_for_non_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadJsonResponse(FakeResponse):
        def json(self) -> dict[str, Any]:
            raise ValueError("not json")

    session = FakeSession([BadJsonResponse()])
    fallback = [{"symbol": "NFLX", "ticker_full": "NFLX"}]
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)
    monkeypatch.setattr(ticker_search, "_search_fallback", lambda query, limit: fallback)

    assert ticker_search.search_yahoo("netflix", limit=4) == fallback


def test_search_yahoo_returns_empty_when_no_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([FakeResponse({"quotes": []})])
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)

    assert ticker_search.search_yahoo("missing", limit=10) == []


def test_search_fallback_tries_indian_suffixes(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            FakeResponse({"quoteResponse": {"result": []}}),
            FakeResponse(
                {
                    "quoteResponse": {
                        "result": [
                            {
                                "symbol": "TCS.NS",
                                "shortName": "Tata Consultancy Services",
                                "exchange": "NSI",
                                "quoteType": "EQUITY",
                            }
                        ]
                    }
                }
            ),
        ]
    )
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)
    monkeypatch.setattr(ticker_search.time, "sleep", lambda _seconds: None)

    results = ticker_search._search_fallback("tcs", limit=5)

    tried_symbols = [call["params"]["symbols"] for call in session.calls]
    assert tried_symbols == ["TCS", "TCS.NS"]
    assert results == [
        {
            "symbol": "TCS.NS",
            "name": "Tata Consultancy Services",
            "exchange": "NSI",
            "type": "EQUITY",
            "ticker_full": "TCS.NS",
        }
    ]


def test_search_fallback_returns_empty_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadJsonResponse(FakeResponse):
        def json(self) -> dict[str, Any]:
            raise ValueError("not json")

    session = FakeSession([BadJsonResponse(status_code=200)])
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)
    monkeypatch.setattr(ticker_search.time, "sleep", lambda _seconds: None)

    assert ticker_search._search_fallback("bad", limit=1) == []


def test_search_nse_returns_results_with_ns_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            FakeResponse({}),
            FakeResponse(
                {
                    "symbols": [
                        {
                            "symbol": "INFY",
                            "name": "Infosys Limited",
                        }
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)
    monkeypatch.setattr(ticker_search.time, "sleep", lambda _seconds: None)

    results = ticker_search.search_nse("infosys", limit=10)

    assert results == [
        {
            "symbol": "INFY",
            "name": "Infosys Limited",
            "exchange": "NSE",
            "type": "EQUITY",
            "ticker_full": "INFY.NS",
        }
    ]
    assert session.calls[0]["url"] == "https://www.nseindia.com"
    assert session.calls[1]["headers"]["Referer"] == "https://www.nseindia.com/"


def test_search_nse_supports_nested_meta_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            FakeResponse({}),
            FakeResponse(
                {
                    "data": [
                        {
                            "meta": {
                                "symbol": "HDFCBANK",
                                "companyName": "HDFC Bank Limited",
                            }
                        }
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)
    monkeypatch.setattr(ticker_search.time, "sleep", lambda _seconds: None)

    results = ticker_search.search_nse("hdfc", limit=1)

    assert results[0]["symbol"] == "HDFCBANK"
    assert results[0]["name"] == "HDFC Bank Limited"
    assert results[0]["ticker_full"] == "HDFCBANK.NS"


def test_smart_resolve_deduplicates_yahoo_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ticker_search,
        "_search_fallback",
        lambda query, limit: [{"symbol": "AAPL", "ticker_full": "AAPL"}],
    )
    monkeypatch.setattr(
        ticker_search,
        "search_yahoo",
        lambda query, limit: [
            {"symbol": "AAPL", "ticker_full": "AAPL"},
            {"symbol": "MSFT", "ticker_full": "MSFT"},
        ],
    )

    results = ticker_search.smart_resolve("apple", limit=3)

    assert [result["symbol"] for result in results] == ["AAPL", "MSFT"]


def test_smart_resolve_uses_nse_when_other_sources_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ticker_search, "_search_fallback", lambda query, limit: [])
    monkeypatch.setattr(ticker_search, "search_yahoo", lambda query, limit: [])
    monkeypatch.setattr(
        ticker_search,
        "search_nse",
        lambda query, limit: [{"symbol": "INFY", "ticker_full": "INFY.NS"}],
    )

    assert ticker_search.smart_resolve("infosys") == [{"symbol": "INFY", "ticker_full": "INFY.NS"}]


def test_smart_resolve_empty_query_returns_empty() -> None:
    assert ticker_search.smart_resolve("   ") == []


def test_verify_ticker_returns_quote_info(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "quoteResponse": {
                        "result": [
                            {
                                "symbol": "AAPL",
                                "shortName": "Apple Inc.",
                                "exchange": "NMS",
                                "regularMarketPrice": 190.5,
                                "currency": "USD",
                            }
                        ]
                    }
                }
            )
        ]
    )
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)

    assert ticker_search.verify_ticker("AAPL") == {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "exchange": "NMS",
        "price": 190.5,
        "currency": "USD",
        "valid": True,
    }


def test_verify_ticker_returns_none_for_no_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([FakeResponse({"quoteResponse": {"result": []}})])
    monkeypatch.setattr(ticker_search, "_get_browser_session", lambda: session)

    assert ticker_search.verify_ticker("NOPE") is None
