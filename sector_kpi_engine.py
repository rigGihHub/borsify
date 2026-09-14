from __future__ import annotations
"""Conservative sector KPI extraction from structured financial statements.

Only metrics directly observable in the fetched statements are emitted. KPI concepts
that Yahoo/yfinance does not expose (e.g. NRR, churn, order intake, CET1) remain
explicit gaps rather than estimates.
"""
import math
from typing import Any
import numpy as np
import pandas as pd

def _row(frame:pd.DataFrame|None,names:list[str])->pd.Series|None:
    if not isinstance(frame,pd.DataFrame) or frame.empty:return None
    norm={str(i).lower().replace(" ","").replace("_",""):i for i in frame.index}
    for n in names:
        k=n.lower().replace(" ","").replace("_","")
        if k in norm:
            s=pd.to_numeric(frame.loc[norm[k]],errors="coerce").dropna()
            return s if not s.empty else None
    return None

def _latest(s:pd.Series|None)->float:
    if s is None or s.empty:return np.nan
    try:
        # statement columns are dates; sort newest first where possible
        x=s.copy()
        try:x=x.reindex(sorted(x.index,reverse=True))
        except Exception:pass
        v=float(x.iloc[0]); return v if math.isfinite(v) else np.nan
    except Exception:return np.nan

def _growth(s:pd.Series|None)->float:
    if s is None or len(s)<2:return np.nan
    try:
        x=s.copy()
        try:x=x.reindex(sorted(x.index,reverse=True))
        except Exception:pass
        a,b=float(x.iloc[0]),float(x.iloc[1])
        return a/b-1 if math.isfinite(a) and math.isfinite(b) and b!=0 else np.nan
    except Exception:return np.nan

def extract_sector_kpis(sector:str,industry:str,qi:pd.DataFrame|None,qc:pd.DataFrame|None,qb:pd.DataFrame|None)->dict[str,Any]:
    s=(str(sector or "")+" "+str(industry or "")).lower()
    revenue=_row(qi,["Total Revenue","Operating Revenue"])
    gross=_row(qi,["Gross Profit"])
    opinc=_row(qi,["Operating Income"])
    inventory=_row(qb,["Inventory"])
    fcf=_row(qc,["Free Cash Flow"])
    debt=_row(qb,["Total Debt"])
    equity=_row(qb,["Stockholders Equity","Total Equity Gross Minority Interest"])
    out:dict[str,Any]={}
    rev=_latest(revenue); gp=_latest(gross); oi=_latest(opinc)
    if math.isfinite(rev):
        out["KPI Omsättning QoQ"]=_growth(revenue)
        if math.isfinite(gp):out["KPI Bruttomarginal"]=gp/rev
        if math.isfinite(oi):out["KPI Rörelsemarginal"]=oi/rev
    out["KPI FCF QoQ"]=_growth(fcf)
    if math.isfinite(_latest(debt)) and math.isfinite(_latest(equity)) and _latest(equity)!=0:
        out["KPI Skuld/eget kapital rapport"]= _latest(debt)/_latest(equity)

    if any(x in s for x in ["retail","consumer cyclical","apparel","restaurant"]):
        out["KPI Lager QoQ"]=_growth(inventory)
        out["KPI-specifika observerade"]="lagerutveckling" if math.isfinite(out["KPI Lager QoQ"]) else ""
        out["KPI-specifika saknas"]="like-for-like; butiks-/kanalekonomi"
    elif any(x in s for x in ["software","saas","internet","technology","it services"]):
        out["KPI-specifika observerade"]="bruttomarginal/FCF-konvertering" if math.isfinite(out.get("KPI Bruttomarginal",np.nan)) or math.isfinite(out.get("KPI FCF QoQ",np.nan)) else ""
        out["KPI-specifika saknas"]="ARR/återkommande intäkter; NRR/churn; CAC/payback"
    elif any(x in s for x in ["industrial","machinery","engineering","aerospace","construction"]):
        out["KPI-specifika observerade"]="marginal/FCF genom cykeln" if math.isfinite(out.get("KPI Rörelsemarginal",np.nan)) or math.isfinite(out.get("KPI FCF QoQ",np.nan)) else ""
        out["KPI-specifika saknas"]="orderingång/orderbok; pris/mix; kapacitetsutnyttjande"
    elif any(x in s for x in ["bank","financial","insurance","credit"]):
        out["KPI-specifika observerade"]=""
        out["KPI-specifika saknas"]="CET1/kapitalrelation; kreditförluster; räntenetto/marginal; inlånings-/finansieringsmix"
    else:
        out["KPI-specifika observerade"]=""
        out["KPI-specifika saknas"]=""
    observed=[k for k,v in out.items() if k.startswith("KPI ") and isinstance(v,(int,float,np.floating)) and math.isfinite(float(v))]
    out["KPI strukturerad täckning"]=len(observed)
    return out
