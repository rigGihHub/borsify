from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def _pct(v: Any) -> str:
    x=_num(v)
    return "—" if not np.isfinite(x) else f"{x:+.1%}".replace(".", ",")

def _first_risk(row: pd.Series | dict[str,Any]) -> str:
    flags=str(row.get("Riskflaggor","") or "").strip()
    if flags and flags not in {"—","inga","Ingen"}:
        first=flags.split(",")[0].strip()
        if first:
            return first[0].upper()+first[1:]
    coverage=_num(row.get("Datatäckning"))
    if np.isfinite(coverage) and coverage < .70:
        return "Underlaget är inte komplett, så bedömningen är mer osäker än vanligt."
    return "Ingen enskild stor risk sticker ut i den data Borsify har, men aktien kan fortfarande falla."

def build_buy_card(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,str]:
    """Create four short, beginner-friendly decision prompts from existing data only."""
    quality=_num(row.get("Kvalitet"))
    risk=_num(row.get("Risk"))
    valuation=_num(row.get("Värdering"))
    invest=_num(row.get("INVEST Score"))
    m1=_num(row.get("1 mån"))
    m3=_num(row.get("3 mån"))
    vol=_num(row.get("Volymkvot"))
    rsi=_num(row.get("RSI14"))
    roe=_num(row.get("ROE"))
    margin=_num(row.get("Vinstmarginal"))

    if horizon=="day":
        reasons=[]
        if np.isfinite(vol) and vol>=1.2: reasons.append("handeln i aktien är ovanligt aktiv")
        if np.isfinite(m1) and m1>0: reasons.append(f"kursen har stigit {_pct(m1)} den senaste månaden")
        if np.isfinite(rsi) and 50<=rsi<=72: reasons.append("kursstyrkan är positiv utan att vara extrem")
        why=" och ".join(reasons[:2]) if reasons else "flera kortsiktiga signaler pekar åt samma håll"
        why_now=(
            f"Den senaste handelsaktiviteten är {vol:.1f} gånger normal nivå."
            if np.isfinite(vol) and vol>=1.2 else
            "Borsify ser en kombination av aktuell kursstyrka och trend som klarar köpkraven just nu."
        )
        change=(
            "Borsify skulle ändra sig om handelsaktiviteten faller tydligt, kursstyrkan blir extrem "
            "eller den korta trenden vänder kraftigt ned."
        )
    elif horizon=="medium":
        reasons=[]
        if np.isfinite(m3) and m3>0: reasons.append(f"kursen har utvecklats {_pct(m3)} på tre månader")
        if np.isfinite(quality) and quality>=60: reasons.append("bolagets kvalitet är god")
        if np.isfinite(risk) and risk>=60: reasons.append("riskbilden är relativt stabil")
        why=" och ".join(reasons[:2]) if reasons else "både kursutveckling och bolagsdata klarar Borsifys krav"
        why_now=(
            "Den senaste 1–3-månadersutvecklingen är positiv samtidigt som bolaget klarar kvalitetskraven."
            if (np.isfinite(m3) and m3>0) else
            "Aktien klarar köpkraven nu utan att Borsify behöver fylla ut listan med svagare kandidater."
        )
        change=(
            "Borsify skulle ändra sig om både den senaste månaden och tremånaderstrenden blir tydligt negativa, "
            "eller om bolagets kvalitet eller riskbedömning försämras."
        )
    elif horizon=="long":
        reasons=[]
        if np.isfinite(invest) and invest>=65: reasons.append("den långsiktiga helhetsbedömningen är stark")
        if np.isfinite(quality) and quality>=65: reasons.append("bolagets kvalitet är hög")
        if np.isfinite(valuation) and valuation>=60: reasons.append("priset ser rimligt ut i förhållande till bolaget")
        why=" och ".join(reasons[:2]) if reasons else "bolagets kvalitet, pris och riskbild fungerar tillsammans"
        why_now=(
            "Aktien klarar både den långsiktiga helhetsbedömningen och Borsifys skärpta köpkrav."
        )
        change=(
            "Borsify skulle ändra sig om bolagets kvalitet faller tydligt, riskbilden försämras kraftigt "
            "eller priset inte längre ser rimligt ut i förhållande till bolagets utveckling."
        )
    else:
        reasons=[]
        if np.isfinite(quality) and quality>=72: reasons.append("bolagets kvalitet är mycket hög")
        if np.isfinite(risk) and risk>=68: reasons.append("ekonomin och riskbilden ser robusta ut")
        if np.isfinite(roe) and roe>=.15: reasons.append("bolaget tjänar bra på det kapital ägarna satsat")
        if np.isfinite(margin) and margin>=.10: reasons.append("lönsamheten är god")
        why=" och ".join(reasons[:2]) if reasons else "flera tecken på uthållig kvalitet finns samtidigt"
        why_now=(
            "Bolaget klarar de hårdaste köpkraven i Borsify och visar flera tecken på uthållig kvalitet."
        )
        change=(
            "Borsify skulle ändra sig om lönsamheten försämras tydligt, skuldrisken ökar, "
            "bolagets kvalitet faller eller flera av de långsiktiga styrkorna försvinner."
        )

    return {
        "Varför köpa": why[0].upper()+why[1:]+"." if why else "—",
        "Varför nu": why_now,
        "Största risk": _first_risk(row),
        "Vad skulle få Borsify att ändra sig": change,
    }
