from __future__ import annotations
"""Detect potentially mispriced improvement before a large re-rating has already occurred.

Advisory only. Uses point-in-time fields already present on the finalist row and must not
change Borsify ranking until prospective outcome evidence shows incremental edge.
"""
import math
from typing import Any
import numpy as np
import pandas as pd


def _n(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan


def assess_early_mispricing_window(row:pd.Series|dict[str,Any])->dict[str,Any]:
    verdict=str(row.get("Value Trap verdict") or "")
    vt_level=_n(row.get("Value Trap nivå")); kpi=_n(row.get("KPI Inflection nivå")); rev=_n(row.get("Revision breadth nivå"))
    eps=_n(row.get("EPS-estimat förändring")); balance=_n(row.get("EPS-revisionsbalans")); weight=_n(row.get("Estimat tillförlitlighetsvikt"))
    m1=_n(row.get("1 mån")); m3=_n(row.get("3 mån")); relm=_n(row.get("Relativ marknad 3 mån")); rels=_n(row.get("Relativ sektor 3 mån"))
    entry=str(row.get("Ingångsläge nivå") or "").lower(); conf=_n(row.get("Analysis Confidence Score"))

    supports=[]; conflicts=[]
    value_ok=verdict in {"MARKET_WRONG","POSSIBLY_MISPRICED","MISPRICED_LOW_CONFIDENCE"} or (np.isfinite(vt_level) and vt_level>=2)
    if value_ok:supports.append("value-testet pekar mot möjlig felprissättning")
    if np.isfinite(kpi) and kpi>=2:supports.append("verksamhets-KPI förbättras")
    if np.isfinite(rev) and rev>=2:supports.append("bred positiv estimatrevidering")
    if np.isfinite(weight) and weight>=.40 and np.isfinite(eps) and eps>=.02 and np.isfinite(balance) and balance>=.20:
        supports.append("EPS-estimat och revisionsbalans förbättras")

    improvement=sum([np.isfinite(kpi) and kpi>=2,np.isfinite(rev) and rev>=2,
                     np.isfinite(weight) and weight>=.40 and np.isfinite(eps) and eps>=.02 and np.isfinite(balance) and balance>=.20])

    # Price should not already have captured most of the apparent re-rating.
    muted=0
    if np.isfinite(m1) and -.08<=m1<=.12: muted+=1
    if np.isfinite(m3) and -.12<=m3<=.25: muted+=1
    if np.isfinite(relm) and relm<=.12: muted+=1
    if np.isfinite(rels) and rels<=.12: muted+=1
    if muted>=2:supports.append("kurs/relativ reaktion är fortfarande begränsad")

    rerated=False
    if np.isfinite(m1) and m1>=.25: rerated=True; conflicts.append("kursen har redan stigit kraftigt på en månad")
    if np.isfinite(m3) and m3>=.45: rerated=True; conflicts.append("stor del av re-ratingsfasen kan redan ha skett")
    if np.isfinite(relm) and relm>=.25: rerated=True; conflicts.append("aktien har redan kraftigt överpresterat marknaden")
    if np.isfinite(rels) and rels>=.25: rerated=True; conflicts.append("aktien har redan kraftigt överpresterat sektorn")
    if entry in {"orange","red"}: conflicts.append("ingångsläget är inte attraktivt")
    if verdict in {"VALUE_TRAP","TRAP_RISK"}: conflicts.append("value-testet varnar för fundamentalt motiverad rabatt")

    # Require both value support and a fresh independent improvement family.
    score=0
    if value_ok: score+=30
    score+=min(30,improvement*15)
    score+=min(20,muted*5)
    if np.isfinite(conf) and conf>=60: score+=10
    if entry=="green": score+=10
    if rerated: score-=30
    if verdict in {"VALUE_TRAP","TRAP_RISK"}: score-=35
    score=float(np.clip(score,0,100))

    hard_block=(not value_ok) or improvement<1 or verdict in {"VALUE_TRAP","TRAP_RISK"} or entry=="red"
    if score>=75 and improvement>=2 and muted>=2 and not hard_block and not rerated:
        label="💎 Tidig felprissättning · före re-rating"; level=3; status="EARLY_MISPRICING"
    elif score>=58 and improvement>=1 and muted>=2 and not hard_block and not rerated:
        label="🟢 Möjlig tidig felprissättning"; level=2; status="POSSIBLE_EARLY_MISPRICING"
    elif value_ok and rerated:
        label="🟠 Bra tes · marknaden kan redan ha hunnit ikapp"; level=0; status="RERATING_ADVANCED"
    elif value_ok and improvement>=1:
        label="🟡 Förbättring syns · prisreaktionen är oklar"; level=1; status="IMPROVEMENT_UNCLEAR_REACTION"
    else:
        label="— Ingen verifierad tidig felprissättning"; level=0; status="NO_EARLY_WINDOW"
    if np.isfinite(conf) and conf<45 and level>1:
        label="🟡 Tidig tes · svagt analysunderlag"; level=1; status="EARLY_LOW_CONFIDENCE"

    why=f"Early Mispricing {score:.0f}/100 · förbättringsfamiljer {improvement}, begränsade prisreaktioner {muted}/4. "
    if supports: why+="Stöd: "+"; ".join(supports[:5])+". "
    if conflicts: why+="Motargument: "+"; ".join(conflicts[:4])+". "
    why+="Signalen är prospektiv och rådgivande och påverkar ännu inte rankingen."
    return {"Early Mispricing":label,"Early Mispricing status":status,"Early Mispricing nivå":level,
            "Early Mispricing Score":score,"Early Mispricing improvement families":improvement,
            "Early Mispricing muted reactions":muted,"Early Mispricing stöd":"; ".join(supports),
            "Early Mispricing motargument":"; ".join(conflicts),"Early Mispricing förklaring":why}


def add_early_mispricing_window(df:pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); extra=pd.DataFrame([assess_early_mispricing_window(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra if c in out.columns]
    if overlap:out=out.drop(columns=overlap)
    return out.join(extra)
