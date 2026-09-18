from __future__ import annotations
from typing import Any
import pandas as pd

_EMPTY = {"", "—", "-", "nan", "none"}

def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _EMPTY else text

def _first(row, *keys: str, default: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return default

def _expectations(text: str) -> str:
    low = text.lower()
    if "hög" in low:
        return "Priset verkar redan räkna med att mycket ska gå bra. Då kan aktien falla om bolaget gör marknaden besviken."
    if "låg" in low:
        return "Priset verkar inte kräva att allt går perfekt för bolaget."
    if "rimlig" in low:
        return "Priset verkar bygga på ganska rimliga förväntningar."
    return "Borsify kan inte säga säkert hur mycket framtida framgång som redan finns inräknad i priset."

def _timing(text: str) -> str:
    if not text or "okänd" in text.lower():
        return "Borsify vet inte när fler investerare kan börja se aktien på ett nytt sätt."
    return text.replace("Recognition", "förändring")

def _confidence(text: str) -> str:
    low = text.lower()
    if "begrän" in low:
        return "Borsify saknar en del information. Därför är bedömningen mer osäker."
    if "hög" in low:
        return "Borsify har bra information att bygga analysen på."
    if "medel" in low:
        return "Borsify har ganska bra information, men det finns fortfarande luckor."
    return "Det är osäkert hur komplett informationen är."

def build_decision_brief(row) -> dict[str, Any]:
    decision = _first(row, "Signal", "Decision Support action", default="BEVAKA")
    decision_short = _first(row, "Signal kort", "Decision Support", default="Borsify har inte tillräckligt bra information för ett tydligt beslut.")
    thesis = _first(row, "Varför köpa", "Horisontförklaring", "Affärsläge förklaring", default="Borsify ser ännu inget tillräckligt tydligt skäl att köpa aktien.")
    market_wrong = _first(row, "Market Blind Spot reasons", "Early Mispricing stöd", "Value Trap stöd", default="Borsify kan inte säkert förklara varför andra investerare skulle värdera aktien för lågt.")
    expectations = _expectations(_first(row, "Market-Implied Expectations", default=""))
    recognition = _first(row, "Varför nu", "Catalyst Why Now", default="Borsify ser ingen tydlig händelse som kan göra aktien mer intressant snart.")
    timing = _timing(_first(row, "Recognition Window", default=""))
    payoff = _first(row, "Recognition Window payoff", default="Borsify kan inte säga säkert hur stor uppgången kan bli eller hur lång tid den kan ta.")
    risk = _first(row, "Största risk", "Riskflaggor", default="Borsify ser ingen enskild stor varningssignal, men aktien kan fortfarande falla.")
    invalidation = _first(row, "Vad ändrar Borsifys syn", "Vänta på", default="Borsify blir mer försiktig om bolaget börjar gå sämre eller riskerna ökar.")
    confidence = _confidence(_first(row, "Analysis Confidence", default=""))
    return {
        "Decision Brief beslut": decision, "Decision Brief kort": decision_short,
        "Decision Brief tes": thesis, "Decision Brief market wrong": market_wrong,
        "Decision Brief expectations": expectations, "Decision Brief recognition": recognition,
        "Decision Brief timing": timing, "Decision Brief payoff": payoff,
        "Decision Brief risk": risk, "Decision Brief invalidation": invalidation,
        "Decision Brief confidence": confidence,
    }

def add_decision_briefs(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    extra = pd.DataFrame([build_decision_brief(row) for _, row in out.iterrows()], index=out.index)
    overlap = [c for c in extra.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
