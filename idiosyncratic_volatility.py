from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

MIN_SESSIONS = 60


def _close(frame: pd.DataFrame) -> pd.Series:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Close" not in frame.columns:
        return pd.Series(dtype=float)
    s = pd.to_numeric(frame["Close"], errors="coerce").dropna()
    if isinstance(s.index, pd.DatetimeIndex):
        try:
            s.index = s.index.tz_localize(None)
        except TypeError:
            pass
    return s


def idiosyncratic_volatility(stock_history: pd.DataFrame, benchmark_history: pd.DataFrame, min_sessions: int = MIN_SESSIONS) -> dict[str, Any]:
    """Estimate stock-specific daily volatility after removing benchmark movement.

    This is a simple one-factor OLS diagnostic, not a forecast model. It uses only
    aligned historical daily returns and never treats high idiosyncratic volatility
    as positive evidence.
    """
    stock = _close(stock_history).pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    bench = _close(benchmark_history).pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    aligned = pd.concat([stock.rename("stock"), bench.rename("bench")], axis=1, join="inner").dropna()
    if len(aligned) < int(min_sessions):
        return {"Idiosynkratisk volatilitet status": "FÖR LITE UNDERLAG", "Idiosynkratisk volatilitet sessioner": int(len(aligned))}

    x = aligned["bench"].to_numpy(dtype=float)
    y = aligned["stock"].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    try:
        alpha, beta = np.linalg.lstsq(X, y, rcond=None)[0]
    except Exception:
        return {"Idiosynkratisk volatilitet status": "FÖR LITE UNDERLAG", "Idiosynkratisk volatilitet sessioner": int(len(aligned))}
    residual = y - (alpha + beta * x)
    idio_daily = float(np.std(residual, ddof=2)) if len(residual) > 2 else np.nan
    total_daily = float(np.std(y, ddof=1)) if len(y) > 1 else np.nan
    annual = idio_daily * math.sqrt(252) if math.isfinite(idio_daily) else np.nan
    share = idio_daily / total_daily if math.isfinite(idio_daily) and math.isfinite(total_daily) and total_daily > 0 else np.nan

    # Deliberately broad guardrail bands. This is a risk clue, not a new score.
    if not math.isfinite(annual):
        status = "FÖR LITE UNDERLAG"
    elif annual >= 0.55 or (math.isfinite(share) and share >= 0.92 and annual >= 0.40):
        status = "MYCKET HÖG BOLAGSSPECIFIK RISK"
    elif annual >= 0.38 or (math.isfinite(share) and share >= 0.82 and annual >= 0.30):
        status = "HÖG BOLAGSSPECIFIK RISK"
    else:
        status = "INGEN TYDLIG EXTRA RISK"
    return {
        "Idiosynkratisk volatilitet status": status,
        "Idiosynkratisk volatilitet": annual,
        "Idiosynkratisk volatilitet andel": share,
        "Idiosynkratisk beta": float(beta),
        "Idiosynkratisk volatilitet sessioner": int(len(aligned)),
        "Idiosynkratisk volatilitet förklaring": "Hur mycket aktien svänger efter att den vanliga marknadsrörelsen räknats bort.",
    }


def apply_idiosyncratic_volatility(frame: pd.DataFrame, benchmark_history: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if out.empty:
        return out
    rows = []
    for _, row in out.iterrows():
        hist = row.get("_history")
        rows.append(idiosyncratic_volatility(hist if isinstance(hist, pd.DataFrame) else pd.DataFrame(), benchmark_history))
    metrics = pd.DataFrame(rows, index=out.index)
    for col in metrics.columns:
        out[col] = metrics[col]
    return out
