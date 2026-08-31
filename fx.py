from __future__ import annotations

import math
from typing import Mapping, Any

# Yahoo Finance symbols where the quote means SEK for one unit of the base currency.
FX_TO_SEK_SYMBOLS = {
    "USD": "USDSEK=X",
    "EUR": "EURSEK=X",
    "GBP": "GBPSEK=X",
    "DKK": "DKKSEK=X",
    "NOK": "NOKSEK=X",
    "CHF": "CHFSEK=X",
    "CAD": "CADSEK=X",
    "JPY": "JPYSEK=X",
}

# Some exchanges quote shares in a sub-unit even though the underlying currency is a
# major unit. LSE commonly uses GBp/GBX (pence). The factor converts quote units to
# one major currency unit before the FX conversion.
QUOTE_UNIT_MAP = {
    "GBP": ("GBP", 1.0),
    "GBPENCE": ("GBP", 0.01),
    "GBPENNY": ("GBP", 0.01),
    "GBPEN": ("GBP", 0.01),
    "GBX": ("GBP", 0.01),
    "GBP.": ("GBP", 1.0),
    "GBP ": ("GBP", 1.0),
    "GBp": ("GBP", 0.01),
}


def _finite(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else math.nan
    except (TypeError, ValueError):
        return math.nan


def normalize_quote_currency(currency: str | None) -> tuple[str, float]:
    """Return (major currency, quote-unit multiplier).

    Example: GBp/GBX is quoted in pence, so 100 GBp = 1 GBP and the multiplier is .01.
    """
    raw = str(currency or "").strip()
    if not raw:
        return "SEK", 1.0
    # Preserve the case-sensitive Yahoo GBp convention before normalising.
    if raw in {"GBp", "GBX"}:
        return "GBP", 0.01
    upper = raw.upper()
    if upper in {"GBPENCE", "GBPENNY", "GBPEN"}:
        return "GBP", 0.01
    return upper, 1.0


def major_currency(currency: str | None) -> str:
    return normalize_quote_currency(currency)[0]


def quote_amount_to_sek(amount: Any, currency: str | None, rates: Mapping[str, float]) -> float:
    value = _finite(amount)
    if not math.isfinite(value):
        return math.nan
    major, unit_factor = normalize_quote_currency(currency)
    if major == "SEK":
        return value * unit_factor
    rate = _finite(rates.get(major))
    if not math.isfinite(rate) or rate <= 0:
        return math.nan
    return value * unit_factor * rate


def major_amount_to_sek(amount: Any, currency: str | None, rates: Mapping[str, float]) -> float:
    """Convert an amount already expressed in major currency units (e.g. market cap)."""
    value = _finite(amount)
    if not math.isfinite(value):
        return math.nan
    major = major_currency(currency)
    if major == "SEK":
        return value
    rate = _finite(rates.get(major))
    if not math.isfinite(rate) or rate <= 0:
        return math.nan
    return value * rate
