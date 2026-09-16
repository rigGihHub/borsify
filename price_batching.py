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
    max_missing_ratio: float = 0.25,
) -> list[str]:
    """Plan bounded single-symbol retries only for genuinely partial bulk success.

    Empty or heavily degraded multi-symbol responses usually signal a provider/batch
    failure. Serially retrying many constituents then makes the UI look frozen and
    amplifies Yahoo rate limits. We therefore retry only when most of the batch was
    returned successfully. A one-symbol final batch remains eligible for its normal
    fallback.
    """
    members = list(dict.fromkeys(str(symbol) for symbol in batch if str(symbol)))
    if max_fallbacks < 1 or not members:
        return []
    if not 0 <= max_missing_ratio <= 1:
        raise ValueError("max_missing_ratio must be between 0 and 1")

    missing = [symbol for symbol in members if symbol not in price_map]
    if not missing:
        return []
    if len(members) == 1:
        return missing[:max_fallbacks]
    if not price_map:
        return []

    # If the bulk provider returned only a minority of the requested batch, treat
    # that as a batch/provider incident rather than launching a serial retry storm.
    missing_ratio = len(missing) / len(members)
    if missing_ratio > max_missing_ratio:
        return []
    return missing[:max_fallbacks]
