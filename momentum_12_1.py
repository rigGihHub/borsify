from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def momentum_12_1_return(close: pd.Series, long_days: int = 252, skip_days: int = 21) -> float:
    """Classic 12–1 momentum proxy: return from ~12 months ago to ~1 month ago.

    Uses only observations available at the snapshot date and deliberately excludes the
    most recent month so a short squeeze/rally is not confused with persistent momentum.
    """
    if close is None:
        return np.nan
    s = pd.to_numeric(close, errors="coerce").dropna()
    if len(s) <= skip_days:
        return np.nan
    end = len(s) - 1 - skip_days
    start = max(0, len(s) - 1 - long_days)
    # Do not label a short history as 12–1 momentum. Require roughly nine months.
    if end - start < 168:
        return np.nan
    base = _num(s.iloc[start]); last = _num(s.iloc[end])
    if not math.isfinite(base) or not math.isfinite(last) or base <= 0:
        return np.nan
    return float(last / base - 1.0)


def momentum_12_1_score(ret: Any) -> float:
    """Conservative confirmation score; extreme past winners are capped, not extrapolated."""
    r = _num(ret)
    if not math.isfinite(r):
        return np.nan
    # -25% -> 0, 0% -> 31, +40% -> 81, +55% -> 100. No bonus beyond the cap.
    return float(np.clip((r + 0.25) / 0.80 * 100.0, 0.0, 100.0))


def momentum_12_1_label(ret: Any) -> str:
    r = _num(ret)
    if not math.isfinite(r):
        return "För lite historik"
    if r >= 0.35:
        return "Starkt längre momentum"
    if r >= 0.12:
        return "Positivt längre momentum"
    if r > -0.10:
        return "Neutralt längre momentum"
    return "Svagt längre momentum"


def combine_momentum(short_score: Any, long_score: Any) -> tuple[float, str]:
    """Keep recent timing primary while adding independent longer-horizon confirmation."""
    s = _num(short_score); l = _num(long_score)
    if not math.isfinite(s) and not math.isfinite(l):
        return 45.0, "för lite kursdata"
    if not math.isfinite(l):
        return float(s), "12–1 saknas; kortare momentum används"
    if not math.isfinite(s):
        return float(l), "bara 12–1 momentum finns"
    combined = 0.65 * s + 0.35 * l
    if s >= 60 and l >= 60:
        text = "kort och längre momentum bekräftar varandra"
    elif s >= 60 and l < 40:
        text = "kort uppgång saknar stöd i längre momentum"
    elif s < 40 and l >= 60:
        text = "längre momentum är positivt men senaste tiden är svag"
    else:
        text = "blandad momentumbild"
    return float(np.clip(combined, 0.0, 100.0)), text
