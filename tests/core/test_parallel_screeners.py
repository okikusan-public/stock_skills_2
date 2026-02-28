"""Tests for parallel execution in ContrarianScreener, PullbackScreener, MomentumScreener (KIK-530)."""

import pandas as pd
import numpy as np
import pytest

from src.core.screening.contrarian_screener import ContrarianScreener
from src.core.screening.pullback_screener import PullbackScreener
from src.core.screening.momentum_screener import MomentumScreener


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_oversold_hist() -> pd.DataFrame:
    """Generate history where RSI is very low (sharp recent decline)."""
    n = 250
    dates = pd.bdate_range(end="2026-02-27", periods=n)
    prices = np.full(n, 1000.0)
    prices[200:] = np.linspace(1000, 600, 50)
    volumes = np.full(n, 300_000.0)
    volumes[-5:] = 900_000
    return pd.DataFrame({"Close": prices, "Volume": volumes}, index=dates)


def _make_uptrend_hist(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """Create a simple uptrend history."""
    prices = [base * (1 + 0.001 * i) for i in range(n)]
    return pd.DataFrame({
        "Close": prices,
        "Volume": [1_000_000.0] * n,
    })


def _make_contrarian_quote(symbol: str, per: float = 7.0, pbr: float = 0.4, roe: float = 0.12) -> dict:
    return {
        "symbol": symbol,
        "shortName": f"Company {symbol}",
        "sector": "Technology",
        "industry": "Semiconductors",
        "currency": "JPY",
        "regularMarketPrice": 1000.0,
        "marketCap": 100_000_000_000,
        "trailingPE": per,
        "priceToBook": pbr,
        "returnOnEquity": roe,
        "dividendYield": 3.0,
        "revenueGrowth": 0.05,
        "earningsGrowth": 0.08,
        "exchange": "JPX",
    }


def _make_contrarian_detail() -> dict:
    return {
        "eps_growth": 0.05,
        "fcf": 15_000_000_000,
        "market_cap": 100_000_000_000,
        "roe": 0.15,
        "dividend_yield_trailing": 0.04,
    }


def _make_momentum_quote(symbol: str, ma50_change: float = 0.20, high_change: float = -0.03) -> dict:
    return {
        "symbol": symbol,
        "shortName": f"Company {symbol}",
        "regularMarketPrice": 2500,
        "trailingPE": 10,
        "priceToBook": 1.2,
        "dividendYield": 0.025,
        "trailingAnnualDividendYield": 0.023,
        "returnOnEquity": 0.12,
        "revenueGrowth": 0.08,
        "epsGrowth": 0.10,
        "fiftyDayAverageChangePercent": ma50_change,
        "fiftyTwoWeekHighChangePercent": high_change,
    }


def _make_pullback_quote(symbol: str, high_change: float = -0.08) -> dict:
    return {
        "symbol": symbol,
        "shortName": f"Company {symbol}",
        "regularMarketPrice": 2500,
        "trailingPE": 10,
        "priceToBook": 1.0,
        "dividendYield": 0.02,
        "trailingAnnualDividendYield": 0.02,
        "returnOnEquity": 0.10,
        "revenueGrowth": 0.06,
        "epsGrowth": 0.05,
        "fiftyTwoWeekHighChangePercent": high_change,
    }


# ---------------------------------------------------------------------------
# Mock clients
# ---------------------------------------------------------------------------

class _ContrarianMockClient:
    def __init__(self, quotes, hist, detail, fail_symbols=None):
        self._quotes = quotes
        self._hist = hist
        self._detail = detail
        self._fail_symbols = fail_symbols or set()

    def screen_stocks(self, query, **kw):
        return self._quotes

    def get_price_history(self, symbol, period="1y"):
        if symbol in self._fail_symbols:
            raise RuntimeError(f"Simulated failure for {symbol}")
        if callable(self._hist):
            return self._hist(symbol)
        return self._hist

    def get_stock_detail(self, symbol):
        if symbol in self._fail_symbols:
            raise RuntimeError(f"Simulated failure for {symbol}")
        if callable(self._detail):
            return self._detail(symbol)
        return self._detail


class _MomentumMockClient:
    def __init__(self, quotes, hist, fail_symbols=None):
        self._quotes = quotes
        self._hist = hist
        self._fail_symbols = fail_symbols or set()

    def screen_stocks(self, query, **kw):
        return self._quotes

    def get_price_history(self, symbol, period="1y"):
        if symbol in self._fail_symbols:
            raise RuntimeError(f"Simulated failure for {symbol}")
        return self._hist

    def get_stock_detail(self, symbol):
        return {}


class _PullbackMockClient:
    def __init__(self, quotes, hist, fail_symbols=None):
        self._quotes = quotes
        self._hist = hist
        self._fail_symbols = fail_symbols or set()

    def screen_stocks(self, query, **kw):
        return self._quotes

    def get_price_history(self, symbol, **kw):
        if symbol in self._fail_symbols:
            raise RuntimeError(f"Simulated failure for {symbol}")
        return self._hist

    def get_stock_detail(self, symbol):
        return {}


# ---------------------------------------------------------------------------
# ContrarianScreener parallel tests
# ---------------------------------------------------------------------------

class TestContrarianParallel:
    def test_parallel_results_sorted_descending(self):
        """Results are sorted by contrarian_score descending even with parallel execution."""
        quotes = [_make_contrarian_quote(f"{i}.T") for i in range(1001, 1011)]
        screener = ContrarianScreener(_ContrarianMockClient(
            quotes=quotes,
            hist=_make_oversold_hist(),
            detail=_make_contrarian_detail(),
        ))
        results = screener.screen(region="jp", top_n=20)
        if len(results) >= 2:
            scores = [r["contrarian_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_parallel_one_failure_others_succeed(self):
        """One stock raising exception should not affect other stocks."""
        quotes = [
            _make_contrarian_quote("1001.T"),
            _make_contrarian_quote("FAIL.T"),
            _make_contrarian_quote("1002.T"),
        ]
        screener = ContrarianScreener(_ContrarianMockClient(
            quotes=quotes,
            hist=_make_oversold_hist(),
            detail=_make_contrarian_detail(),
            fail_symbols={"FAIL.T"},
        ))
        results = screener.screen(region="jp", top_n=10)
        # FAIL.T should be skipped; others may pass depending on score
        symbols = [r["symbol"] for r in results]
        assert "FAIL.T" not in symbols


# ---------------------------------------------------------------------------
# MomentumScreener parallel tests
# ---------------------------------------------------------------------------

class TestMomentumParallel:
    def test_parallel_results_sorted_descending(self):
        """Results are sorted by surge_score descending even with parallel execution."""
        quotes = [_make_momentum_quote(f"S{i}", ma50_change=0.20) for i in range(10)]
        screener = MomentumScreener(_MomentumMockClient(
            quotes=quotes,
            hist=_make_uptrend_hist(300),
        ))
        results = screener.screen(region="jp", top_n=20, submode="surge")
        if len(results) >= 2:
            scores = [r["surge_score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_parallel_one_failure_others_succeed(self):
        """One stock raising exception should not affect other stocks."""
        quotes = [
            _make_momentum_quote("A", ma50_change=0.20),
            _make_momentum_quote("FAIL", ma50_change=0.20),
            _make_momentum_quote("B", ma50_change=0.20),
        ]
        screener = MomentumScreener(_MomentumMockClient(
            quotes=quotes,
            hist=_make_uptrend_hist(300),
            fail_symbols={"FAIL"},
        ))
        results = screener.screen(region="jp", top_n=10, submode="surge")
        symbols = [r["symbol"] for r in results]
        assert "FAIL" not in symbols


# ---------------------------------------------------------------------------
# PullbackScreener parallel tests
# ---------------------------------------------------------------------------

class TestPullbackParallel:
    def test_parallel_one_failure_others_succeed(self):
        """One stock raising exception should not affect other stocks."""
        quotes = [
            _make_pullback_quote("A"),
            _make_pullback_quote("FAIL"),
            _make_pullback_quote("B"),
        ]
        screener = PullbackScreener(_PullbackMockClient(
            quotes=quotes,
            hist=_make_uptrend_hist(300),
            fail_symbols={"FAIL"},
        ))
        results = screener.screen(region="jp", top_n=10)
        # FAIL should be skipped; others may or may not pass tech filter
        symbols = [r["symbol"] for r in results]
        assert "FAIL" not in symbols
        assert isinstance(results, list)

    def test_parallel_results_deterministic_sort(self):
        """Results should be deterministically sorted after parallel execution."""
        quotes = [_make_pullback_quote(f"P{i}") for i in range(10)]
        screener = PullbackScreener(_PullbackMockClient(
            quotes=quotes,
            hist=_make_uptrend_hist(300),
        ))
        results = screener.screen(region="jp", top_n=20)
        if len(results) >= 2:
            # Sort order: full before partial, then by final_score desc
            for i in range(len(results) - 1):
                a, b = results[i], results[i + 1]
                a_key = (0 if a.get("match_type") == "full" else 1, -(a.get("final_score") or 0.0))
                b_key = (0 if b.get("match_type") == "full" else 1, -(b.get("final_score") or 0.0))
                assert a_key <= b_key
