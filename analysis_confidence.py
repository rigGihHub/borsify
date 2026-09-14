from __future__ import annotations
"""Separate confidence-in-analysis from attractiveness-of-investment.

The score reflects how complete, healthy and independently evidenced the analysis is.
It must not alter Borsify's investment score or Deal Conviction unless future
prospective evidence justifies doing so.
"""
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

def _bool(v: Any) -> bool:
    if isinstance(v,bool): return v
    return str(v or "").strip().lower() in {"1","true","yes","ja","öppen","open"}

def assess_analysis_confidence(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    coverage=_num(row.get("Datatäckning"))
    failure_penalty=_num(row.get("Data Failure penalty"))
    kpi_count=_num(row.get("KPI strukturerad täckning"))
    deep_conf=_num(row.get("Deep Confidence"))
    evidence_count=_num(row.get("Case Evidence Count"))
    deal_families=_num(row.get("Deal Conviction oberoende familjer"))

    fundamental_status=str(row.get("Fundamental source status") or "").upper()
    deep_status=str(row.get("Deep source status") or "").upper()
    fundamental_circuit=_bool(row.get("Fundamental circuit open"))
    deep_circuit=_bool(row.get("Deep source circuit open"))
    kpi_gaps=str(row.get("Business KPI gaps") or row.get("KPI-specifika saknas") or "").strip()

    components={}
    # 40 pts: broad core-field coverage.
    components["Datatäckning"]=40.0*(min(max(coverage,0),1) if np.isfinite(coverage) else 0.0)

    # 20 pts: source health. Missing explicit telemetry is neutral-ish, not perfect.
    source=20.0
    for status in [fundamental_status,deep_status]:
        if status in {"ERROR","DEGRADED","CIRCUIT_OPEN"}: source-=8.0
        elif status in {"PARTIAL","NO_DATA"}: source-=4.0
        elif not status: source-=1.5
    if fundamental_circuit: source-=5.0
    if deep_circuit: source-=5.0
    components["Källhälsa"]=max(0.0,source)

    # 15 pts: sector/business-specific observability. Generic financials alone
    # are not enough to claim full business understanding.
    if np.isfinite(kpi_count):
        components["Bransch-KPI"]=min(15.0,max(0.0,kpi_count)*5.0)
    else:
        components["Bransch-KPI"]=0.0
    if kpi_gaps:
        components["Bransch-KPI"]=max(0.0,components["Bransch-KPI"]-3.0)

    # 15 pts: depth of fundamental verification.
    if np.isfinite(deep_conf):
        norm=deep_conf/100.0 if deep_conf>1 else deep_conf
        components["Djupverifiering"]=15.0*min(max(norm,0),1)
    else:
        components["Djupverifiering"]=0.0

    # 10 pts: independent evidence breadth. This is not investment conviction;
    # it only says how many distinct evidence families actually exist.
    breadth=0.0
    if np.isfinite(deal_families):
        breadth=max(breadth,min(10.0,deal_families*2.5))
    if np.isfinite(evidence_count):
        breadth=max(breadth,min(10.0,evidence_count*1.5))
    components["Evidensbredd"]=breadth

    raw=sum(components.values())
    if np.isfinite(failure_penalty):
        raw-=min(max(failure_penalty,0),60)*0.35

    score=float(np.clip(raw,0,100))
    blockers=[]
    warnings=[]
    if fundamental_circuit or deep_circuit: blockers.append("öppen circuit breaker")
    if fundamental_status=="ERROR": blockers.append("fundamental källa fel")
    if deep_status in {"ERROR","DEGRADED"}: blockers.append("djupkälla fel/försämrad")
    if np.isfinite(coverage) and coverage<.50: warnings.append("låg kärndatatäckning")
    if kpi_gaps: warnings.append("viktiga bransch-KPI:er saknas")
    if not np.isfinite(deep_conf) or deep_conf<=0: warnings.append("begränsad djupverifiering")

    if blockers or score<35:
        label="🔴 Lågt analysförtroende"
        level=1
    elif score<60:
        label="🟡 Begränsat analysförtroende"
        level=2
    elif score<80:
        label="🟢 Gott analysförtroende"
        level=3
    else:
        label="💎 Mycket högt analysförtroende"
        level=4

    why=(
        f"Datatäckning {components['Datatäckning']:.0f}/40 · "
        f"källhälsa {components['Källhälsa']:.0f}/20 · "
        f"bransch-KPI {components['Bransch-KPI']:.0f}/15 · "
        f"djupverifiering {components['Djupverifiering']:.0f}/15 · "
        f"evidensbredd {components['Evidensbredd']:.0f}/10."
    )
    if blockers: why+=" Blockerare: "+"; ".join(dict.fromkeys(blockers))+"."
    if warnings: why+=" Begränsningar: "+"; ".join(dict.fromkeys(warnings))+"."
    why+=" Detta mäter tillförlitligheten i analysunderlaget, inte hur attraktiv aktien är."

    return {
        "Analysis Confidence":label,
        "Analysis Confidence Score":score,
        "Analysis Confidence nivå":level,
        "Analysis Confidence blockerare":"; ".join(dict.fromkeys(blockers)),
        "Analysis Confidence varningar":"; ".join(dict.fromkeys(warnings)),
        "Analysis Confidence förklaring":why,
        "Analysis Confidence datatäckning":components["Datatäckning"],
        "Analysis Confidence källhälsa":components["Källhälsa"],
        "Analysis Confidence bransch-KPI":components["Bransch-KPI"],
        "Analysis Confidence djup":components["Djupverifiering"],
        "Analysis Confidence evidens":components["Evidensbredd"],
    }

def add_analysis_confidence(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_analysis_confidence(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
