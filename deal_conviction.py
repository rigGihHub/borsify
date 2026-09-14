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

FAMILIES = {
    "operativ förbättring": (
        "Mispriced acceleration nivå", "Margin recovery nivå",
        "Cash conversion inflection nivå", "Operating leverage nivå",
        "Earnings power noise nivå",
    ),
    "tidig upptäckt/förväntningar": (
        "Hidden inflection nivå", "Revision breadth nivå", "Underfollowed Quality nivå",
    ),
    "värdering/asymmetri": ("Affärsläge nivå", "Negativ överreaktion nivå"),
    "uthållighet/optionality": ("Ignored compounder nivå", "Balance-sheet optionality nivå"),
}

def _family_state(row, fields):
    vals=[]
    for f in fields:
        x=_num(row.get(f))
        if np.isfinite(x): vals.append((f,int(x)))
    positives=[(f,v) for f,v in vals if v>0]
    return {
        "best": max((v for _,v in positives), default=0),
        "negative": any(v<0 for _,v in vals),
        "support_count": sum(v>0 for _,v in vals),
    }

def assess_deal_conviction(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,Any]:
    states={name:_family_state(row,fields) for name,fields in FAMILIES.items()}
    active=list(FAMILIES)
    if horizon in {"day","medium"}:
        active=[x for x in active if x != "uthållighet/optionality"]

    family_scores={}; supporting=[]; negative_families=[]
    for name in active:
        st=states[name]
        base={0:0,1:10,2:18,3:25}.get(st["best"],25 if st["best"]>3 else 0)
        confirm=min(max(st["support_count"]-1,0)*2,4)
        family_scores[name]=base+confirm
        if st["best"]>0: supporting.append(name)
        if st["negative"]: negative_families.append(name)

    raw=sum(family_scores.values())
    cross_bonus=(8 if len(supporting)>=2 else 0)+(7 if len(supporting)>=3 else 0)+(5 if len(supporting)>=4 else 0)
    entry=str(row.get("Ingångsläge nivå") or "").lower()
    company=str(row.get("Bolagsbedömning nivå") or "").lower()
    penalties=12*len(negative_families)
    if entry=="red": penalties+=20
    elif entry=="orange": penalties+=8
    if company=="red": penalties+=20
    elif company=="yellow": penalties+=5
    score=float(np.clip(raw+cross_bonus-penalties,0,100))
    independent=len(supporting)

    if len(negative_families)>=2 or company=="red":
        label="⚠️ Låg conviction · motstridiga fyndsignaler"; level=-1
    elif score>=72 and independent>=3 and entry!="red":
        label="💎 Exceptionell affärskonfluens"; level=3
    elif score>=52 and independent>=2:
        label="🟢 Hög Deal Conviction"; level=2
    elif score>=28 and independent>=1:
        label="🟡 Viss affärskonfluens"; level=1
    else:
        label="— Ingen stark affärskonfluens"; level=0

    fam_text=", ".join(f"{k} {family_scores[k]:.0f}" for k in active if family_scores[k]>0) or "inga"
    why=(f"{independent} oberoende evidensfamiljer stöder caset. Familjepoäng: {fam_text}. "
         "Närbesläktade signaler inom samma familj dubbelräknas inte.")
    if negative_families:
        why += " Motstridiga familjer: " + ", ".join(negative_families) + "."
    return {
        "Deal Conviction":label, "Deal Conviction nivå":level, "Deal Conviction Score":score,
        "Deal Conviction oberoende familjer":independent,
        "Deal Conviction familjer":", ".join(supporting),
        "Deal Conviction negativa familjer":", ".join(negative_families),
        "Deal Conviction förklaring":why,
    }

def add_deal_conviction(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_deal_conviction(r,horizon) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
