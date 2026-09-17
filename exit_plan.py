from __future__ import annotations

import math
from typing import Any


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else math.nan
    except Exception:
        return math.nan


def build_near_term_exit_plan(row: Any) -> dict[str, str]:
    """Explain when a near-term position should be reviewed/sold.

    Uses conditions rather than pretending Borsify knows an exact future date.
    """
    rsi = _num(row.get("RSI14"))
    m1 = _num(row.get("1 mån"))
    sma = _num(row.get("Avstånd SMA200"))
    risk = _num(row.get("Risk"))

    review = "Följ aktien varje börsdag. Gör en ny kontroll senast efter 1–4 veckor."
    sell_signals: list[str] = []
    if math.isfinite(rsi):
        sell_signals.append("sälj eller ta hem en del av vinsten om uppgången blir överhettad och sedan börjar tappa fart")
    if math.isfinite(m1):
        sell_signals.append("sälj om den korta uppgången tydligt vänder ned och köpskälet inte längre finns")
    if math.isfinite(sma):
        sell_signals.append("sälj om prisutvecklingen bryter ned så att den positiva trenden försvinner")
    if math.isfinite(risk) and risk < 55:
        sell_signals.append("var extra snabb att sälja om riskbilden försämras")
    if not sell_signals:
        sell_signals.append("sälj när det som gjorde aktien intressant på kort sikt inte längre gäller")

    return {
        "Tänkt tid att äga": "Några dagar till några veckor – inte ett långsiktigt köp.",
        "När ska jag kontrollera igen?": review,
        "När bör jag sälja?": " ".join(signal[0].upper() + signal[1:] + "." for signal in sell_signals[:3]),
        "Viktigt": "Borsify anger inte ett påhittat exakt säljdatum. Säljbeslutet ska bygga på vad som faktiskt händer med aktien.",
    }
