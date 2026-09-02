from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

BUY_THRESHOLDS = {
    "day": 66.0,
    "medium": 64.0,
    "long": 63.0,
    "lifetime": 66.0,
}

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def _has_severe_risk(row: pd.Series | dict[str,Any]) -> bool:
    flags=str(row.get("Riskflaggor","") or "").lower()
    severe=[
        "negativ roe","negativ marginal","hög skuldsättning",
        "fallande lång trend",
    ]
    return any(x in flags for x in severe)

def assess_buy_gate(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,Any]:
    score_col={
        "day":"Daytrade Score",
        "medium":"Mellan Score",
        "long":"Lång Score",
        "lifetime":"Livstid Score",
    }[horizon]
    score=_num(row.get(score_col))
    threshold=BUY_THRESHOLDS[horizon]
    blockers=[]
    supports=[]

    qc=str(row.get("Universe QC","") or "")
    if qc=="EXKLUDERA":
        blockers.append("otillräcklig marknadsdatakvalitet")
    elif qc=="VERIFIERAD":
        supports.append("verifierad datakvalitet")

    coverage=_num(row.get("Datatäckning"))
    if np.isfinite(coverage) and coverage < .40:
        blockers.append("för låg fundamental datatäckning")

    if not np.isfinite(score) or score < threshold:
        blockers.append(f"horisontscore under köpgränsen {threshold:.0f}")

    risk=_num(row.get("Risk"))
    quality=_num(row.get("Kvalitet"))
    valuation=_num(row.get("Värdering"))

    if horizon=="day":
        vol=_num(row.get("Volymkvot"))
        rsi=_num(row.get("RSI14"))
        m1=_num(row.get("1 mån"))
        daily=_num(row.get("Dagsförändring"))
        if np.isfinite(vol) and vol < .80:
            blockers.append("för svag handelsaktivitet")
        if np.isfinite(rsi) and (rsi < 42 or rsi > 79):
            blockers.append("RSI utanför köpzon")
        if np.isfinite(m1) and m1 < -.15:
            blockers.append("för svag 1-månaderstrend")
        if np.isfinite(daily) and daily < -.06:
            blockers.append("för kraftigt negativ dagsrörelse")
        if np.isfinite(vol) and vol >= 1.2: supports.append("stark handelsaktivitet")
        if np.isfinite(rsi) and 50 <= rsi <= 72: supports.append("balanserad kortsiktig styrka")

    elif horizon=="medium":
        m1=_num(row.get("1 mån"))
        m3=_num(row.get("3 mån"))
        if np.isfinite(m1) and np.isfinite(m3) and m1 < -.10 and m3 < -.15:
            blockers.append("negativ trend på både 1 och 3 månader")
        if np.isfinite(risk) and risk < 38:
            blockers.append("för svag riskprofil")
        if np.isfinite(quality) and quality < 38:
            blockers.append("för låg kvalitet")
        if np.isfinite(m3) and m3 > 0: supports.append("positiv 3-månaderstrend")
        if np.isfinite(quality) and quality >= 60: supports.append("god kvalitet")

    elif horizon=="long":
        invest=_num(row.get("INVEST Score"))
        if np.isfinite(invest) and invest < 58:
            blockers.append("INVEST-score för låg")
        if np.isfinite(quality) and quality < 48:
            blockers.append("för låg kvalitet för flerårsägande")
        if np.isfinite(risk) and risk < 42:
            blockers.append("för svag riskprofil för flerårsägande")
        if _has_severe_risk(row):
            blockers.append("allvarlig riskflagga")
        if np.isfinite(invest) and invest >= 65: supports.append("stark INVEST-bedömning")
        if np.isfinite(valuation) and valuation >= 60: supports.append("attraktiv relativ värdering")

    else:  # lifetime
        roe=_num(row.get("ROE"))
        margin=_num(row.get("Vinstmarginal"))
        growth=_num(row.get("Omsättningstillväxt"))
        if np.isfinite(quality) and quality < 62:
            blockers.append("kvaliteten är inte tillräckligt hög")
        if np.isfinite(risk) and risk < 58:
            blockers.append("riskprofilen är inte robust nog")
        if np.isfinite(roe) and roe < .10:
            blockers.append("för låg avkastning på eget kapital")
        if np.isfinite(margin) and margin <= 0:
            blockers.append("saknar uthållig positiv marginal")
        if np.isfinite(growth) and growth < -.08:
            blockers.append("tydligt negativ omsättningstrend")
        if _has_severe_risk(row):
            blockers.append("allvarlig riskflagga")
        if np.isfinite(quality) and quality >= 72: supports.append("mycket hög kvalitet")
        if np.isfinite(risk) and risk >= 68: supports.append("robust riskprofil")
        if np.isfinite(roe) and roe >= .15: supports.append("stark ROE")

    passed=len(blockers)==0
    return {
        "Köpfilter": "KÖPCASE" if passed else "UNDERKÄND",
        "Köpfilter godkänd": bool(passed),
        "Köpfilter gräns": float(threshold),
        "Köpfilter stopp": "; ".join(blockers) if blockers else "inga hårda stopp",
        "Köpfilter stöd": "; ".join(supports[:3]) if supports else "klarar modellens grundkrav",
    }

def apply_buy_gate(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    rows=[assess_buy_gate(r,horizon) for _,r in out.iterrows()]
    gate=pd.DataFrame(rows,index=out.index)
    overlap=[c for c in gate.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(gate)

def eligible_buys(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    gated=apply_buy_gate(df,horizon)
    if gated.empty:
        return gated
    return gated[gated["Köpfilter godkänd"].eq(True)].copy()
