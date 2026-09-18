from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

def _num(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def _label(row): return str(row.get("Namn") or row.get("Ticker") or "aktien")
def _entry_rank(v): return {"green":4,"yellow":3,"orange":2,"red":1}.get(str(v or "").lower(),0)
def _company_rank(v): return {"green":3,"yellow":2,"red":1}.get(str(v or "").lower(),0)

def _pair_edges(winner,other,score_col):
    wins=[]; losses=[]
    ws,os=_num(winner.get(score_col)),_num(other.get(score_col))
    if np.isfinite(ws) and np.isfinite(os) and abs(ws-os)>=.5:
        (wins if ws>os else losses).append("har ett bättre samlat betyg")
    wc,oc=_num(winner.get("Deal Conviction Score")),_num(other.get("Deal Conviction Score"))
    if np.isfinite(wc) and np.isfinite(oc) and abs(wc-oc)>=3:
        (wins if wc>oc else losses).append("har fler tydliga saker som talar för aktien")
    wr,or_=_num(winner.get("Case Readiness")),_num(other.get("Case Readiness"))
    if np.isfinite(wr) and np.isfinite(or_) and abs(wr-or_)>=3:
        (wins if wr>or_ else losses).append("Borsify har bättre information om aktien")
    we,oe=_entry_rank(winner.get("Ingångsläge nivå")),_entry_rank(other.get("Ingångsläge nivå"))
    if we and oe and we!=oe:(wins if we>oe else losses).append("priset ser bättre ut att köpa till just nu")
    wb,ob=_company_rank(winner.get("Bolagsbedömning nivå")),_company_rank(other.get("Bolagsbedömning nivå"))
    if wb and ob and wb!=ob:(wins if wb>ob else losses).append("bolaget ser starkare ut")
    return wins,losses

def explain_top_pick(ranked:pd.DataFrame,score_col:str,horizon:str)->dict[str,Any]:
    if ranked is None or ranked.empty:
        return {"Varför #1":"Borsify hittade ingen aktie som klarade alla krav.","Förstavalets fördelar":"","Utmanarnas fördelar":"","Jämförelseunderlag":pd.DataFrame()}
    top=ranked.head(3).copy()
    # The visible comparison must use the same specialist-aware score as the ranking.
    score_col = "Borsify slutbetyg" if "Borsify slutbetyg" in top.columns else score_col
    # Do not say a lower-ranked challenger has a better overall score. If the
    # specialist-aware score is equal/close, explain only genuine component edges.
    winner=top.iloc[0]; comparisons=[]; challenger=[]
    for pos in range(1,len(top)):
        other=top.iloc[pos]; wins,losses=_pair_edges(winner,other,score_col); label=_label(other)
        if wins: comparisons.append(f"Jämfört med {label} " + " och ".join(wins[:2]))
        if losses: challenger.append(f"{label} " + " och ".join(losses[:2]))
    name=_label(winner)
    headline=(f"Borsify väljer {name} först. " + ". ".join(comparisons) + ".") if comparisons else f"Borsify väljer {name} först eftersom aktien klarar kraven och ingen annan godkänd aktie tydligt är bättre i jämförelsen."
    if challenger: headline += " Den är ändå inte bäst på allt."
    cols=[c for c in ["Ticker","Namn",score_col,"Ingångsläge","Bolagsbedömning"] if c in top.columns]
    view=top[cols].copy(); view.insert(0,"#",range(1,len(view)+1))
    return {"Varför #1":headline,"Förstavalets fördelar":". ".join(comparisons),"Utmanarnas fördelar":". ".join(challenger) if challenger else "Ingen annan godkänd aktie har en tydlig fördel i den här jämförelsen.","Jämförelseunderlag":view}
