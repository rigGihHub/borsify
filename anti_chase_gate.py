from __future__ import annotations

import math
from typing import Any


def _num(value: Any) -> float:
    try:
        x=float(value); return x if math.isfinite(x) else math.nan
    except Exception: return math.nan


def anti_chase_decision(row: Any, horizon: str) -> dict[str, Any]:
    """Hard buy-now guard: a good company can still be a bad entry today."""
    m1=_num(row.get("1 mån")); m3=_num(row.get("3 mån")); daily=_num(row.get("Dagsförändring"))
    rsi=_num(row.get("RSI14")); dist=_num(row.get("Avstånd SMA200"))
    reasons=[]

    # One-year lists are deliberately stricter than the old entry-timing thresholds.
    if horizon in {"year", "long"}:
        if math.isfinite(m1) and m1 >= .25: reasons.append("aktien har redan stigit minst 25 % på en månad")
        if math.isfinite(m1) and math.isfinite(m3) and m1 >= .18 and m3 >= .30:
            reasons.append("uppgången är redan kraftig både på en och tre månader")
        if math.isfinite(m3) and m3 >= .50: reasons.append("aktien har redan stigit minst 50 % på tre månader")
    else:
        if math.isfinite(m1) and m1 >= .30: reasons.append("aktien har redan rusat på en månad")

    if math.isfinite(daily) and daily >= .10: reasons.append("aktien har rusat minst 10 % på en dag")
    if math.isfinite(rsi) and rsi >= 82: reasons.append("priset ser extremt överhettat ut")
    if math.isfinite(dist) and dist >= .28: reasons.append("priset ligger mycket långt över sin långsiktiga trend")

    blocked=bool(reasons)
    return {
        "Köp nu efter rusning": not blocked,
        "Köp nu efter rusning skäl": "; ".join(reasons[:3]) if reasons else "ingen tydlig kursrusning som stoppar köp idag",
        "Köp nu efter rusning text": (
            "Bra bolag kan fortfarande vara ett dåligt köp idag. Vänta på ett lugnare eller billigare läge."
            if blocked else "Kursen har inte rusat så mycket att Borsify stoppar köp av den anledningen."
        ),
    }
