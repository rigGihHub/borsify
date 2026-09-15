from __future__ import annotations

"""Pure planning helpers for resilient, observable price acquisition."""

from collections.abc import Iterable, Mapping
from typing import Any


def symbol_batches(symbols: Iterable[str], batch_size: int = 40) -> list[tuple[str, ...]]:
    """Return stable, de-duplicated symbol batches without inventing work."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    unique = list(dict.fromkeys(str(symbol) for symbol in symbols if str(symbol)))
    return [tuple(unique[start:start + batch_size]) for start in range(0, len(unique), batch_size)]


def partial_fallback_symbols(
    batch: Iterable[str],
    price_map: Mapping[str, Any],
    max_fallbacks: int = 8,
) -> list[str]:
    """Plan bounded single-symbol retries only when a bulk batch partly succeeded.

    An empty multi-symbol response usually signals a provider/batch failure. Retrying
    every constituent serially makes the UI appear frozen and amplifies rate limits.
    A one-symbol final batch remains eligible for its normal single-symbol fallback.
    """
    members = list(batch)
    if max_fallbacks < 1 or not members:
        return []
    if not price_map and len(members) > 1:
        return []
    return [symbol for symbol in members if symbol not in price_map][:max_fallbacks]
