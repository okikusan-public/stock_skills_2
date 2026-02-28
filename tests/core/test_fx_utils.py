"""Tests for src.core.portfolio.fx_utils (KIK-511)."""

import pytest

from src.core.portfolio.fx_utils import (
    FX_PAIRS,
    convert_to_jpy,
    fx_symbol_for_currency,
    get_fx_rates,
    get_rate,
)


# ===================================================================
# FX_PAIRS constant
# ===================================================================


class TestFxPairs:
    def test_contains_usd(self):
        assert "USDJPY=X" in FX_PAIRS

    def test_contains_sgd(self):
        assert "SGDJPY=X" in FX_PAIRS

    def test_contains_eur(self):
        assert "EURJPY=X" in FX_PAIRS

    def test_all_end_with_jpy(self):
        for pair in FX_PAIRS:
            assert pair.endswith("JPY=X"), f"{pair} does not end with JPY=X"

    def test_no_duplicates(self):
        assert len(FX_PAIRS) == len(set(FX_PAIRS))


# ===================================================================
# fx_symbol_for_currency
# ===================================================================


class TestFxSymbolForCurrency:
    def test_usd(self):
        assert fx_symbol_for_currency("USD") == "USDJPY=X"

    def test_eur(self):
        assert fx_symbol_for_currency("EUR") == "EURJPY=X"

    def test_sgd(self):
        assert fx_symbol_for_currency("SGD") == "SGDJPY=X"

    def test_jpy_returns_none(self):
        assert fx_symbol_for_currency("JPY") is None

    def test_arbitrary_currency(self):
        assert fx_symbol_for_currency("XYZ") == "XYZJPY=X"


# ===================================================================
# get_fx_rates
# ===================================================================


class TestGetFxRates:
    def test_jpy_always_included(self):
        """JPY rate should always be 1.0, even with empty client."""
        class EmptyClient:
            def get_stock_info(self, symbol):
                return None
        rates = get_fx_rates(EmptyClient())
        assert rates["JPY"] == 1.0

    def test_successful_fetch(self):
        """Successfully fetched rates should appear in result."""
        class MockClient:
            def get_stock_info(self, symbol):
                if symbol == "USDJPY=X":
                    return {"price": 150.5}
                if symbol == "EURJPY=X":
                    return {"price": 165.2}
                return None

        rates = get_fx_rates(MockClient())
        assert rates["JPY"] == 1.0
        assert rates["USD"] == 150.5
        assert rates["EUR"] == 165.2

    def test_fetch_error_is_handled(self, capsys):
        """Client exceptions should be caught and logged."""
        class ErrorClient:
            def get_stock_info(self, symbol):
                raise ConnectionError("Network error")

        rates = get_fx_rates(ErrorClient())
        assert rates == {"JPY": 1.0}
        output = capsys.readouterr().out
        assert "Warning" in output

    def test_none_price_is_skipped(self, capsys):
        """None price should be skipped with a warning."""
        class NoneClient:
            def get_stock_info(self, symbol):
                return {"price": None}

        rates = get_fx_rates(NoneClient())
        assert rates == {"JPY": 1.0}
        output = capsys.readouterr().out
        assert "unavailable" in output

    def test_partial_success(self):
        """Some currencies succeed, others fail."""
        class PartialClient:
            def get_stock_info(self, symbol):
                if symbol == "USDJPY=X":
                    return {"price": 150.0}
                return None

        rates = get_fx_rates(PartialClient())
        assert rates["JPY"] == 1.0
        assert rates["USD"] == 150.0
        assert "SGD" not in rates


# ===================================================================
# get_rate
# ===================================================================


class TestGetRate:
    def test_known_currency(self):
        rates = {"JPY": 1.0, "USD": 150.0}
        assert get_rate("USD", rates) == 150.0

    def test_jpy(self):
        rates = {"JPY": 1.0, "USD": 150.0}
        assert get_rate("JPY", rates) == 1.0

    def test_unknown_currency_returns_one(self, capsys):
        rates = {"JPY": 1.0, "USD": 150.0}
        result = get_rate("EUR", rates)
        assert result == 1.0
        output = capsys.readouterr().out
        assert "EUR" in output
        assert "not found" in output

    def test_empty_rates_returns_one(self, capsys):
        result = get_rate("USD", {})
        assert result == 1.0


# ===================================================================
# convert_to_jpy
# ===================================================================


class TestConvertToJpy:
    def test_jpy_no_conversion(self):
        rates = {"JPY": 1.0, "USD": 150.0}
        assert convert_to_jpy(1000.0, "JPY", rates) == 1000.0

    def test_usd_to_jpy(self):
        rates = {"JPY": 1.0, "USD": 150.0}
        assert convert_to_jpy(100.0, "USD", rates) == 15000.0

    def test_zero_amount(self):
        rates = {"JPY": 1.0, "USD": 150.0}
        assert convert_to_jpy(0.0, "USD", rates) == 0.0

    def test_negative_amount(self):
        rates = {"JPY": 1.0, "USD": 150.0}
        assert convert_to_jpy(-50.0, "USD", rates) == -7500.0

    def test_unknown_currency_assumes_jpy(self, capsys):
        rates = {"JPY": 1.0}
        result = convert_to_jpy(1000.0, "XYZ", rates)
        assert result == 1000.0  # fallback: 1.0 rate

    def test_sgd_conversion(self):
        rates = {"JPY": 1.0, "SGD": 112.3}
        assert convert_to_jpy(100.0, "SGD", rates) == pytest.approx(11230.0)
