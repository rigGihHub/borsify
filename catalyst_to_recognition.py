from __future__ import annotations
"""Assess whether a credible mispricing has a plausible recognition mechanism.

Advisory only. A catalyst must be observed and time-relevant. Generic optimism,
undated headlines or missing catalyst data never create a strong recognition path.
"""
import math
from typing import Any
import numpy as np
import pandas as pd

def _n(v:Any)->float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def _yes(v:Any)->bool:
    if isinstance(v,bool): return v
    return str(v or "").strip().lower() in {"1","true","yes","ja"}

def assess_catalyst_to_recognition(row:pd.Series|dict[str,Any])->dict[str,Any]:
    blind=str(row.get("Market Blind Spot status") or "")
    blind_score=_n(row.get("Market Blind Spot Score"))
    early=str(row.get("Early Mispricing status") or "")
    catalyst_support=_yes(row.get("Catalyst Independent Support")) or _yes(row.get("Catalyst Support"))
    cat_strength=_n(row.get("Catalyst Strength"))
    cat_conf=_n(row.get("Catalyst Confidence"))
    cat_timing=str(row.get("Catalyst Timing") or "—")
    cat_name=str(row.get("Primary Catalyst") or "Ingen verifierad")
    cat_why=str(row.get("Catalyst Why Now") or "")
    why_status=str(row.get("Why Now Status") or "")
    has_independent=_yes(row.get("Why Now Has Independent Catalyst"))
    report_days=_n(row.get("Post-report dagar sedan"))
    revision=_n(row.get("Revision breadth nivå"))
    kpi=_n(row.get("KPI Inflection nivå"))
    conf=_n(row.get("Analysis Confidence Score"))
    m1=_n(row.get("1 mån"))
    relm=_n(row.get("Relativ marknad 3 mån"))
    rels=_n(row.get("Relativ sektor 3 mån"))

    reasons=[]; warnings=[]; mechanisms=set()

    eligible_blind=blind in {"CREDIBLE_BLIND_SPOT","POSSIBLE_BLIND_SPOT","BLIND_SPOT_LOW_CONFIDENCE"}
    eligible_early=early in {"EARLY_MISPRICING","POSSIBLE_EARLY_MISPRICING","EARLY_LOW_CONFIDENCE"}
    eligible=eligible_blind and eligible_early

    # Independent catalyst already verified by catalyst engine.
    if catalyst_support and np.isfinite(cat_strength) and cat_strength>0:
        reasons.append(f"verifierad katalysator: {cat_name} ({cat_timing})")
        mechanisms.add("explicit_catalyst")

    # A near report can reveal improving KPI/estimates, but scheduled timing alone
    # cannot create a strong path unless the business evidence is already improving.
    timing_lower=cat_timing.lower()
    near_report=any(x in timing_lower for x in ["inom en vecka","inom en månad","nästa 1–2 rapporter"])
    if near_report and (kpi>=2 or revision>=2):
        reasons.append("nära rapportfönster kan göra den redan observerade förbättringen synligare")
        mechanisms.add("report_window")

    # Estimate breadth can itself become a recognition channel when it is already
    # broadening but price has not run far.
    if revision>=2:
        reasons.append("bredare estimatrevidering kan sprida förbättringsbilden till fler investerare")
        mechanisms.add("estimate_diffusion")

    # Recent report underreaction can be a path if post-report evidence exists.
    if np.isfinite(report_days) and 0<=report_days<=30 and (kpi>=2 or revision>=2):
        reasons.append("färsk rapport + fortsatt förbättring ger möjlighet till gradvis omvärdering")
        mechanisms.add("post_report_drift")

    # If there is no independently verified mechanism, say so explicitly.
    if not catalyst_support and not has_independent and not mechanisms:
        warnings.append("ingen oberoende omvärderingsmekanism är verifierad")

    # Recognition may already be happening.
    rerating=False
    if np.isfinite(m1) and m1>=.20:
        rerating=True; warnings.append("kursen har redan reagerat kraftigt senaste månaden")
    if np.isfinite(relm) and relm>=.20:
        rerating=True; warnings.append("aktien överpresterar redan marknaden tydligt")
    if np.isfinite(rels) and rels>=.20:
        rerating=True; warnings.append("aktien överpresterar redan sektorn tydligt")

    score=0.0
    if eligible: score+=30
    if eligible_blind and np.isfinite(blind_score): score+=min(15,max(0,(blind_score-50)*.5))
    score+=min(35,len(mechanisms)*14)
    if catalyst_support: score+=10
    if np.isfinite(cat_conf) and cat_conf>=70: score+=5
    if np.isfinite(conf) and conf>=60: score+=5
    if rerating: score-=25
    score=float(np.clip(score,0,100))

    if not eligible:
        label="— Ingen tillräckligt verifierad blind spot att katalysera"; status="NO_BASE"; level=0
    elif not mechanisms:
        label="🟡 Felprissättning utan tydlig recognition-path"; status="NO_RECOGNITION_PATH"; level=1
    elif rerating:
        label="🟠 Recognition kan redan vara igång"; status="RECOGNITION_IN_PROGRESS"; level=1
    elif score>=75 and len(mechanisms)>=2:
        label="💎 Tydlig Catalyst-to-Recognition-path"; status="STRONG_RECOGNITION_PATH"; level=3
    else:
        label="🟢 Möjlig Catalyst-to-Recognition-path"; status="POSSIBLE_RECOGNITION_PATH"; level=2

    if np.isfinite(conf) and conf<45 and level>1:
        label="🟡 Recognition-tes · svagt analysunderlag"; status="LOW_CONFIDENCE_PATH"; level=1

    why=f"Catalyst-to-Recognition {score:.0f}/100 · {len(mechanisms)} verifierad(e) mekanismfamilj(er). "
    if reasons: why+="Stöd: "+"; ".join(reasons[:5])+". "
    if warnings: why+="Motargument: "+"; ".join(warnings[:4])+". "
    why+="Signalen beskriver en möjlig väg till omvärdering, inte en garanti för kursuppgång, och påverkar ännu inte rankingen."

    return {
        "Catalyst-to-Recognition":label,
        "Catalyst-to-Recognition status":status,
        "Catalyst-to-Recognition nivå":level,
        "Catalyst-to-Recognition Score":score,
        "Catalyst-to-Recognition mechanisms":len(mechanisms),
        "Catalyst-to-Recognition reasons":"; ".join(reasons),
        "Catalyst-to-Recognition warnings":"; ".join(warnings),
        "Catalyst-to-Recognition förklaring":why,
    }

def add_catalyst_to_recognition(df:pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_catalyst_to_recognition(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
