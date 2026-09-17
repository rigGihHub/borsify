from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

def _num(v: Any) -> float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception: return np.nan

def _pct(v: Any) -> str:
    x=_num(v); return "—" if not np.isfinite(x) else f"{x:+.1%}".replace(".", ",")

def _first_risk(row: pd.Series | dict[str,Any]) -> str:
    flags=str(row.get("Riskflaggor","") or "").strip()
    if flags and flags not in {"—","inga","Ingen"}:
        first=flags.split(",")[0].strip()
        if first: return first[0].upper()+first[1:]
    coverage=_num(row.get("Datatäckning"))
    if np.isfinite(coverage) and coverage < .70:
        return "Borsify saknar en del information om bolaget. Därför är bedömningen mer osäker."
    return "Borsify ser ingen enskild stor varningssignal i informationen som finns, men aktien kan fortfarande falla."

def _sentence(parts: list[str], fallback: str) -> str:
    if not parts: return fallback
    if len(parts)==1: return parts[0][0].upper()+parts[0][1:]+"."
    return (", ".join(parts[:-1])+" och "+parts[-1]+".")[0].upper() + (", ".join(parts[:-1])+" och "+parts[-1]+".")[1:]

def build_buy_card(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,str]:
    """Explain a possible buy in plain language using only observed model inputs."""
    quality=_num(row.get("Kvalitet")); risk=_num(row.get("Risk")); valuation=_num(row.get("Värdering"))
    invest=_num(row.get("INVEST Score")); m1=_num(row.get("1 mån")); m3=_num(row.get("3 mån"))
    vol=_num(row.get("Volymkvot")); rsi=_num(row.get("RSI14")); roe=_num(row.get("ROE")); margin=_num(row.get("Vinstmarginal"))
    reasons=[]
    if horizon=="day":
        if np.isfinite(vol) and vol>=1.2: reasons.append(f"ovanligt många handlar aktien just nu ({vol:.1f} gånger normal handel)")
        if np.isfinite(m1) and m1>0: reasons.append(f"priset har stigit {_pct(m1)} den senaste månaden")
        if np.isfinite(rsi) and 50<=rsi<=72: reasons.append("priset visar styrka utan att uppgången ser extrem ut")
        why=_sentence(reasons[:3],"Flera kortsiktiga tecken är positiva samtidigt.")
        now="Det här är främst ett kortsiktigt läge. Borsify ser stöd i den senaste handeln och prisutvecklingen just nu."
        change="Borsify blir mer försiktig om handeln tappar fart eller priset börjar falla tydligt."
    elif horizon=="medium":
        if np.isfinite(m3) and m3>0: reasons.append(f"priset har utvecklats {_pct(m3)} på tre månader")
        if np.isfinite(quality) and quality>=60: reasons.append("bolagets ekonomi får ett bra kvalitetsbetyg")
        if np.isfinite(risk) and risk>=60: reasons.append("Borsify ser färre tydliga risktecken än i många svagare kandidater")
        why=_sentence(reasons[:3],"Både bolaget och den senaste prisutvecklingen klarar Borsifys krav.")
        now="Borsify tycker att kombinationen av bolagets läge och de senaste månadernas utveckling är tillräckligt stark för att undersöka ett köp nu."
        change="Borsify blir mer försiktig om priset faller under flera månader eller om bolagets ekonomi försämras."
    elif horizon=="long":
        if np.isfinite(quality) and quality>=65: reasons.append("bolaget får ett högt betyg för kvalitet")
        if np.isfinite(valuation) and valuation>=60: reasons.append("priset ser rimligt ut jämfört med bolagets ekonomi")
        if np.isfinite(risk) and risk>=60: reasons.append("riskbilden är relativt stabil")
        if np.isfinite(invest) and invest>=65 and not reasons: reasons.append("den samlade långsiktiga analysen är stark")
        why=_sentence(reasons[:3],"Bolagets kvalitet, pris och risk fungerar bra tillsammans i Borsifys analys.")
        now="Poängen är inte bara att bolaget är bra. Borsify bedömer också att dagens pris är tillräckligt rimligt för ett långsiktigt köp."
        change="Borsify blir mer försiktig om bolaget tjänar sämre, riskerna ökar eller aktien blir för dyr jämfört med bolagets ekonomi."
    else:
        if np.isfinite(quality) and quality>=72: reasons.append("bolaget har mycket hög kvalitet i Borsifys analys")
        if np.isfinite(roe) and roe>=.15: reasons.append("bolaget är bra på att tjäna pengar på ägarnas kapital")
        if np.isfinite(margin) and margin>=.10: reasons.append("bolaget behåller en bra del av försäljningen som vinst")
        if np.isfinite(risk) and risk>=68: reasons.append("ekonomin ser relativt tålig ut")
        why=_sentence(reasons[:3],"Flera tecken tyder på att bolaget kan vara starkt under lång tid.")
        now="Det här är ett förslag för den som kan tänka sig att äga länge. Borsify letar efter företag som kan fortsätta vara bra, inte bara aktier som nyligen gått upp."
        change="Borsify blir mer försiktig om lönsamheten faller, skulderna blir ett större problem eller flera av bolagets långsiktiga styrkor försvinner."
    return {
        "Därför kan aktien vara värd att köpa": why,
        "Varför just nu": now,
        "Det här är den största risken": _first_risk(row),
        "Då skulle Borsify tänka om": change,
    }
