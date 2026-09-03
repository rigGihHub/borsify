from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

from buy_quality_gate import BUY_THRESHOLDS, apply_buy_gate
from market_regime import add_market_regime

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def assess_overextension(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,Any]:
    """Detect when price has already moved unusually far.

    This is intentionally conservative. It does not claim the stock must fall;
    it says that the entry may have become less attractive after a fast move.
    """
    rsi=_num(row.get("RSI14"))
    daily=_num(row.get("Dagsförändring"))
    m1=_num(row.get("1 mån"))
    m3=_num(row.get("3 mån"))
    dist=_num(row.get("Avstånd SMA200"))

    warnings=[]
    severe=[]

    if np.isfinite(rsi) and rsi > 79:
        warnings.append("kursstyrkan är extremt hög just nu")
        if rsi >= 84:
            severe.append("mycket hög kortsiktig kursstyrka")
    if np.isfinite(daily) and daily > .07:
        warnings.append("aktien har stigit mer än 7 % idag")
        if daily > .10:
            severe.append("mycket stor uppgång på en enda dag")
    if np.isfinite(m1) and m1 > .25:
        warnings.append("aktien har stigit mer än 25 % på en månad")
        if m1 > .40:
            severe.append("extrem uppgång den senaste månaden")
    if np.isfinite(m3) and m3 > .55:
        warnings.append("aktien har stigit mer än 55 % på tre månader")
    if np.isfinite(dist) and dist > .20:
        warnings.append("kursen ligger mer än 20 % över sin långsiktiga trend")
        if dist > .30:
            severe.append("kursen ligger mycket långt över sin långsiktiga trend")

    # For very short horizons a combination of two warnings is enough to make
    # chasing the move unattractive. Long-term lists retain the candidate but warn.
    severe_for_horizon = bool(severe) or (horizon in {"day","medium"} and len(warnings) >= 2)
    if severe_for_horizon:
        status="FÖR SENT ATT JAGA?"
    elif warnings:
        status="VAR FÖRSIKTIG"
    else:
        status="NORMALT KÖPLÄGE"

    return {
        "Köpläge": status,
        "För långt gången": bool(severe_for_horizon),
        "Köplägesvarningar": "; ".join(warnings) if warnings else "ingen tydlig översträckning",
        "Köplägesförklaring": (
            "Aktien kan fortfarande vara bra, men den har redan rört sig så kraftigt att ett nytt köp riskerar att ske efter en stor del av uppgången."
            if severe_for_horizon else
            "Aktien har gått starkt och bör inte jagas utan ytterligare bekräftelse."
            if warnings else
            "Borsify ser ingen tydlig signal om att kursen redan gått ovanligt långt."
        ),
    }

def _hard_blocker(text: str) -> bool:
    t=str(text or "").lower()
    hard_terms=[
        "otillräcklig marknadsdatakvalitet",
        "för lite bolagsdata",
        "för lite relevant data",
        "allvarlig riskflagga",
        "för låg kvalitet",
        "för svag riskprofil",
        "kvaliteten är inte tillräckligt hög",
        "riskprofilen är inte robust nog",
        "saknar uthållig positiv marginal",
        "tydligt negativ omsättningstrend",
        "för få tydliga tecken på uthållig kvalitet",
    ]
    return any(term in t for term in hard_terms)

def _trigger_from_row(row: pd.Series | dict[str,Any], horizon: str, score: float) -> str:
    threshold=BUY_THRESHOLDS[horizon]
    missing=[]
    if score < threshold:
        missing.append(f"Borsifys betyg behöver stiga från {score:.0f} till minst {threshold:.0f}")

    if horizon=="day":
        vol=_num(row.get("Volymkvot"))
        rsi=_num(row.get("RSI14"))
        m1=_num(row.get("1 mån"))
        if np.isfinite(vol) and vol < .80:
            missing.append("handelsaktiviteten behöver öka till minst ungefär 80 % av normal nivå")
        if np.isfinite(rsi) and rsi < 42:
            missing.append("den kortsiktiga kursstyrkan behöver förbättras")
        elif np.isfinite(rsi) and rsi > 79:
            missing.append("kursen behöver lugna ned sig från en alltför het nivå")
        if np.isfinite(m1) and m1 < -.15:
            missing.append("den senaste månadens tydliga nedgång behöver brytas")
    elif horizon=="medium":
        m1=_num(row.get("1 mån")); m3=_num(row.get("3 mån"))
        quality=_num(row.get("Kvalitet"))
        if np.isfinite(m1) and np.isfinite(m3) and m1 < -.10 and m3 < -.15:
            missing.append("den negativa 1–3-månaderstrenden behöver vända")
        if not ((np.isfinite(m3) and m3>0) or (np.isfinite(quality) and quality>=60)):
            missing.append("antingen tremånadersutvecklingen eller bolagskvaliteten behöver ge tydligare stöd")
    elif horizon=="long":
        invest=_num(row.get("INVEST Score")); quality=_num(row.get("Kvalitet"))
        if np.isfinite(invest) and invest < 65 and np.isfinite(quality) and quality < 65:
            missing.append("den långsiktiga helhetsbedömningen eller bolagskvaliteten behöver stärkas")
    else:
        quality=_num(row.get("Kvalitet")); risk=_num(row.get("Risk")); roe=_num(row.get("ROE")); margin=_num(row.get("Vinstmarginal"))
        durable=sum([
            bool(np.isfinite(quality) and quality>=72),
            bool(np.isfinite(risk) and risk>=68),
            bool(np.isfinite(roe) and roe>=.15),
            bool(np.isfinite(margin) and margin>=.10),
        ])
        if durable < 2:
            missing.append("minst två tydliga tecken på uthållig kvalitet behöver finnas samtidigt")

    return ". ".join(missing[:2]) + ("." if missing else "En mindre förbättring i helhetsbetyget kan räcka för full köpsignal.")

def near_buy_candidates(df: pd.DataFrame, horizon: str, limit: int=3) -> pd.DataFrame:
    """Return candidates close to passing, never hard-risk failures.

    Near-buy is not a softened buy list: candidates must be within 5 score points
    of the real threshold, have no hard data/risk blocker, and not be severely
    overextended.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    score_col={
        "day":"Daytrade Score",
        "medium":"Mellan Score",
        "long":"Lång Score",
        "lifetime":"Livstid Score",
    }[horizon]
    gated=add_market_regime(apply_buy_gate(df,horizon),horizon)
    if score_col not in gated.columns:
        return pd.DataFrame()

    rows=[]
    threshold=BUY_THRESHOLDS[horizon]
    for _,row in gated.iterrows():
        normal_buy=bool(row.get("Köpfilter godkänd"))
        market_ok=bool(row.get("Marknadskrav godkänd",True))
        if normal_buy and market_ok:
            continue
        effective_threshold=_num(row.get("Marknadskrav"))
        if not np.isfinite(effective_threshold):
            effective_threshold=threshold
        score=_num(row.get(score_col))
        if not np.isfinite(score) or score < effective_threshold-5:
            continue
        blockers=[x.strip() for x in str(row.get("Köpfilter stopp","")).split(";") if x.strip()]
        if any(_hard_blocker(x) for x in blockers):
            continue
        ext=assess_overextension(row,horizon)
        if ext["För långt gången"]:
            continue
        data=row.to_dict()
        data.update(ext)
        data["Nära köp"] = True
        if normal_buy and not market_ok:
            req=_num(row.get("Marknadskrav"))
            status=str(row.get("Marknadsläge","") or "").lower()
            data["Vad saknas"] = (
                f"Aktien klarar de vanliga köpkraven, men marknaden är {status}. "
                f"Borsify kräver därför minst {req:.0f} poäng just nu."
            )
        else:
            data["Vad saknas"] = _trigger_from_row(row,horizon,score)
        data["Avstånd till köpgräns"] = max(0.0, effective_threshold-score)
        rows.append(data)

    if not rows:
        return pd.DataFrame()
    out=pd.DataFrame(rows)
    sort_cols=["Avstånd till köpgräns",score_col]
    return out.sort_values(sort_cols,ascending=[True,False]).head(limit).reset_index(drop=True)
