from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from risk_reward import build_risk_reward

MIN_TOP_CASE_READINESS = 60.0

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def _present(row: pd.Series | dict[str,Any], fields: list[str]) -> tuple[int,int]:
    return sum(np.isfinite(_num(row.get(f))) for f in fields), len(fields)

def _freshness_points(value: Any) -> tuple[float,str]:
    if value is None or str(value).strip() in {"","—","nan","None"}:
        return 0.0, "datum för senaste kurs saknas"
    try:
        dt=pd.Timestamp(value)
        if dt.tzinfo is not None:
            dt=dt.tz_localize(None)
        now=pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
        age=max(0,(now.normalize()-dt.normalize()).days)
        if age <= 4:
            return 10.0, f"kursdata är {age} dagar gammal"
        if age <= 8:
            return 6.0, f"kursdata är {age} dagar gammal"
        return 0.0, f"kursdata är {age} dagar gammal och bör uppdateras"
    except Exception:
        return 0.0, "datum för senaste kurs kunde inte tolkas"

def assess_case_readiness(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,Any]:
    """Measure whether a case is sufficiently well-supported to deserve a Top-3 slot.

    This is deliberately NOT a return forecast. It rewards complete, fresh and
    internally consistent evidence and penalizes missing data or unclear risk.
    """
    if horizon not in {"day","medium","long","lifetime"}:
        raise ValueError("unknown horizon")

    score=0.0
    positives=[]
    gaps=[]
    blockers=[]

    # 1) Data foundation: max 30.
    qc=str(row.get("Universe QC","") or "")
    coverage=_num(row.get("Datatäckning"))
    if qc=="VERIFIERAD":
        score += 10
        positives.append("marknadsdatan är verifierad")
    elif qc=="DELVIS VERIFIERAD":
        score += 5
        gaps.append("marknadsdatan är bara delvis verifierad")
    elif qc=="EXKLUDERA":
        blockers.append("marknadsdatan är inte tillräckligt pålitlig")

    if np.isfinite(coverage):
        score += 10*float(np.clip((coverage-.35)/.55,0,1))
        if coverage >= .70:
            positives.append("bolagsdatan är relativt komplett")
        elif coverage < .50:
            gaps.append("för mycket bolagsdata saknas")
    else:
        gaps.append("Borsify kan inte mäta hur komplett bolagsdatan är")

    relevant={
        "day":["Dagsförändring","1 mån","Volymkvot","RSI14","Avstånd SMA200"],
        "medium":["1 mån","3 mån","6 mån","Kvalitet","Risk","Värdering"],
        "long":["INVEST Score","Kvalitet","Risk","Värdering","ROE","Vinstmarginal"],
        "lifetime":["Kvalitet","Risk","ROE","Vinstmarginal","Omsättningstillväxt","Skuld/eget kapital"],
    }[horizon]
    available,total=_present(row,relevant)
    score += 10*(available/total)
    if available==total:
        positives.append("alla viktigaste datapunkter för perioden finns")
    elif available < total-1:
        gaps.append(f"bara {available} av {total} viktiga datapunkter finns")

    # 2) Independent confirmation: max 25.
    confirmations=0
    possible=0
    def add(condition: bool):
        nonlocal confirmations, possible
        possible += 1
        confirmations += int(bool(condition))

    if horizon=="day":
        add(_num(row.get("Volymkvot")) >= 1.0)
        rsi=_num(row.get("RSI14")); add(np.isfinite(rsi) and 48 <= rsi <= 75)
        add(_num(row.get("Dagsförändring")) > 0)
        add(_num(row.get("Avstånd SMA200")) > 0)
        rel=_num(row.get("Relativ styrka")); add(np.isfinite(rel) and rel >= 55)
    elif horizon=="medium":
        add(_num(row.get("1 mån")) > 0)
        add(_num(row.get("3 mån")) > 0)
        add(_num(row.get("Kvalitet")) >= 60)
        add(_num(row.get("Risk")) >= 55)
        rel=_num(row.get("Relativ styrka")); add(np.isfinite(rel) and rel >= 55)
    elif horizon=="long":
        add(_num(row.get("INVEST Score")) >= 65)
        add(_num(row.get("Kvalitet")) >= 65)
        add(_num(row.get("Risk")) >= 60)
        add(_num(row.get("Värdering")) >= 55)
        add(_num(row.get("ROE")) >= .12)
    else:
        add(_num(row.get("Kvalitet")) >= 72)
        add(_num(row.get("Risk")) >= 68)
        add(_num(row.get("ROE")) >= .15)
        add(_num(row.get("Vinstmarginal")) >= .10)
        add(_num(row.get("Omsättningstillväxt")) >= 0)

    score += 25*(confirmations/max(possible,1))
    if confirmations >= 4:
        positives.append("flera oberoende delar pekar åt samma håll")
    elif confirmations <= 2:
        gaps.append("för få delar av analysen bekräftar varandra")

    # 3) Risk clarity: max 20.
    flags=str(row.get("Riskflaggor","") or "").lower()
    severe_terms=("negativ roe","negativ marginal","hög skuldsättning","fallande lång trend")
    severe=any(x in flags for x in severe_terms)
    if severe:
        blockers.append("en allvarlig riskflagga finns")
    else:
        score += 8
        positives.append("ingen allvarlig riskflagga stoppar caset")

    if horizon in {"day","medium"}:
        plan=build_risk_reward(row,horizon)
        rr_status=str(plan.get("RR status",""))
        if rr_status in {"ATTRAKTIVT","GODKÄNT"}:
            score += 12
            positives.append("nedsida och möjlig uppsida går att jämföra tydligt")
        elif rr_status in {"SVAGT","DÅLIGT"}:
            score += 7
            gaps.append("risk i förhållande till möjlig uppsida är inte särskilt attraktiv")
        elif rr_status=="INGEN TYDLIG MÅLNIVÅ":
            score += 5
            gaps.append("ingen tydlig tidigare nivå finns ovanför dagens kurs")
        else:
            gaps.append("Borsify kan inte räkna fram en tillräckligt tydlig riskplan")
            blockers.append("riskplanen kan inte räknas ut från tillgänglig kurshistorik")
    else:
        risk=_num(row.get("Risk"))
        debt=_num(row.get("Skuld/eget kapital"))
        if np.isfinite(risk) and risk >= 60:
            score += 8
        elif np.isfinite(risk) and risk < 45:
            gaps.append("riskprofilen är svag")
        if np.isfinite(debt):
            score += 4
        else:
            gaps.append("skuldsättningen saknas i underlaget")

    # 4) Decision clarity: max 15.
    if horizon=="day":
        clear=sum([
            bool(_num(row.get("Volymkvot")) >= 1.0),
            bool(_num(row.get("Dagsförändring")) > 0),
            bool(_num(row.get("1 mån")) > 0),
        ])
    elif horizon=="medium":
        clear=sum([
            bool(_num(row.get("1 mån")) > 0),
            bool(_num(row.get("3 mån")) > 0),
            bool(_num(row.get("Relativ styrka")) >= 55),
        ])
    elif horizon=="long":
        clear=sum([
            bool(_num(row.get("INVEST Score")) >= 65),
            bool(_num(row.get("Kvalitet")) >= 65),
            bool(_num(row.get("Värdering")) >= 55),
        ])
    else:
        clear=sum([
            bool(_num(row.get("Kvalitet")) >= 72),
            bool(_num(row.get("ROE")) >= .15),
            bool(_num(row.get("Vinstmarginal")) >= .10),
        ])
    score += 15*(clear/3)
    if clear>=2:
        positives.append("det är tydligt vad som bär caset")
    else:
        gaps.append("det är otydligt vilken huvudtes som bär caset")

    # 5) Freshness: max 10.
    fresh_points,fresh_text=_freshness_points(row.get("Prisdatum"))
    score += fresh_points
    if fresh_points >= 6:
        positives.append(fresh_text)
    else:
        gaps.append(fresh_text)

    final=float(np.clip(score,0,100))
    if blockers:
        status="STOPP – UNDERLAGET RÄCKER INTE"
        top_ready=False
    elif final >= 78:
        status="MYCKET VÄL UNDERBYGGT"
        top_ready=True
    elif final >= MIN_TOP_CASE_READINESS:
        status="TILLRÄCKLIGT UNDERBYGGT"
        top_ready=True
    else:
        status="FÖR SVAGT UNDERLAG"
        top_ready=False

    return {
        "Case Readiness":final,
        "Case Readiness status":status,
        "Case Readiness godkänd":bool(top_ready),
        "Case Readiness styrkor":"; ".join(positives[:4]) if positives else "inga tydliga styrkor i underlaget",
        "Case Readiness luckor":"; ".join(gaps[:4]) if gaps else "inga större luckor upptäckta",
        "Case Readiness stopp":"; ".join(blockers) if blockers else "",
        "Case Readiness datapunkter":f"{available}/{total}",
        "Case Readiness bekräftelser":f"{confirmations}/{possible}",
    }

def add_case_readiness(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    rows=[assess_case_readiness(r,horizon) for _,r in out.iterrows()]
    q=pd.DataFrame(rows,index=out.index)
    overlap=[c for c in q.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(q)

def filter_top_case_ready(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    if "Case Readiness godkänd" not in df.columns:
        return df.copy()
    return df[df["Case Readiness godkänd"].eq(True)].copy()
