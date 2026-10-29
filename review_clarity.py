"""Observation-based data status and explicitly hypothetical valuation arithmetic."""
import math
import pandas as pd


def earnings_hurdle(pe, terminal_pe=25, years=5, annual_return=.10):
    """Required EPS CAGR: P0/E0 = PE0; Pn = En*PEn. No dividends assumed.

    This is a sensitivity calculation, not a forecast, target or fair value.
    Earnings are per share so dilution cannot be ignored by growing total profit.
    """
    try:
        pe, terminal_pe, years, annual_return = map(float, (pe, terminal_pe, years, annual_return))
    except (ValueError, TypeError):
        return None
    if not all(math.isfinite(x) for x in (pe, terminal_pe, years, annual_return)):
        return None
    if pe <= 0 or terminal_pe <= 0 or years <= 0 or annual_return <= -1:
        return None
    return (pe / terminal_pe) ** (1 / years) * (1 + annual_return) - 1


def observation_status(frame, now=None):
    """Report oldest observations and missing/future timestamps separately.

    Never infer data freshness from a scan/save/manual-refresh timestamp.
    Market holidays are not known here; report calendar age without asserting an
    instrument should have traded on a particular day.
    """
    now = pd.Timestamp(now or pd.Timestamp.now(tz="UTC"))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    result = {"rows": len(frame)}
    for key, column, days in [("prices", "Prisdatum", 7), ("fundamentals", "Fundamental hämtad", 3)]:
        stamps = pd.to_datetime(frame.get(column, pd.Series(index=frame.index, dtype=str)), utc=True, errors="coerce", format="mixed")
        future = stamps > now
        valid = stamps.notna() & ~future
        age = (now - stamps).dt.total_seconds() / 86400
        result[key] = {"known": int(valid.sum()), "missing": int(stamps.isna().sum()),
                       "future": int(future.sum()), "old": int((valid & age.gt(days)).sum()),
                       "oldest": stamps[valid].min().isoformat() if valid.any() else None}
    return result
