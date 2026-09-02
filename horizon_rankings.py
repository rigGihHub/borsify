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

def _clip(x: float) -> float:
    return float(np.clip(x,0,100))

def _pct_score(v: Any, low: float, high: float) -> float:
    x=_num(v)
    if not np.isfinite(x): return 50.0
    return _clip((x-low)/(high-low)*100)

def _ideal_rsi(v: Any) -> float:
    x=_num(v)
    if not np.isfinite(x): return 50.0
    # Daytrading sweet spot: strength without extreme overextension.
    return _clip(100 - abs(x-62)*3.0)

def add_horizon_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    rows=[]
    for _,r in out.iterrows():
        day = (
            .22*_pct_score(r.get("Dagsförändring"),-.03,.04)
            + .18*_pct_score(r.get("1 mån"),-.12,.18)
            + .18*_pct_score(r.get("Volymkvot"),.6,2.0)
            + .17*_ideal_rsi(r.get("RSI14"))
            + .15*_pct_score(r.get("Avstånd SMA200"),-.12,.15)
            + .10*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)
        )
        medium = (
            .24*_pct_score(r.get("1 mån"),-.18,.25)
            + .24*_pct_score(r.get("3 mån"),-.30,.45)
            + .12*_pct_score(r.get("6 mån"),-.40,.65)
            + .16*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)
            + .12*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)
            + .12*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)
        )
        long = (
            .38*_num(r.get("INVEST Score") if np.isfinite(_num(r.get("INVEST Score"))) else 50)
            + .25*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)
            + .17*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)
            + .20*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)
        )
        # "Resten av livet" intentionally favors durable quality/risk over cheapness/momentum.
        lifetime = (
            .40*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)
            + .25*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)
            + .12*_pct_score(r.get("ROE"),0,.30)
            + .10*_pct_score(r.get("Vinstmarginal"),0,.25)
            + .08*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)
            + .05*_pct_score(r.get("Omsättningstillväxt"),-.05,.15)
        )
        rows.append((_clip(day),_clip(medium),_clip(long),_clip(lifetime)))
    vals=pd.DataFrame(rows,index=out.index,columns=["Daytrade Score","Mellan Score","Lång Score","Livstid Score"])
    return out.join(vals)

def horizon_reason(row: pd.Series|dict[str,Any], horizon: str) -> str:
    r=row
    if horizon=="day":
        parts=[]
        if _num(r.get("Volymkvot"))>=1.2: parts.append("ovanligt hög handelsaktivitet")
        if _num(r.get("Dagsförändring"))>0: parts.append("positiv dagsmomentum")
        if _num(r.get("RSI14"))>=50 and _num(r.get("RSI14"))<=72: parts.append("starkt men inte extremt RSI")
        if _num(r.get("Avstånd SMA200"))>0: parts.append("handlas över lång trend")
        return "; ".join(parts[:3]) or "balanserad kombination av momentum, trend och risk"
    if horizon=="medium":
        parts=[]
        if _num(r.get("3 mån"))>0: parts.append("positiv 3-månaderstrend")
        if _num(r.get("1 mån"))>0: parts.append("positiv senaste månad")
        if _num(r.get("Kvalitet"))>=65: parts.append("god fundamental kvalitet")
        if _num(r.get("Risk"))>=65: parts.append("relativt robust riskprofil")
        return "; ".join(parts[:3]) or "balanserad 1–3-månadersbild"
    if horizon=="long":
        parts=[]
        if _num(r.get("INVEST Score"))>=65: parts.append("stark INVEST-bedömning")
        if _num(r.get("Kvalitet"))>=65: parts.append("hög kvalitet")
        if _num(r.get("Värdering"))>=60: parts.append("rimlig/attraktiv värdering")
        if _num(r.get("Risk"))>=65: parts.append("robust riskprofil")
        return "; ".join(parts[:3]) or "balanserad flerårsprofil"
    parts=[]
    if _num(r.get("Kvalitet"))>=70: parts.append("hög bolagskvalitet")
    if _num(r.get("Risk"))>=70: parts.append("robust finansiell/riskmässig profil")
    if _num(r.get("ROE"))>=.15: parts.append("stark avkastning på eget kapital")
    if _num(r.get("Vinstmarginal"))>=.10: parts.append("god lönsamhet")
    return "; ".join(parts[:3]) or "kvalitetsprofil lämpad för mycket lång ägarhorisont"

def top_three(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    col={"day":"Daytrade Score","medium":"Mellan Score","long":"Lång Score","lifetime":"Livstid Score"}[horizon]
    out=add_horizon_scores(df)
    out=out.sort_values([col,"Datatäckning"],ascending=[False,False]).head(3).copy()
    out["Horisontförklaring"]=[horizon_reason(r,horizon) for _,r in out.iterrows()]
    return out
