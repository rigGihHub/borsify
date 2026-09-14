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

def _yes(v: Any) -> bool:
    if isinstance(v,bool): return v
    return str(v or "").strip().lower() in {"1","true","ja","yes"}

def assess_hidden_inflection(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    r=row
    new_pos=_num(r.get("Fresh Change New Positives")); new_neg=_num(r.get("Fresh Change New Negatives"))
    pos_count=_num(r.get("Fresh Change Positive Count")); neg_count=_num(r.get("Fresh Change Negative Count"))
    report_pos=_num(r.get("Report Delta positiva")); report_neg=_num(r.get("Report Delta negativa"))
    eps=_num(r.get("EPS-estimat förändring")); rev_bal=_num(r.get("EPS-revisionsbalans"))
    analysts=_num(r.get("Analytiker antal")); bullish=_num(r.get("Konsensus bullish andel"))
    m1=_num(r.get("1 mån")); m3=_num(r.get("3 mån")); dist=_num(r.get("Avstånd SMA200"))
    valuation=_num(r.get("Värdering")); quality=_num(r.get("Kvalitet"))
    crowded=_yes(r.get("Crowded varning")) or _yes(r.get("Crowded stark varning"))
    early=[]; warnings=[]
    if np.isfinite(new_pos) and new_pos >= 1 and (not np.isfinite(new_neg) or new_neg == 0): early.append("nya positiva förändringspunkter utan nya negativa")
    if np.isfinite(pos_count) and 1 <= pos_count <= 2 and (not np.isfinite(neg_count) or neg_count == 0): early.append("förbättringen är ännu smal och tidig")
    if np.isfinite(report_pos) and 1 <= report_pos <= 2 and (not np.isfinite(report_neg) or report_neg == 0): early.append("rapportförändringen har börjat luta positivt")
    if np.isfinite(eps) and .005 <= eps < .03: early.append("estimaten börjar skruvas upp")
    if np.isfinite(rev_bal) and .10 <= rev_bal < .35: early.append("revisionsbalansen har börjat förbättras")
    if np.isfinite(m1) and m1 > .15: warnings.append("kursen har redan börjat springa")
    if np.isfinite(m3) and m3 > .25: warnings.append("tremånaderskursen har redan rört sig tydligt")
    if np.isfinite(dist) and dist > .15: warnings.append("kursen ligger redan långt över lång trend")
    if crowded: warnings.append("förväntningsbilden är redan trång")
    if np.isfinite(bullish) and bullish >= .75 and np.isfinite(analysts) and analysts >= 6: warnings.append("bred konsensus är redan tydligt positiv")
    if np.isfinite(valuation) and valuation < 45: warnings.append("värderingen är ansträngd")
    if np.isfinite(quality) and quality < 55: warnings.append("bolagskvaliteten är för svag")
    too_late=any(x in warnings for x in ["kursen har redan börjat springa","tremånaderskursen har redan rört sig tydligt","förväntningsbilden är redan trång","bred konsensus är redan tydligt positiv"])
    bad=(np.isfinite(neg_count) and neg_count >= 2) or (np.isfinite(report_neg) and report_neg >= 2) or (np.isfinite(quality) and quality < 55)
    n=len(early)
    if bad:
        tier=-1; label="⚠️ Ingen dold vändning – negativa signaler dominerar"
    elif n < 2:
        tier=0; label="— För lite tidig förbättring"
    elif too_late:
        tier=1; label="🟡 Tidig förbättring finns – men marknaden har börjat hinna med"
    elif n >= 3:
        tier=3; label="💎 Hidden inflection · mycket tidig fyndkandidat"
    else:
        tier=2; label="🟢 Hidden inflection · tidig förbättring före konsensus"
    rank=float(max(tier,0)*100 + min(n,5)*7 - min(len(warnings),4)*6)
    if tier < 0: rank=-100.0
    why="; ".join(early[:4]) if early else "ingen verifierad tidig förbättring"
    if warnings: why += ". Motargument: " + "; ".join(warnings[:3])
    return {"Hidden inflection":label,"Hidden inflection nivå":tier,"Hidden inflection rangvärde":rank,"Hidden inflection stöd":"; ".join(early[:5]),"Hidden inflection varningar":"; ".join(warnings[:5]),"Hidden inflection förklaring":why}

def add_hidden_inflection(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); extra=pd.DataFrame([assess_hidden_inflection(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
