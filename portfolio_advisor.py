from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

def _num(v: Any) -> float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception: return np.nan

def assess_holding(purchase_price: Any, current: dict[str,Any]|pd.Series) -> dict[str,Any]:
    buy=_num(purchase_price); now=_num(current.get("Pris"))
    ret=now/buy-1 if np.isfinite(now) and np.isfinite(buy) and buy>0 else np.nan
    score=_num(current.get("Borsify Score"))
    quality=_num(current.get("Kvalitet")); risk=_num(current.get("Risk"))
    m3=_num(current.get("3 mån")); dist=_num(current.get("Avstånd SMA200"))
    reasons=[]
    if np.isfinite(score) and score<45: reasons.append("Borsify Score är svag")
    if np.isfinite(quality) and quality<40: reasons.append("kvalitetsbilden är svag")
    if np.isfinite(risk) and risk<40: reasons.append("riskbilden har försämrats")
    if np.isfinite(m3) and m3<-.20 and np.isfinite(dist) and dist<-.10: reasons.append("tydligt negativ trend")
    negatives=len(reasons)
    if negatives>=2:
        status="OMPRÖVA"
        advice="Stark säljsignal / ompröva innehavet"
    elif negatives==1:
        status="BEVAKA"
        advice="Bevaka noga – ett viktigt motbevis finns"
    elif np.isfinite(ret) and ret>0.35 and np.isfinite(score) and score<60:
        status="VINSTSÄKRA?"
        advice="Stor uppgång men modellstödet är inte längre starkt – överväg riskreducering"
    else:
        status="BEHÅLL"
        advice="Ingen tydlig säljsignal i nuvarande Borsify-data"
    return {"Status":status,"Borsify råd":advice,"Utveckling":ret,"Skäl":"; ".join(reasons) if reasons else "inga tydliga modellbaserade säljsignaler"}
