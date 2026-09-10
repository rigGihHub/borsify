from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


STRONG_ACTIONS = {
    "medium": {"KÖP NU", "KÖP"},
    "year": {"KÖP / ÄG", "BYGG POSITION"},
    "lifetime": {"KÖP / ÄG LÅNGSIKTIGT", "BYGG LÅNGSIKTIGT"},
}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def classify_change(
    *,
    current_signal: str,
    current_rank: int,
    current_score: float,
    previous_rank: int | None,
    previous_score: float | None,
    horizon: str,
) -> tuple[str, str]:
    """Explain how a current horizon candidate changed since the prior saved scan.

    This is presentation-only. It never changes eligibility, score, action signal,
    or ranking. Missing history produces an explicit neutral state rather than an
    inferred improvement.
    """
    strong = str(current_signal) in STRONG_ACTIONS.get(horizon, set())
    if previous_rank is None:
        if strong:
            return "NY KÖPSIGNAL", "Ny i den här topp 10-listan och har samtidigt en köpbar handlingssignal."
        return "NY PÅ LISTAN", "Ny i den här topp 10-listan sedan föregående sparade analys."

    score_now = _num(current_score)
    score_prev = _num(previous_score)
    rank_delta = int(previous_rank) - int(current_rank)  # positive = improved
    score_delta = score_now - score_prev if np.isfinite(score_now) and np.isfinite(score_prev) else np.nan

    if (np.isfinite(score_delta) and score_delta >= 3.0) or rank_delta >= 2:
        return "STÄRKT", "Aktien har tydligt förbättrat sitt score eller sin placering sedan föregående sparade analys."
    if (np.isfinite(score_delta) and score_delta <= -3.0) or rank_delta <= -2:
        return "FÖRSVAGAD", "Aktien har tydligt tappat score eller placering sedan föregående sparade analys."
    return "OFÖRÄNDRAD", "Ingen tydlig förändring i score eller placering sedan föregående sparade analys."


def add_change_signals(current: pd.DataFrame, previous: pd.DataFrame, score_col: str, horizon: str) -> pd.DataFrame:
    if current is None or current.empty:
        return current.copy() if isinstance(current, pd.DataFrame) else pd.DataFrame()
    out = current.copy().reset_index(drop=True)
    prev_map: dict[str, dict[str, Any]] = {}
    if isinstance(previous, pd.DataFrame) and not previous.empty:
        for _, row in previous.iterrows():
            symbol = str(row.get("Ticker") or row.get("symbol") or "").upper().strip()
            if symbol:
                prev_map[symbol] = {
                    "rank": int(row.get("Rank") or row.get("rank") or 0) or None,
                    "score": row.get("Score") if "Score" in row else row.get("score"),
                }

    labels: list[str] = []
    texts: list[str] = []
    for i, row in out.iterrows():
        symbol = str(row.get("Ticker", "")).upper().strip()
        prev = prev_map.get(symbol, {})
        label, text = classify_change(
            current_signal=str(row.get("Signal", "")),
            current_rank=i + 1,
            current_score=_num(row.get(score_col)),
            previous_rank=prev.get("rank"),
            previous_score=prev.get("score"),
            horizon=horizon,
        )
        labels.append(label)
        texts.append(text)
    out["Förändring"] = labels
    out["Förändring förklaring"] = texts
    return out


def dropped_from_top10(current: pd.DataFrame, previous: pd.DataFrame) -> list[str]:
    """Symbols that were in the previous top 10 but are absent now.

    Deliberately called a list departure rather than a sell signal; falling out of a
    ranking alone is not enough evidence to tell a user to sell an existing holding.
    """
    if previous is None or previous.empty:
        return []
    current_symbols = set(current.get("Ticker", pd.Series(dtype=str)).astype(str).str.upper()) if current is not None else set()
    previous_symbols = []
    for _, row in previous.iterrows():
        symbol = str(row.get("Ticker") or row.get("symbol") or "").upper().strip()
        if symbol and symbol not in current_symbols:
            previous_symbols.append(symbol)
    return previous_symbols
