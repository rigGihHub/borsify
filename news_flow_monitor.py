from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from news_impact_engine import build_news_impact_assessment

FLOW_WINDOW_DAYS = 30
RECENT_WINDOW_DAYS = 14
EARLY_WINDOW_DAYS = 7
MIN_POSITIVE_FLOW = 2


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _norm_title(value: Any) -> str:
    text = str(value or "").lower()
    text = text.translate(str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e"}))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse exact/syndicated headline duplicates conservatively.

    Same normalized headline on the same calendar day counts once. When duplicates exist,
    keep the version with the strongest source-quality label and available reaction data.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in items:
        title_key = _norm_title(row.get("title"))
        if not title_key:
            continue
        day = str(row.get("published_at") or "")[:10]
        key = (title_key, day)
        rank = (
            int(row.get("source_quality_score") or 0),
            int(bool(row.get("independent_source"))),
            int(math.isfinite(_num(row.get("immediate_reaction")))),
        )
        prev = best.get(key)
        if prev is None:
            best[key] = dict(row)
            best[key]["_dedupe_rank"] = rank
        elif rank > tuple(prev.get("_dedupe_rank", (0, 0, 0))):
            best[key] = dict(row)
            best[key]["_dedupe_rank"] = rank
    out = []
    for row in best.values():
        row.pop("_dedupe_rank", None)
        out.append(row)
    return sorted(out, key=lambda r: str(r.get("published_at") or ""), reverse=True)


def _median(rows: list[dict[str, Any]], key: str) -> float:
    vals = [_num(r.get(key)) for r in rows]
    vals = [x for x in vals if math.isfinite(x)]
    return float(np.median(vals)) if vals else np.nan


def build_news_flow_monitor(
    events: dict[str, Any] | None,
    price_history: pd.DataFrame | None,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Assess whether a *sequence* of news is changing and how price has absorbed it.

    This deliberately avoids a free-form sentiment score. It uses the same conservative
    headline taxonomy and source-quality rules as News Impact Engine, deduplicates
    syndicated headlines, and reports observed price association rather than causality.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    impact = build_news_impact_assessment(events or {}, price_history, now)
    items = _dedupe_items(list(impact.get("News Impact Items") or []))
    items = [r for r in items if r.get("age_days") is None or int(r.get("age_days")) <= FLOW_WINDOW_DAYS]

    recent = [r for r in items if r.get("age_days") is not None and int(r["age_days"]) <= RECENT_WINDOW_DAYS]
    early = [r for r in recent if int(r.get("age_days") or 0) <= EARLY_WINDOW_DAYS]
    prior = [r for r in items if r.get("age_days") is not None and RECENT_WINDOW_DAYS < int(r["age_days"]) <= FLOW_WINDOW_DAYS]

    strong_recent_pos = [r for r in recent if r.get("direction") == "positive" and int(r.get("headline_strength") or 0) >= 3]
    strong_recent_neg = [r for r in recent if r.get("direction") == "negative" and int(r.get("headline_strength") or 0) >= 3]
    independent_pos = [r for r in strong_recent_pos if bool(r.get("independent_source"))]
    independent_neg = [r for r in strong_recent_neg if bool(r.get("independent_source"))]
    early_pos = [r for r in early if r.get("direction") == "positive" and int(r.get("headline_strength") or 0) >= 3]
    early_neg = [r for r in early if r.get("direction") == "negative" and int(r.get("headline_strength") or 0) >= 3]
    prior_pos = [r for r in prior if r.get("direction") == "positive" and int(r.get("headline_strength") or 0) >= 3]
    prior_neg = [r for r in prior if r.get("direction") == "negative" and int(r.get("headline_strength") or 0) >= 3]

    immediate_pos = _median(independent_pos, "immediate_reaction")
    five_day_pos = _median(independent_pos, "five_day_reaction")
    drift_pos = _median(independent_pos, "post_news_drift")

    distinct_positive_days = len({str(r.get("published_at") or "")[:10] for r in independent_pos})
    positive_sequence = len(independent_pos) >= MIN_POSITIVE_FLOW and distinct_positive_days >= 2 and not independent_neg
    negative_sequence = len(independent_neg) >= 2 or (independent_neg and not independent_pos)

    # A change in direction means the recent 14d balance is materially better/worse
    # than the preceding 15–30d window. Counts are shown instead of a synthetic score.
    recent_balance = len(strong_recent_pos) - len(strong_recent_neg)
    prior_balance = len(prior_pos) - len(prior_neg)
    direction_shift = recent_balance - prior_balance

    price_pattern = "För lite reaktionsdata"
    if positive_sequence and math.isfinite(immediate_pos):
        if immediate_pos < 0.02 and math.isfinite(five_day_pos) and five_day_pos < 0.04:
            price_pattern = "Möjlig ackumulerad underreaktion"
        elif immediate_pos < 0.02 and math.isfinite(drift_pos) and drift_pos >= 0.02:
            price_pattern = "Fördröjd positiv kursbekräftelse"
        elif immediate_pos >= 0.04 or (math.isfinite(five_day_pos) and five_day_pos >= 0.07):
            price_pattern = "Positivt flöde verkar redan tydligt prisat"
        else:
            price_pattern = "Blandad prisabsorption"
    elif negative_sequence and math.isfinite(_median(independent_neg, "immediate_reaction")):
        price_pattern = "Negativt flöde med observerad kursreaktion"

    if independent_neg:
        status = "Försämrande nyhetsflöde" if negative_sequence else "Negativ nyhet bryter flödet"
        summary = "Färska negativa rubriker från stark källa väger tyngre än en positiv nyhetsserie tills originalinformationen är verifierad."
    elif positive_sequence and price_pattern == "Möjlig ackumulerad underreaktion":
        status = "Förbättrande flöde · möjlig underreaktion"
        summary = "Flera separata positiva nyheter från starka källor har kommit utan tydlig initial eller femdagars kursreaktion."
    elif positive_sequence and price_pattern == "Fördröjd positiv kursbekräftelse":
        status = "Förbättrande flöde · marknaden reagerar gradvis"
        summary = "Flera separata positiva nyheter följs av mer kursstöd efter den första reaktionen än direkt vid publicering."
    elif positive_sequence:
        status = "Förbättrande nyhetsflöde"
        summary = "Minst två separata positiva nyheter från starka källor finns i det senaste tvåveckorsfönstret."
    elif direction_shift >= 2 and len(strong_recent_pos) >= 2:
        status = "Nyhetsriktningen förbättras"
        summary = "Balansen mellan positiva och negativa rubriker har förbättrats jämfört med föregående halvmånad, men stödet är ännu inte tillräckligt oberoende."
    elif direction_shift <= -2 and len(strong_recent_neg) >= 1:
        status = "Nyhetsriktningen försämras"
        summary = "Balansen mellan positiva och negativa rubriker har försämrats jämfört med föregående halvmånad."
    elif recent:
        status = "Blandat nyhetsflöde"
        summary = "Det finns färska rubriker, men ingen tillräckligt tydlig serie av oberoende positiva eller negativa händelser."
    else:
        status = "För lite nyhetsflöde"
        summary = "Det finns inte tillräckligt med färska rubriker för att bedöma en förändring i nyhetsflödet."

    return {
        "News Flow Status": status,
        "News Flow Summary": summary,
        "News Flow Unique Items 30d": len(items),
        "News Flow Recent Items 14d": len(recent),
        "News Flow Positive 14d": len(strong_recent_pos),
        "News Flow Negative 14d": len(strong_recent_neg),
        "News Flow Independent Positive 14d": len(independent_pos),
        "News Flow Independent Negative 14d": len(independent_neg),
        "News Flow Early Positive 7d": len(early_pos),
        "News Flow Early Negative 7d": len(early_neg),
        "News Flow Prior Positive 15-30d": len(prior_pos),
        "News Flow Prior Negative 15-30d": len(prior_neg),
        "News Flow Direction Shift": direction_shift,
        "News Flow Distinct Positive Days": distinct_positive_days,
        "News Flow Price Pattern": price_pattern,
        "News Flow Median Immediate Positive": immediate_pos,
        "News Flow Median Five Day Positive": five_day_pos,
        "News Flow Median Positive Drift": drift_pos,
        "News Flow Warning": "Nyhetsserier och kursrörelser visar tidsmässiga samband, inte bevisad kausalitet. Dubletter tas bort och originalkällan ska verifieras.",
    }
