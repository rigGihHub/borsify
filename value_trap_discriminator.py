from __future__ import annotations
"""Distinguish a likely value trap from a potentially mispriced good business.

Advisory only. The discriminator uses already-observed/frozen evidence and must not
change ranking until prospective validation shows incremental edge.
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


def assess_value_trap_vs_market_wrong(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    valuation=_num(row.get("Värdering"))
    quality=_num(row.get("Kvalitet"))
    risk=_num(row.get("Risk"))
    fcf=_num(row.get("FCF-yield"))
    rev_growth=_num(row.get("Omsättningstillväxt"))
    earn_growth=_num(row.get("Vinsttillväxt"))
    margin=_num(row.get("Vinstmarginal"))
    debt=_num(row.get("Skuld/eget kapital"))
    draw=_num(row.get("52v från topp"))
    confidence=_num(row.get("Analysis Confidence Score"))
    company=str(row.get("Bolagsbedömning nivå") or "").lower()
    entry=str(row.get("Ingångsläge nivå") or "").lower()

    support=[]
    trap=[]

    # Reasons the market may be too pessimistic.
    if np.isfinite(quality) and quality>=70: support.append("hög bolagskvalitet")
    if np.isfinite(fcf) and fcf>=.04: support.append("positiv FCF-yield")
    if np.isfinite(rev_growth) and rev_growth>0: support.append("omsättningen växer")
    if np.isfinite(earn_growth) and earn_growth>0: support.append("vinsten växer")
    if np.isfinite(margin) and margin>=.08: support.append("lönsam verksamhet")
    if _num(row.get("Revision breadth nivå"))>=2: support.append("bred positiv estimatrevidering")
    if _num(row.get("KPI Inflection nivå"))>=2: support.append("verksamhets-KPI förbättras")
    if _num(row.get("Management execution nivå"))>=2: support.append("stark observerad management execution")
    if _num(row.get("Mispriced acceleration nivå"))>=2: support.append("mispriced acceleration")
    if _num(row.get("Negativ överreaktion nivå"))>=2: support.append("möjlig negativ överreaktion")
    if _num(row.get("Balance-sheet optionality nivå"))>=2: support.append("balansräkningsoptionality")

    # Reasons cheapness may be justified.
    if np.isfinite(quality) and quality<45: trap.append("låg bolagskvalitet")
    if np.isfinite(risk) and risk<40: trap.append("svag riskprofil")
    if company=="red": trap.append("röd bolagsbedömning")
    if np.isfinite(fcf) and fcf<0: trap.append("negativt fritt kassaflöde")
    if np.isfinite(rev_growth) and rev_growth<=-.08: trap.append("kraftigt fallande omsättning")
    if np.isfinite(earn_growth) and earn_growth<=-.15: trap.append("kraftigt fallande vinst")
    if np.isfinite(margin) and margin<0: trap.append("förlustverksamhet")
    if np.isfinite(debt) and debt>250: trap.append("hög skuldsättning")
    if _num(row.get("Management execution nivå"))<0: trap.append("management execution ger varningar")
    if _num(row.get("KPI Inflection nivå"))<0: trap.append("KPI-bilden försämras")
    if _num(row.get("Revision breadth nivå"))<0: trap.append("negativa estimatrevideringar")

    # Cheapness must actually exist before claiming market mispricing/value trap.
    cheap = (np.isfinite(valuation) and valuation>=65) or (np.isfinite(fcf) and fcf>=.05) or (np.isfinite(draw) and draw<=-.20)
    support_score=min(100, len(support)*12 + (8 if cheap else 0))
    trap_score=min(100, len(trap)*16 + (10 if company=="red" else 0))

    if not cheap:
        label="— Inte ett tydligt value-case"
        verdict="NO_VALUE_CASE"
        level=0
    elif trap_score>=48 and trap_score>=support_score+12:
        label="🔴 Trolig value trap"
        verdict="VALUE_TRAP"
        level=-2
    elif trap_score>=28 and support_score<trap_score+15:
        label="🟠 Billig av en anledning?"
        verdict="TRAP_RISK"
        level=-1
    elif support_score>=60 and trap_score<=24:
        label="💎 Marknaden kan ha fel"
        verdict="MARKET_WRONG"
        level=3
    elif support_score>=36 and support_score>trap_score:
        label="🟢 Möjligen felprissatt"
        verdict="POSSIBLY_MISPRICED"
        level=2
    else:
        label="🟡 Oklart varför den är billig"
        verdict="UNCLEAR"
        level=1

    if np.isfinite(confidence) and confidence<45 and level>1:
        label="🟡 Lovande value-case · svag data"
        verdict="MISPRICED_LOW_CONFIDENCE"
        level=1

    why=(f"Value Trap-test · stöd {support_score:.0f}/100, trap-risk {trap_score:.0f}/100. ")
    if support: why += "Stöd: "+"; ".join(support[:6])+". "
    if trap: why += "Varningsflaggor: "+"; ".join(trap[:6])+". "
    if entry=="red": why += "Köpläget är fortfarande rött även om värderingen är låg. "
    why += "Bedömningen är rådgivande och påverkar ännu inte Borsifys ranking."

    return {
        "Value Trap Test":label,
        "Value Trap verdict":verdict,
        "Value Trap nivå":level,
        "Value Trap support score":float(support_score),
        "Value Trap risk score":float(trap_score),
        "Value Trap stöd":"; ".join(support),
        "Value Trap varningar":"; ".join(trap),
        "Value Trap förklaring":why,
    }


def add_value_trap_test(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_value_trap_vs_market_wrong(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
