from __future__ import annotations
"""Independent 'deal nose': looks for asymmetric setups without rewarding price-chasing.

Advisory only until prospective evidence shows that it adds edge beyond existing scores.
"""
import math
from typing import Any
import numpy as np
import pandas as pd

def _num(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def assess_exceptional_deal(row:pd.Series|dict[str,Any], horizon:str)->dict[str,Any]:
    val=_num(row.get("Värdering")); qual=_num(row.get("Kvalitet")); risk=_num(row.get("Risk"))
    upside=_num(row.get("Riktkurs potential")); draw=_num(row.get("52v från topp")); fcf=_num(row.get("FCF-yield"))
    entry=str(row.get("Ingångsläge nivå") or "").lower(); company=str(row.get("Bolagsbedömning nivå") or "").lower()
    conviction=_num(row.get("Deal Conviction Score")); confidence=_num(row.get("Analysis Confidence Score"))

    # Pillar 1: price/value. Analyst upside is supporting evidence, never sufficient alone.
    value=0; reasons=[]
    if np.isfinite(val): value += max(0,min(35,(val-50)*.7))
    if np.isfinite(fcf) and fcf>=.04: value += 6; reasons.append("positiv kassaflödesavkastning")
    if np.isfinite(upside) and upside>=.20: value += min(8,upside*16); reasons.append("riktkursgap som stöd, inte bevis")

    # Pillar 2: business quality/survivability. Cheap junk should not qualify.
    quality=0
    if np.isfinite(qual): quality=max(0,min(25,(qual-45)*.5))
    if np.isfinite(risk): quality += max(0,min(7,(risk-55)*.2))
    if company=="red": quality-=18

    # Pillar 3: independent improvement/catalyst evidence already frozen by existing engines.
    catalyst_fields=["Mispriced acceleration nivå","Hidden inflection nivå","Revision breadth nivå",
                     "Margin recovery nivå","Cash conversion inflection nivå","Operating leverage nivå",
                     "Earnings power noise nivå","Negativ överreaktion nivå"]
    active=sum(1 for f in catalyst_fields if _num(row.get(f))>0)
    catalyst=min(24,active*6)
    if active>=2: reasons.append(f"{active} förbättrings-/katalysatorsignaler")

    # Pillar 4: don't arrive after the easy money. This is deliberately asymmetric.
    timing={"green":12,"yellow":7,"orange":-8,"red":-25}.get(entry,0)
    m1=_num(row.get("1 mån")); m3=_num(row.get("3 mån")); rsi=_num(row.get("RSI14")); dist=_num(row.get("Avstånd SMA200"))
    chase=0
    if np.isfinite(m1) and m1>=.25: chase+=8
    if np.isfinite(m3) and m3>=.50: chase+=8
    if np.isfinite(rsi) and rsi>=78: chase+=7
    if np.isfinite(dist) and dist>=.22: chase+=7
    if chase: reasons.append("kursen har redan sprungit och ger chase-avdrag")

    # Conviction/confidence confirm breadth, but are capped to avoid circular domination.
    confirm=0
    if np.isfinite(conviction): confirm+=max(0,min(6,(conviction-55)*.15))
    if np.isfinite(confidence): confirm+=max(0,min(4,(confidence-60)*.10))
    score=float(np.clip(value+quality+catalyst+timing+confirm-chase,0,100))

    hard_block = company=="red" or entry=="red" or (np.isfinite(qual) and qual<40) or (np.isfinite(risk) and risk<35)
    pillars=sum([value>=12,quality>=10,catalyst>=6,timing>0])
    if score>=72 and pillars>=4 and not hard_block:
        label="💎 Exceptionellt affärsläge"; level=3
    elif score>=56 and pillars>=3 and not hard_block:
        label="🟢 Stark fyndkandidat"; level=2
    elif score>=38 and pillars>=2:
        label="🟡 Intressant – kräver mer bevis"; level=1
    else:
        label="— Ingen exceptionell asymmetri"; level=0
    why=(f"Deal Nose {score:.0f}/100 · värde {value:.0f}, kvalitet {quality:.0f}, "
         f"förbättring/katalysator {catalyst:.0f}, timing {timing:.0f}, chase-avdrag {chase:.0f}. ")
    if reasons: why += "; ".join(reasons)+". "
    why += "Signalen är prospektiv och rådgivande; den påverkar ännu inte Borsify-rankingen."
    return {"Deal Nose":label,"Deal Nose Score":score,"Deal Nose nivå":level,"Deal Nose pelare":pillars,"Deal Nose förklaring":why}

def add_exceptional_deal_nose(df:pd.DataFrame,horizon:str)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); extra=pd.DataFrame([assess_exceptional_deal(r,horizon) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra if c in out.columns]
    if overlap:out=out.drop(columns=overlap)
    return out.join(extra)
