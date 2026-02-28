"""FX conversion utilities (KIK-511).

Consolidated FX rate fetching and currency conversion, previously
scattered across portfolio_manager.py and return_estimate.py.

Usage::

    from src.core.portfolio.fx_utils import get_fx_rates, convert_to_jpy

    rates = get_fx_rates(yahoo_client)
    jpy_value = convert_to_jpy(100.0, "USD", rates)
"""

from typing import Optional


# FX pairs to fetch for JPY conversion
FX_PAIRS = [
    "USDJPY=X",
    "SGDJPY=X",
    "THBJPY=X",
    "MYRJPY=X",
    "IDRJPY=X",
    "PHPJPY=X",
    "HKDJPY=X",
    "KRWJPY=X",
    "TWDJPY=X",
    "CNYJPY=X",
    "GBPJPY=X",
    "EURJPY=X",
    "CADJPY=X",
    "AUDJPY=X",
    "BRLJPY=X",
    "INRJPY=X",
]


def fx_symbol_for_currency(currency: str) -> Optional[str]:
    """Return the yfinance FX pair symbol for converting *currency* to JPY.

    Returns None if *currency* is already JPY (no conversion needed).
    """
    if currency == "JPY":
        return None
    return f"{currency}JPY=X"


def get_fx_rates(client) -> dict[str, float]:
    """Fetch major FX rates (per-unit JPY values) via yahoo_client.

    Parameters
    ----------
    client
        yahoo_client module (must expose ``get_stock_info``).

    Returns
    -------
    dict[str, float]
        ``{"JPY": 1.0, "USD": 150.5, "SGD": 112.3, ...}``
        Each value is the JPY amount for 1 unit of that currency.
        Currencies whose rate could not be fetched are omitted.
    """
    rates: dict[str, float] = {"JPY": 1.0}

    for pair in FX_PAIRS:
        currency = pair.replace("JPY=X", "")
        try:
            info = client.get_stock_info(pair)
            if info is not None and info.get("price") is not None:
                rates[currency] = float(info["price"])
            else:
                print(f"[fx_utils] Warning: FX rate for {pair} unavailable")
        except Exception as e:
            print(f"[fx_utils] Warning: FX rate fetch error for {pair}: {e}")

    return rates


def get_rate(currency: str, fx_rates: dict[str, float]) -> float:
    """Return the per-unit JPY rate for *currency*.

    Falls back to 1.0 (JPY equivalent) when the rate is not found.
    """
    if currency in fx_rates:
        return fx_rates[currency]
    print(
        f"[fx_utils] Warning: FX rate for {currency} not found, "
        f"assuming 1.0 (JPY equivalent)"
    )
    return 1.0


def convert_to_jpy(
    amount: float,
    currency: str,
    fx_rates: dict[str, float],
) -> float:
    """Convert *amount* in *currency* to JPY.

    Parameters
    ----------
    amount : float
        The value in the source currency.
    currency : str
        ISO currency code (e.g. "USD", "JPY").
    fx_rates : dict[str, float]
        FX rate table from :func:`get_fx_rates`.

    Returns
    -------
    float
        The value in JPY.
    """
    return amount * get_rate(currency, fx_rates)
