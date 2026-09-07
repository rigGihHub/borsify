from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from news_impact_engine import build_news_impact_assessment

FRESH_DAYS = 7
MIN_REFERENCE_EVENTS = 2


def _norm(value: Any) -> str:
    text = str(value or "").lower().translate(str.maketrans({"å":"a","ä":"a","ö":"o","é":"e"}))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%+\- ]+", " ", text)).strip()


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


POSITIVE_EXPECTATION_TERMS = (
    "beats expectations", "beats estimates", "beat estimates", "above expectations",
    "better than expected", "stronger than expected", "raises guidance", "raised guidance",
    "raises outlook", "raised outlook", "hojer prognos", "hojd prognos", "over forvantan",
    "battre an vantat", "starkare an vantat",
)
NEGATIVE_EXPECTATION_TERMS = (
    "misses expectations", "misses estimates", "missed estimates", "below expectations",
    "worse than expected", "weaker than expected", "cuts guidance", "cut guidance",
    "lowers guidance", "lowered outlook", "profit warning", "vinstvarning",
    "sanker prognos", "sankt prognos", "under forvantan", "samre an vantat",
)
EVENT_SURPRISE_TYPES = {
    "Order/kontrakt", "Regulatoriskt godkännande", "Insiderköp", "Återköp",
    "Emission/finansieringsrisk",
}


def classify_news_surprise(item: dict[str, Any]) -> tuple[str, str, int]:
    """Headline-only surprise proxy.

    It deliberately does not claim to know consensus magnitude. Explicit expectation
    language is stronger than merely positive/negative corporate-news wording.
    """
    title = _norm(item.get("title"))
    direction = str(item.get("direction") or "uncertain")
    kind = str(item.get("type") or "Oklart")
    if any(_norm(t) in title for t in NEGATIVE_EXPECTATION_TERMS):
        return "Tydlig negativ förväntningsöverraskning", "negative", 3
    if any(_norm(t) in title for t in POSITIVE_EXPECTATION_TERMS):
        return "Tydlig positiv förväntningsöverraskning", "positive", 3
    if kind in EVENT_SURPRISE_TYPES and direction in {"positive", "negative"}:
        label = "Möjlig positiv händelseöverraskning" if direction == "positive" else "Möjlig negativ händelseöverraskning"
        return label, direction, 2
    return "Ingen verifierbar överraskning i rubriken", "uncertain", 0


def _directional_return(direction: str, value: float) -> float:
    if not math.isfinite(value):
        return np.nan
    if direction == "positive":
        return value
    if direction == "negative":
        return -value
    return np.nan


def _response_label(direction: str, immediate: float, five_day: float, surprise_strength: int, independent: bool) -> str:
    di = _directional_return(direction, immediate)
    d5 = _directional_return(direction, five_day)
    if not math.isfinite(di):
        return "För lite kursdata"
    if di <= -0.02:
        return "Kursen motsäger rubrikens riktning"
    if di >= 0.08:
        return "Mycket stor direkt reaktion"
    if surprise_strength >= 3 and independent and di < 0.02:
        if math.isfinite(d5) and d5 >= 0.03:
            return "Liten direkt reaktion · senare bekräftelse"
        if math.isfinite(d5) and d5 < 0.03:
            return "Möjlig underreaktion på tydlig överraskning"
        return "Möjlig underreaktion · femdagarsutfall saknas"
    if di >= 0.03:
        return "Tydlig direkt reaktion"
    return "Begränsad direkt reaktion"


def build_news_surprise_response(
    events: dict[str, Any] | None,
    price_history: pd.DataFrame | None,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Separate headline surprise evidence from observed price response.

    No causal claim, no ranking score, and no invented consensus estimate. A relative
    response is only shown when at least two older same-type/same-direction events exist
    in the currently frozen 30-day context.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    impact = build_news_impact_assessment(events or {}, price_history, now)
    rows: list[dict[str, Any]] = []
    for raw in list(impact.get("News Impact Items") or []):
        row = dict(raw)
        surprise_label, surprise_direction, surprise_strength = classify_news_surprise(row)
        # When surprise wording is explicit, that direction takes precedence. Otherwise
        # the ordinary conservative headline direction remains available as context.
        direction = surprise_direction if surprise_strength >= 2 else str(row.get("direction") or "uncertain")
        immediate = _num(row.get("immediate_reaction"))
        five_day = _num(row.get("five_day_reaction"))
        row.update({
            "surprise_label": surprise_label,
            "surprise_direction": surprise_direction,
            "surprise_strength": surprise_strength,
            "response_label": _response_label(
                direction, immediate, five_day, surprise_strength, bool(row.get("independent_source"))
            ),
            "directional_immediate": _directional_return(direction, immediate),
            "directional_five_day": _directional_return(direction, five_day),
        })
        rows.append(row)

    fresh = [r for r in rows if r.get("age_days") is not None and int(r["age_days"]) <= FRESH_DAYS]
    meaningful = [r for r in fresh if int(r.get("surprise_strength") or 0) >= 2]
    # Negative surprise gets priority so positive headlines cannot hide fresh downside evidence.
    meaningful.sort(key=lambda r: (r.get("surprise_direction") != "negative", -int(r.get("surprise_strength") or 0), str(r.get("published_at") or "")))
    primary = meaningful[0] if meaningful else (fresh[0] if fresh else (rows[0] if rows else None))

    ref_n = 0
    ref_median = np.nan
    relative_gap = np.nan
    if primary and int(primary.get("surprise_strength") or 0) >= 2:
        p_type = str(primary.get("type") or "")
        p_dir = str(primary.get("surprise_direction") or "")
        older = [
            r for r in rows
            if r is not primary
            and r.get("age_days") is not None and int(r["age_days"]) > FRESH_DAYS
            and str(r.get("type") or "") == p_type
            and str(r.get("surprise_direction") or "") == p_dir
            and math.isfinite(_num(r.get("directional_immediate")))
        ]
        if len(older) >= MIN_REFERENCE_EVENTS:
            vals = [_num(r.get("directional_immediate")) for r in older]
            ref_n = len(vals)
            ref_median = float(np.median(vals))
            p_immediate = _num(primary.get("directional_immediate"))
            if math.isfinite(p_immediate):
                relative_gap = p_immediate - ref_median

    if primary is None:
        status = "Ingen bedömbar nyhet"
        summary = "Ingen rubrik med tillräckliga tids- och kursdata kunde bedömas."
    elif int(primary.get("surprise_strength") or 0) == 0:
        status = "Ingen tydlig överraskning"
        summary = "Färsk nyhet finns, men rubriken visar inte tydligt att marknadens förväntningar överraskades."
    else:
        status = str(primary.get("response_label") or "För lite kursdata")
        summary = f"{primary.get('surprise_label')}. {status}."

    underreaction = bool(primary and str(primary.get("response_label") or "").startswith("Möjlig underreaktion"))
    later_confirmation = bool(primary and "senare bekräftelse" in str(primary.get("response_label") or ""))
    adverse = bool(primary and str(primary.get("response_label") or "") == "Kursen motsäger rubrikens riktning")

    return {
        "News Surprise Status": status,
        "News Surprise Summary": summary,
        "News Surprise Fresh Count": len(fresh),
        "News Surprise Meaningful Count": len(meaningful),
        "News Surprise Primary Title": primary.get("title") if primary else "—",
        "News Surprise Primary Type": primary.get("type") if primary else "—",
        "News Surprise Primary Label": primary.get("surprise_label") if primary else "—",
        "News Surprise Primary Direction": primary.get("surprise_direction") if primary else "uncertain",
        "News Surprise Strength": int(primary.get("surprise_strength") or 0) if primary else 0,
        "News Surprise Immediate Reaction": _num(primary.get("immediate_reaction")) if primary else np.nan,
        "News Surprise Five Day Reaction": _num(primary.get("five_day_reaction")) if primary else np.nan,
        "News Surprise Directional Immediate": _num(primary.get("directional_immediate")) if primary else np.nan,
        "News Surprise Directional Five Day": _num(primary.get("directional_five_day")) if primary else np.nan,
        "News Surprise Underreaction": underreaction,
        "News Surprise Later Confirmation": later_confirmation,
        "News Surprise Adverse Reaction": adverse,
        "News Surprise Reference N": ref_n,
        "News Surprise Reference Median Immediate": ref_median,
        "News Surprise Relative Reaction Gap": relative_gap,
        "News Surprise Source Quality": primary.get("source_quality") if primary else "—",
        "News Surprise Warning": "Överraskning är en konservativ rubrikproxy, inte verifierad konsensusavvikelse. Kursrörelsen visar tidsmässig association, inte bevisad kausalitet.",
    }
