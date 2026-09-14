from __future__ import annotations
"""Explain why a prospective mispricing may still exist.

Advisory only. A blind spot is not positive evidence by itself; it must sit on top of an
already verified Early Mispricing/value case. Missing attention data never counts as low attention.
"""
import math
from typing import Any
import numpy as np
import pandas as pd


def _n(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan


def assess_market_blind_spot(row:pd.Series|dict[str,Any])->dict[str,Any]:
    early=str(row.get("Early Mispricing status") or "")
    early_score=_n(row.get("Early Mispricing Score")); conf=_n(row.get("Analysis Confidence Score"))
    analysts=_n(row.get("Analytiker antal")); under=_n(row.get("Underfollowed Quality nivå"))
    earnings=_n(row.get("Earnings power noise nivå")); hidden=_n(row.get("Hidden inflection nivå"))
    kpi=_n(row.get("KPI Inflection nivå")); revisions=_n(row.get("Revision breadth nivå"))
    report_pos=_n(row.get("Report Delta positiva")); report_neg=_n(row.get("Report Delta negativa"))
    m1=_n(row.get("1 mån")); relm=_n(row.get("Relativ marknad 3 mån")); rels=_n(row.get("Relativ sektor 3 mån"))

    reasons=[]; counter=[]; families=set()
    eligible=early in {"EARLY_MISPRICING","POSSIBLE_EARLY_MISPRICING","EARLY_LOW_CONFIDENCE"}

    # Attention blind spot: only observed low coverage qualifies. Missing coverage never does.
    if np.isfinite(analysts) and analysts<=3 and under>=1:
        reasons.append(f"låg verifierad analytikertäckning ({int(analysts)} analytiker) samtidigt som kvalitetskraven klaras")
        families.add("attention")
    elif not np.isfinite(analysts):
        counter.append("analytikertäckning saknas och räknas inte som låg bevakning")

    # Headline/accounting noise must already have passed the dedicated conservative engine.
    if earnings>=2:
        reasons.append("rubrikresultatet ser svagare ut än den verifierade underliggande intjäningsbilden")
        families.add("headline_noise")
    if hidden>=2:
        reasons.append("förbättringen syns i ledande data innan den är fullt synlig i rubriksiffrorna")
        families.add("lead_lag")
    elif kpi>=2 and revisions<2:
        reasons.append("verksamhets-KPI förbättras före en bred analytikerrevidering")
        families.add("lead_lag")
    if np.isfinite(report_neg) and np.isfinite(report_pos) and report_neg>report_pos and (kpi>=2 or revisions>=2):
        reasons.append("negativa rapportpunkter kan fortfarande överskugga en förbättrad framåtblickande bild")
        families.add("mixed_report")

    # If price/relative price has already moved strongly, the alleged blind spot is less credible.
    noticed=False
    if np.isfinite(m1) and m1>=.20: noticed=True; counter.append("kursen har redan reagerat kraftigt på kort sikt")
    if np.isfinite(relm) and relm>=.20: noticed=True; counter.append("aktien har redan tydligt överpresterat marknaden")
    if np.isfinite(rels) and rels>=.20: noticed=True; counter.append("aktien har redan tydligt överpresterat sektorn")

    score=0.0
    if eligible: score+=30
    score+=min(45,len(families)*18)
    if np.isfinite(early_score): score+=min(15,max(0,(early_score-50)*.5))
    if np.isfinite(conf) and conf>=60: score+=10
    if noticed: score-=30
    score=float(np.clip(score,0,100))

    if not eligible:
        label="— Ingen verifierad felprissättning att förklara"; status="NO_MISPRICING_BASE"; level=0
    elif not families:
        label="🟡 Felprissättning möjlig · men blind spot saknar förklaring"; status="UNEXPLAINED_MISPRICING"; level=1
    elif noticed:
        label="🟠 Blind spot kan vara på väg att stängas"; status="BLIND_SPOT_CLOSING"; level=1
    elif score>=75 and len(families)>=2:
        label="💎 Trovärdig market blind spot"; status="CREDIBLE_BLIND_SPOT"; level=3
    else:
        label="🟢 Möjlig market blind spot"; status="POSSIBLE_BLIND_SPOT"; level=2
    if np.isfinite(conf) and conf<45 and level>1:
        label="🟡 Blind-spot-tes · svagt analysunderlag"; status="BLIND_SPOT_LOW_CONFIDENCE"; level=1

    why=f"Market Blind Spot {score:.0f}/100 · {len(families)} oberoende förklaringsfamilj(er). "
    if reasons: why+="Möjlig förklaring: "+"; ".join(reasons[:5])+". "
    if counter: why+="Motargument: "+"; ".join(counter[:4])+". "
    why+="En blind spot är aldrig positiv evidens i sig och påverkar ännu inte rankingen."
    return {"Market Blind Spot":label,"Market Blind Spot status":status,"Market Blind Spot nivå":level,
            "Market Blind Spot Score":score,"Market Blind Spot families":len(families),
            "Market Blind Spot reasons":"; ".join(reasons),"Market Blind Spot counter":"; ".join(counter),
            "Market Blind Spot förklaring":why}


def add_market_blind_spot(df:pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); extra=pd.DataFrame([assess_market_blind_spot(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra if c in out.columns]
    if overlap:out=out.drop(columns=overlap)
    return out.join(extra)
