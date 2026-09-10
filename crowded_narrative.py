"""Anti-consensus / Crowded Narrative context layer.

This is deliberately not a score. It identifies cases where a broad, very positive
analyst consensus coexists with limited remaining target upside and/or an already
stretched valuation signal. Popularity alone is never negative evidence.
"""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if np.isfinite(x) else np.nan
    except Exception:
        return np.nan


def build_crowded_narrative(row: pd.Series | dict[str, Any] | None) -> dict[str, Any]:
    r = row if row is not None else {}
    bull = _num(r.get("Konsensus bullish andel"))
    analysts = _num(r.get("Konsensus analytiker antal"))
    upside = _num(r.get("Riktkurs potential"))
    valuation = _num(r.get("Värdering"))

    broad = bool(np.isfinite(bull) and np.isfinite(analysts) and analysts >= 5)
    very_positive = bool(broad and bull >= 0.80)
    extreme = bool(broad and bull >= 0.90)
    limited_upside = bool(np.isfinite(upside) and upside <= 0.10)
    downside_to_target = bool(np.isfinite(upside) and upside < 0)
    stretched_valuation = bool(np.isfinite(valuation) and valuation <= 35)

    crowded = bool(very_positive and (limited_upside or stretched_valuation))
    strong_warning = bool(extreme and (downside_to_target or (limited_upside and stretched_valuation)))

    if not broad:
        status = "För lite bred konsensusdata"
        why = "Borsify kräver minst fem observerade analytiker innan en ensidig konsensusbild kan kallas trång."
    elif not very_positive:
        status = "Ingen trång positiv konsensus"
        why = "Analytikerkollektivet är inte tillräckligt ensidigt positivt för att ge en crowded-varning."
    elif strong_warning:
        status = "Mycket trång positiv förväntansbild"
        why = "Nästan hela analytikerkollektivet är positivt samtidigt som kvarvarande riktkursuppsida är liten och/eller värderingen redan är ansträngd. Ett bra bolag kan därför redan bära höga förväntningar."
    elif crowded and downside_to_target:
        status = "Positiv konsensus men riktkurserna ger ingen uppsida"
        why = "En stor majoritet av analytikerna är positiva, men aktuell kurs ligger redan över den observerade riktkursmedianen."
    elif crowded and limited_upside:
        status = "Trång positiv konsensus – begränsad uppsida"
        why = "En stor majoritet av analytikerna är positiva samtidigt som den observerade riktkursuppsidan är liten. Det kan betyda att mycket av caset redan är känt."
    elif crowded:
        status = "Trång positiv konsensus – hög förväntansnivå"
        why = "Analytikerna är ovanligt samstämmigt positiva samtidigt som Borsifys värderingssignal är ansträngd. Detta är en riskflagga, inte en säljsignal."
    else:
        status = "Positiv konsensus utan tydlig crowding"
        why = "Analytikerna är mycket positiva, men Borsify ser inte tillräckligt stöd för att säga att förväntningsbilden redan är trång."

    return {
        "Crowded status": status,
        "Crowded varning": crowded,
        "Crowded stark varning": strong_warning,
        "Crowded bullish andel": bull,
        "Crowded analytiker antal": analysts,
        "Crowded riktkurs potential": upside,
        "Crowded värdering": valuation,
        "Crowded förklaring": why,
    }
