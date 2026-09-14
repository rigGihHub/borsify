from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _history(row: pd.Series | dict[str, Any]) -> pd.DataFrame:
    hist = row.get("_history")
    if not isinstance(hist, pd.DataFrame) or hist.empty:
        return pd.DataFrame()
    out = hist.copy()
    for c in ("High", "Low", "Close"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _atr14(hist: pd.DataFrame) -> float:
    if hist.empty or not {"High", "Low", "Close"}.issubset(hist.columns):
        return np.nan
    h, l, c = hist["High"], hist["Low"], hist["Close"]
    prev = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    val = tr.rolling(14, min_periods=10).mean().iloc[-1]
    return _num(val)


def _better_entry_zone(
    row: pd.Series | dict[str, Any],
    horizon: str,
    level: str,
    dist: float,
) -> dict[str, Any]:
    """Derive a *reference* entry zone from observed price structure.

    A zone is only produced for orange/red entry timing. It is anchored to actual
    trend/price-history inputs already available to Borsify. If the data cannot
    support a sensible lower zone, no price target is fabricated.
    """
    empty = {
        "Bättre ingång": "—",
        "Bättre ingång låg": np.nan,
        "Bättre ingång hög": np.nan,
        "Bättre ingång ankare": "—",
        "Bättre ingång skäl": "För lite prisstruktur för att ange en ärlig ingångszon.",
    }
    if level not in {"orange", "red"}:
        return {
            **empty,
            "Bättre ingång skäl": "Nuvarande ingångsläge kräver ingen särskild väntzon.",
        }

    price = _num(row.get("Pris"))
    if not np.isfinite(price) or price <= 0:
        return empty

    hist = _history(row)
    atr = _atr14(hist)
    candidates: list[tuple[str, float]] = []

    # Infer SMA200 from the frozen distance if both price and distance are known.
    if np.isfinite(dist) and dist > -0.95:
        sma200 = price / (1.0 + dist)
        desired_premium = {"medium": .08, "year": .12, "long": .16}.get(horizon, .10)
        trend_anchor = sma200 * (1.0 + desired_premium)
        if np.isfinite(trend_anchor) and trend_anchor < price:
            candidates.append(("SMA200 + rimlig trendpremie", float(trend_anchor)))

    if not hist.empty and "Close" in hist.columns:
        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if len(close) >= 15:
            ma20 = _num(close.tail(20).mean())
            if np.isfinite(ma20) and ma20 < price:
                candidates.append(("20-dagars prisstruktur", ma20))
        if len(close) >= 35:
            ma50 = _num(close.tail(50).mean())
            if np.isfinite(ma50) and ma50 < price:
                candidates.append(("50-dagars prisstruktur", ma50))
    if not hist.empty and "Low" in hist.columns:
        lows = pd.to_numeric(hist["Low"], errors="coerce").dropna()
        if len(lows) >= 15:
            # 20d low is an observed structure point, not an invented retracement.
            recent_low = _num(lows.tail(20).min())
            if np.isfinite(recent_low) and recent_low < price:
                candidates.append(("senaste 20 dagarnas observerade lågpunkt", recent_low))

    if not candidates:
        return empty

    # A "better" zone must actually be below today's price. Red cases require more
    # breathing room than orange cases; otherwise we would just relabel today's price.
    min_discount = .05 if level == "red" else .03
    max_anchor = price * (1.0 - min_discount)
    eligible = [(name, value) for name, value in candidates if value <= max_anchor]
    if not eligible:
        return empty

    # Prefer the nearest credible lower anchor so the zone remains actionable rather
    # than defaulting to an unnecessarily deep crash scenario.
    anchor_name, anchor = max(eligible, key=lambda x: x[1])

    if np.isfinite(atr) and atr > 0:
        half_width = max(0.45 * atr, 0.0125 * price)
    else:
        half_width = 0.02 * price

    low = max(0.01, anchor - half_width)
    high = min(anchor + half_width, price * (1.0 - .01))
    if high <= low or high >= price:
        return empty

    pct_to_high = high / price - 1.0
    pct_to_low = low / price - 1.0
    zone_text = f"{low:.2f}–{high:.2f}"
    reason = (
        f"Referenszonen förankras i {anchor_name}. "
        f"Det motsvarar ungefär {pct_to_high:.0%} till {pct_to_low:.0%} från dagens kurs. "
        + ("Zonbredden använder aktiens ATR." if np.isfinite(atr) and atr > 0 else "ATR saknas, så zonen görs konservativt bred utan att påstå exakt volatilitet.")
        + " Det är en teknisk väntzon, inte en prognos eller garanterad köpnivå."
    )
    return {
        "Bättre ingång": zone_text,
        "Bättre ingång låg": low,
        "Bättre ingång hög": high,
        "Bättre ingång ankare": anchor_name,
        "Bättre ingång skäl": reason,
    }


def assess_entry_timing(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Assess whether a good case is still a good *entry*.

    This is deliberately separate from the investment thesis. Strong momentum is not
    automatically bad, but a combination of very fast gains, extreme RSI and large
    distance from the long trend is treated as chasing risk.
    """
    daily = _num(row.get("Dagsförändring"))
    m1 = _num(row.get("1 mån"))
    m3 = _num(row.get("3 mån"))
    dist = _num(row.get("Avstånd SMA200"))
    rsi = _num(row.get("RSI14"))

    hot = []
    severe = []
    if np.isfinite(daily) and daily >= .07:
        hot.append("stor uppgång idag")
        if daily >= .10:
            severe.append("över 10 % upp på en dag")
    if np.isfinite(m1) and m1 >= .18:
        hot.append("snabb uppgång senaste månaden")
        if m1 >= .30:
            severe.append("över 30 % upp på en månad")
    if np.isfinite(m3) and m3 >= .35:
        hot.append("kraftig tremånadersuppgång")
        if m3 >= .60:
            severe.append("över 60 % upp på tre månader")
    if np.isfinite(dist) and dist >= .18:
        hot.append("långt över 200-dagarstrenden")
        if dist >= .28:
            severe.append("mycket långt över 200-dagarstrenden")
    if np.isfinite(rsi) and rsi >= 75:
        hot.append("hett RSI")
        if rsi >= 82:
            severe.append("extremt RSI")

    if horizon == "medium":
        red = bool(severe) or len(hot) >= 3 or (np.isfinite(m1) and m1 >= .25 and np.isfinite(dist) and dist >= .20)
        orange = bool(hot)
    elif horizon == "year":
        red = len(severe) >= 2 or (np.isfinite(m1) and m1 >= .35) or (np.isfinite(m3) and m3 >= .65)
        orange = bool(severe) or len(hot) >= 2
    else:  # lifetime/long
        red = (np.isfinite(m1) and m1 >= .40 and np.isfinite(dist) and dist >= .25) or (np.isfinite(rsi) and rsi >= 85)
        orange = bool(severe) or len(hot) >= 2

    if red:
        status = "🔴 Jaga inte"
        level = "red"
    elif orange:
        status = "🟠 Avvakta"
        level = "orange"
    elif len(hot) == 1:
        status = "🟡 Okej"
        level = "yellow"
    else:
        status = "🟢 Attraktivt"
        level = "green"

    waits = []
    if np.isfinite(rsi) and rsi >= 75:
        waits.append("att kursstyrkan kyls ned")
    if np.isfinite(dist) and dist >= .18:
        waits.append("att kursen kommer närmare sin långsiktiga trend")
    if np.isfinite(m1) and m1 >= .18:
        waits.append("en lugnare period eller rekyl")
    if not waits and orange:
        waits.append("ett mindre ansträngt ingångsläge")
    wait_for = ", ".join(waits[:2]) if waits else "ingen tydlig väntesignal"

    reason = "; ".join((severe + hot)[:3]) if (severe or hot) else "ingen tydlig översträckning i kursen"
    zone = _better_entry_zone(row, horizon, level, dist)
    return {
        "Ingångsläge": status,
        "Ingångsläge nivå": level,
        "Chasing-risk": bool(red),
        "Ingångsläge skäl": reason,
        "Vänta på": wait_for,
        **zone,
    }


def add_entry_timing(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    rows = [assess_entry_timing(r, horizon) for _, r in out.iterrows()]
    timing = pd.DataFrame(rows, index=out.index)
    overlap = [c for c in timing.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(timing)
