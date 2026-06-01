"""Tests for ticker_resolver module."""

import pytest
from breachalpha.ticker_resolver import resolve_ticker, resolve_all, KNOWN_TICKERS


class TestResolveTicker:
    def test_known_company(self):
        assert resolve_ticker("Equifax") == "EFX"

    def test_known_company_lowercase(self):
        assert resolve_ticker("equifax") == "EFX"

    def test_known_company_with_suffix(self):
        assert resolve_ticker("Equifax Inc.") == "EFX"

    def test_unknown_company(self):
        assert resolve_ticker("FakeCompany123") is None

    def test_partial_match(self):
        # "Capital One Financial" should match "capital one"
        ticker = resolve_ticker("Capital One Financial Corp")
        assert ticker == "COF"

    def test_overrides_take_precedence(self):
        overrides = {"equifax": "CUSTOM"}
        assert resolve_ticker("Equifax", overrides) == "CUSTOM"

    def test_private_company_returns_none(self):
        assert resolve_ticker("colonial pipeline") is None

    def test_all_known_companies_resolve(self):
        """Every hardcoded company should resolve to a valid ticker or None."""
        for name in ["adobe", "apple", "equifax", "walmart", "nvidia"]:
            result = resolve_ticker(name)
            assert result is not None or name in ["colonial pipeline"]


class TestResolveAll:
    def test_batch_resolution(self):
        names = ["Equifax", "Capital One", "Unknown Corp"]
        result = resolve_all(names)
        assert result["Equifax"] == "EFX"
        assert result["Capital One"] == "COF"
        assert result["Unknown Corp"] is None

    def test_empty_input(self):
        result = resolve_all([])
        assert result == {}
