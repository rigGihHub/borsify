from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from catalyst_engine import classify_news_catalyst, assess_catalyst_source_quality

MAX_FRESH_DAYS = 7
MAX_CONTEXT_DAYS = 30


def _to_ts(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, utc=True)
        if isinstance(ts, pd.DatetimeIndex):
            ts = ts[0] if len(ts) else pd.NaT
        return None if pd.isna(ts) else pd.Timestamp(ts)
    except Exception:
        return None


def _pct(a: float, b: float) -> float:
    if not (math.isfinite(a) and math.isfinite(b)) or a == 0:
        return np.nan
    return b / a - 1.0


def _price_reaction(history: pd.DataFrame | None, published_at: Any) -> dict[str, Any]:
    """Measure close-to-close reaction around a news timestamp without inventing intraday precision."""
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Close" not in history:
        return {"status": "Prisdata saknas"}
    ts = _to_ts(published_at)
    if ts is None:
        return {"status": "Publiceringstid saknas"}

    h = history[["Close"]].copy().dropna()
    if h.empty:
        return {"status": "Prisdata saknas"}
    idx = pd.to_datetime(h.index, utc=True, errors="coerce")
    h = h.loc[~idx.isna()].copy()
    h.index = idx[~idx.isna()].normalize()
    h = h[~h.index.duplicated(keep="last")].sort_index()
    event_day = ts.normalize()
    pos = int(h.index.searchsorted(event_day, side="left"))
    if pos >= len(h):
        return {"status": "För ny för kursreaktion"}
    pre = pos - 1
    if pre < 0:
        return {"status": "För lite historik"}
    p0 = float(h.iloc[pre]["Close"])
    p1 = float(h.iloc[pos]["Close"])
    p2 = float(h.iloc[min(pos + 1, len(h) - 1)]["Close"])
    p5 = float(h.iloc[min(pos + 4, len(h) - 1)]["Close"])
    immediate = _pct(p0, p1)
    two_day = _pct(p0, p2)
    five_day = _pct(p0, p5)
    drift = five_day - immediate if math.isfinite(five_day) and math.isfinite(immediate) else np.nan
    return {
        "status": "OK",
        "event_session": str(h.index[pos].date()),
        "immediate": immediate,
        "two_day": two_day,
        "five_day": five_day,
        "post_news_drift": drift,
    }


def _reaction_label(direction: str, reaction: float) -> str:
    if not math.isfinite(reaction):
        return "Reaktion saknas"
    if direction == "positive":
        if reaction >= 0.03: return "Marknaden reagerade tydligt positivt"
        if reaction <= -0.02: return "Kursen gick emot den positiva rubriken"
        return "Svag kursreaktion på positiv rubrik"
    if direction == "negative":
        if reaction <= -0.03: return "Marknaden reagerade tydligt negativt"
        if reaction >= 0.02: return "Kursen gick emot den negativa rubriken"
        return "Svag kursreaktion på negativ rubrik"
    return "Neutral/oklar rubrik"


def build_news_impact_assessment(events: dict[str, Any] | None, price_history: pd.DataFrame | None,
                                 now: pd.Timestamp | None = None) -> dict[str, Any]:
    """Analyse fresh headline flow and observed price reaction conservatively.

    Headlines are triage evidence, not verified fundamentals. The engine never infers
    causal impact from price moves and never treats an unknown source as independent proof.
    """
    events = events or {}
    now = now or pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    rows: list[dict[str, Any]] = []
    for item in (events.get("news") or [])[:8]:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        ts = _to_ts(item.get("published_at"))
        age = None if ts is None else max(0, int((now.normalize() - ts.normalize()).days))
        if age is not None and age > MAX_CONTEXT_DAYS:
            continue
        kind, direction, strength = classify_news_catalyst(title)
        source_label, source_score, independent = assess_catalyst_source_quality(str(item.get("provider") or ""))
        reaction = _price_reaction(price_history, item.get("published_at"))
        immediate = reaction.get("immediate", np.nan)
        fresh = age is not None and age <= MAX_FRESH_DAYS
        rows.append({
            "title": title,
            "provider": str(item.get("provider") or ""),
            "published_at": None if ts is None else ts.isoformat(),
            "age_days": age,
            "type": kind,
            "direction": direction,
            "headline_strength": strength,
            "source_quality": source_label,
            "source_quality_score": source_score,
            "independent_source": independent,
            "fresh": fresh,
            "reaction_status": reaction.get("status"),
            "immediate_reaction": immediate,
            "two_day_reaction": reaction.get("two_day", np.nan),
            "five_day_reaction": reaction.get("five_day", np.nan),
            "post_news_drift": reaction.get("post_news_drift", np.nan),
            "reaction_label": _reaction_label(direction, immediate),
            "link": item.get("link"),
        })

    fresh_rows = [r for r in rows if r["fresh"]]
    negative = [r for r in fresh_rows if r["direction"] == "negative" and r["headline_strength"] >= 3]
    positive = [r for r in fresh_rows if r["direction"] == "positive" and r["headline_strength"] >= 3]
    underreacted = [r for r in positive if r["independent_source"] and math.isfinite(r["immediate_reaction"]) and r["immediate_reaction"] < 0.02]

    if negative:
        status = "Färsk negativ nyhet"
        summary = "En färsk negativ rubrik kräver verifiering innan caset stärks."
    elif underreacted:
        status = "Möjlig underreaktion"
        summary = "Positiv nyhet från stark källa men begränsad initial kursreaktion. Kontrollera originalkällan."
    elif positive:
        status = "Färsk positiv nyhet"
        summary = "Positiv färsk rubrik finns, men kursreaktion och originalkälla måste vägas in."
    elif fresh_rows:
        status = "Färskt nyhetsflöde"
        summary = "Färska rubriker finns men riktningen är ännu oklar."
    else:
        status = "Ingen färsk nyhet"
        summary = "Ingen färsk relevant rubrik kunde bedömas."

    primary = (negative or underreacted or positive or fresh_rows or rows)
    p = primary[0] if primary else None
    return {
        "News Impact Status": status,
        "News Impact Summary": summary,
        "News Impact Fresh Count": len(fresh_rows),
        "News Impact Positive Count": len(positive),
        "News Impact Negative Count": len(negative),
        "News Impact Underreaction Count": len(underreacted),
        "News Impact Primary Title": p.get("title") if p else "—",
        "News Impact Primary Direction": p.get("direction") if p else "uncertain",
        "News Impact Primary Reaction": p.get("immediate_reaction", np.nan) if p else np.nan,
        "News Impact Primary Drift": p.get("post_news_drift", np.nan) if p else np.nan,
        "News Impact Source Quality": p.get("source_quality") if p else "—",
        "News Impact Items": rows,
        "News Impact Warning": "Rubriker och kursrörelser visar samband, inte bevisad kausalitet. Verifiera originalnyheten.",
    }
