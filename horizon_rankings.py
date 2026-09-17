from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd
from buy_now_selection import select_buy_now
from buy_card import build_buy_card
from near_buy import assess_overextension
from risk_reward import build_risk_reward, risk_reward_rank_value
from relative_strength import add_relative_strength, relative_strength_label
from market_regime import add_market_regime, filter_market_regime_eligible, market_regime_user_text
from case_readiness import add_case_readiness, filter_top_case_ready
from liquidity_guard import add_liquidity_guard, filter_execution_ready
from good_deal import add_good_deal
from negative_overreaction import add_negative_overreaction
from mispriced_acceleration import add_mispriced_acceleration
from hidden_inflection import add_hidden_inflection
from quality_compounder_ignored import add_quality_compounder_ignored
from underfollowed_quality import add_underfollowed_quality
from earnings_power_noise import add_earnings_power_noise
from operating_leverage_setup import add_operating_leverage_setup
from balance_sheet_optionality import add_balance_sheet_optionality
from cash_conversion_inflection import add_cash_conversion_inflection
from margin_recovery_before_consensus import add_margin_recovery_before_consensus
from revision_breadth import add_revision_breadth
from deal_conviction import add_deal_conviction

def _num(v: Any) -> float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def _clip(x: float) -> float:return float(np.clip(x,0,100))
def _pct_score(v: Any,low: float,high: float)->float:
    x=_num(v)
    if not np.isfinite(x):return 50.0
    return _clip((x-low)/(high-low)*100)
def _ideal_rsi(v: Any)->float:
    x=_num(v)
    if not np.isfinite(x):return 50.0
    return _clip(100-abs(x-62)*3.0)

def add_horizon_scores(df: pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); rows=[]
    for _,r in out.iterrows():
        day=.22*_pct_score(r.get("Dagsförändring"),-.03,.04)+.18*_pct_score(r.get("1 mån"),-.12,.18)+.18*_pct_score(r.get("Volymkvot"),.6,2.0)+.17*_ideal_rsi(r.get("RSI14"))+.15*_pct_score(r.get("Avstånd SMA200"),-.12,.15)+.10*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)
        medium=.24*_pct_score(r.get("1 mån"),-.18,.25)+.24*_pct_score(r.get("3 mån"),-.30,.45)+.12*_pct_score(r.get("6 mån"),-.40,.65)+.16*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)+.12*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)+.12*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)
        long=.38*_num(r.get("INVEST Score") if np.isfinite(_num(r.get("INVEST Score"))) else 50)+.25*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)+.17*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)+.20*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)
        lifetime=.40*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)+.25*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)+.12*_pct_score(r.get("ROE"),0,.30)+.10*_pct_score(r.get("Vinstmarginal"),0,.25)+.08*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)+.05*_pct_score(r.get("Omsättningstillväxt"),-.05,.15)
        year=.30*_num(r.get("INVEST Score") if np.isfinite(_num(r.get("INVEST Score"))) else 50)+.20*_num(r.get("Kvalitet") if np.isfinite(_num(r.get("Kvalitet"))) else 50)+.15*_num(r.get("Risk") if np.isfinite(_num(r.get("Risk"))) else 50)+.15*_num(r.get("Värdering") if np.isfinite(_num(r.get("Värdering"))) else 50)+.10*_pct_score(r.get("6 mån"),-.35,.55)+.10*_pct_score(r.get("3 mån"),-.25,.40)
        rows.append((_clip(day),_clip(medium),_clip(year),_clip(long),_clip(lifetime)))
    return out.join(pd.DataFrame(rows,index=out.index,columns=["Daytrade Score","Mellan Score","Års Score","Lång Score","Livstid Score"]))

def horizon_reason(r,horizon):
    if horizon=="day":
        p=[]
        if _num(r.get("Volymkvot"))>=1.2:p.append("ovanligt hög handel")
        if _num(r.get("Dagsförändring"))>0:p.append("priset stiger idag")
        if 50<=_num(r.get("RSI14"))<=72:p.append("priset visar styrka utan att se extremt ut")
        return "; ".join(p[:3]) or "flera kortsiktiga tecken ser bra ut"
    if horizon=="medium":
        p=[]
        if _num(r.get("3 mån"))>0:p.append("priset har stigit på tre månader")
        if _num(r.get("Kvalitet"))>=65:p.append("bolaget får högt kvalitetsbetyg")
        return "; ".join(p[:3]) or "både bolaget och prisutvecklingen ser tillräckligt bra ut"
    if horizon=="long":
        p=[]
        if _num(r.get("Kvalitet"))>=65:p.append("bolaget får högt kvalitetsbetyg")
        if _num(r.get("Värdering"))>=60:p.append("priset ser rimligt ut jämfört med bolagets ekonomi")
        if _num(r.get("Risk"))>=65:p.append("riskbilden är relativt stabil")
        return "; ".join(p[:3]) or "kvalitet, pris och risk fungerar bra tillsammans"
    p=[]
    if _num(r.get("Kvalitet"))>=70:p.append("bolaget har hög kvalitet")
    if _num(r.get("ROE"))>=.15:p.append("bolaget tjänar bra på ägarnas kapital")
    return "; ".join(p[:3]) or "flera tecken tyder på uthållig kvalitet"

def top_ranked(df: pd.DataFrame,horizon: str,limit: int=3)->pd.DataFrame:
    if df is None or df.empty:return pd.DataFrame()
    col={"day":"Daytrade Score","medium":"Mellan Score","year":"Års Score","long":"Lång Score","lifetime":"Livstid Score"}[horizon]
    gate_horizon="long" if horizon=="year" else horizon
    out=add_horizon_scores(df); out=add_relative_strength(out); out=add_market_regime(out,gate_horizon)
    # Critical: user-facing Köp nu lists must pass both the normal quality gate and
    # the anti-chase gate. For horizon=year, select_buy_now maps long -> strict year policy.
    out=select_buy_now(out,gate_horizon)
    out=filter_market_regime_eligible(out)
    if out.empty:return out
    out=add_liquidity_guard(out,gate_horizon); out=filter_execution_ready(out,gate_horizon)
    if out.empty:return out
    out=add_case_readiness(out,gate_horizon); out=filter_top_case_ready(out)
    if out.empty:return out
    extension=[assess_overextension(r,gate_horizon) for _,r in out.iterrows()]; ext=pd.DataFrame(extension,index=out.index); overlap=[c for c in ext.columns if c in out.columns]
    if overlap:out=out.drop(columns=overlap)
    out=out.join(ext)
    if gate_horizon in {"day","medium"}:out=out[~out["För långt gången"].eq(True)].copy()
    if out.empty:return out
    out=add_good_deal(out,horizon); out=add_negative_overreaction(out); out=add_mispriced_acceleration(out); out=add_hidden_inflection(out); out=add_quality_compounder_ignored(out,horizon); out=add_underfollowed_quality(out,horizon); out=add_earnings_power_noise(out,horizon); out=add_operating_leverage_setup(out,horizon); out=add_balance_sheet_optionality(out,horizon); out=add_cash_conversion_inflection(out); out=add_margin_recovery_before_consensus(out); out=add_revision_breadth(out); out=add_deal_conviction(out,horizon)
    if gate_horizon in {"day","medium"}:
        rr=[build_risk_reward(r,gate_horizon) for _,r in out.iterrows()]; out["RR plan"]=rr; out["RR rangvärde"]=[risk_reward_rank_value(p) for p in rr]
        out=out.sort_values([col,"Deal Conviction Score","Affärsläge rangvärde","Case Readiness","Relativ styrka","RR rangvärde","Datatäckning"],ascending=[False]*7).head(limit).copy()
    else:
        out=out.sort_values([col,"Deal Conviction Score","Affärsläge rangvärde","Case Readiness","Datatäckning"],ascending=[False]*5).head(limit).copy(); out["RR plan"]=[build_risk_reward(r,gate_horizon) for _,r in out.iterrows()]
    reason_horizon="long" if horizon=="year" else horizon
    out["Horisontförklaring"]=[horizon_reason(r,reason_horizon) for _,r in out.iterrows()]
    cards=[build_buy_card(r,gate_horizon) for _,r in out.iterrows()]
    out["Varför köpa"]=[c["Därför kan aktien vara värd att köpa"] for c in cards]
    out["Varför nu"]=[c["Varför just nu"] for c in cards]
    out["Största risk"]=[c["Det här är den största risken"] for c in cards]
    out["Vad ändrar Borsifys syn"]=[c["Då skulle Borsify tänka om"] for c in cards]
    out["Relativ styrka text"]=[relative_strength_label(r) for _,r in out.iterrows()]
    out["Marknadsläge text"]=[market_regime_user_text(r) for _,r in out.iterrows()]
    return out

def top_three(df: pd.DataFrame,horizon: str)->pd.DataFrame:return top_ranked(df,horizon,limit=3)
