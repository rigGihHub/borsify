import math
from fx import normalize_quote_currency, quote_amount_to_sek, major_amount_to_sek


def test_usd_quote_to_sek():
    assert quote_amount_to_sek(100, "USD", {"USD": 10.5}) == 1050


def test_lse_pence_quote_to_sek():
    # 500 GBp = 5 GBP.
    assert quote_amount_to_sek(500, "GBp", {"GBP": 13.0}) == 65
    assert normalize_quote_currency("GBp") == ("GBP", 0.01)


def test_market_cap_uses_major_currency_not_pence():
    assert major_amount_to_sek(2.0, "GBP", {"GBP": 13.0}) == 26.0


def test_missing_rate_returns_nan():
    assert math.isnan(quote_amount_to_sek(100, "USD", {}))
