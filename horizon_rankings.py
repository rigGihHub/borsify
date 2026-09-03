from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd
from buy_quality_gate import eligible_buys
from buy_card import build_buy_card
from near_buy import assess_overextension
from risk_reward import build_risk_reward, risk_reward_rank_value
from relative_strength import add_relative_strength, relative_strength_label
from market_regime import add_market_regime, filter_market_regime_eligible, market_regime_user_text
from case_readiness import add_case_readiness, filter_top_case_ready

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
    if df is None or df.empty:
        return pd.DataFrame()
    col={"day":"Daytrade Score","medium":"Mellan Score","long":"Lång Score","lifetime":"Livstid Score"}[horizon]
    out=add_horizon_scores(df)
    out=add_relative_strength(out)
    out=add_market_regime(out,horizon)
    out=eligible_buys(out,horizon)
    out=filter_market_regime_eligible(out)
    if out.empty:
        return out

    # A high score is not enough for a Top-3 slot. The case must also have
    # sufficiently complete, fresh and internally consistent evidence.
    out=add_case_readiness(out,horizon)
    out=filter_top_case_ready(out)
    if out.empty:
        return out

    extension=[assess_overextension(r,horizon) for _,r in out.iterrows()]
    ext=pd.DataFrame(extension,index=out.index)
    overlap=[c for c in ext.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    out=out.join(ext)

    # A very short-term candidate that has already moved too far should not be
    # presented as a fresh buy. For long horizons it remains visible with a warning.
    if horizon in {"day","medium"}:
        out=out[~out["För långt gången"].eq(True)].copy()
    if out.empty:
        return out

    # Risk/reward is a secondary ranking input for the two short horizons. It can
    # separate otherwise similar candidates, but does not override the core buy gate.
    if horizon in {"day","medium"}:
        rr_plans=[build_risk_reward(r,horizon) for _,r in out.iterrows()]
        out["RR plan"]=rr_plans
        out["RR rangvärde"]=[risk_reward_rank_value(p) for p in rr_plans]
        # Relative strength is deliberately only a tie-break/confirmation layer.
        # It cannot lift a failed candidate into the buy list.
        out=out.sort_values(
            [col,"Case Readiness","Relativ styrka","RR rangvärde","Datatäckning"],
            ascending=[False,False,False,False,False]
        ).head(3).copy()
    else:
        out=out.sort_values(
            [col,"Case Readiness","Datatäckning"],
            ascending=[False,False,False]
        ).head(3).copy()
        out["RR plan"]=[build_risk_reward(r,horizon) for _,r in out.iterrows()]

    out["Horisontförklaring"]=[horizon_reason(r,horizon) for _,r in out.iterrows()]
    cards=[build_buy_card(r,horizon) for _,r in out.iterrows()]
    out["Varför köpa"]=[c["Varför köpa"] for c in cards]
    out["Varför nu"]=[c["Varför nu"] for c in cards]
    out["Största risk"]=[c["Största risk"] for c in cards]
    out["Vad ändrar Borsifys syn"]=[c["Vad skulle få Borsify att ändra sig"] for c in cards]
    out["Relativ styrka text"]=[relative_strength_label(r) for _,r in out.iterrows()]
    out["Marknadsläge text"]=[market_regime_user_text(r) for _,r in out.iterrows()]
    return out
