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


def _rank_score(series: pd.Series, higher_is_better: bool=True) -> pd.Series:
    s=pd.to_numeric(series,errors="coerce")
    out=pd.Series(50.0,index=s.index,dtype=float)
    valid=s.notna()
    if valid.sum() >= 2:
        pct=s[valid].rank(pct=True,method="average")*100
        if not higher_is_better:
            pct=100-pct+(100/valid.sum())
        out.loc[valid]=pct.clip(0,100)
    return out


def add_price_only_prefilter_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Build cheap candidate scores using only quote/history fields.

    No fundamental fields, analyst targets, sectors or AI outputs are used.
    The goal is recall testing, not a new investment score.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()

    out=df.copy()
    daily=pd.to_numeric(out.get("Dagsförändring"),errors="coerce")
    m1=pd.to_numeric(out.get("1 mån"),errors="coerce")
    m3=pd.to_numeric(out.get("3 mån"),errors="coerce")
    m6=pd.to_numeric(out.get("6 mån"),errors="coerce")
    draw=pd.to_numeric(out.get("52v från topp"),errors="coerce")
    rsi=pd.to_numeric(out.get("RSI14"),errors="coerce")
    vol=pd.to_numeric(out.get("Volymkvot"),errors="coerce")
    dist=pd.to_numeric(out.get("Avstånd SMA200"),errors="coerce")
    turnover=pd.to_numeric(out.get("Omsättning lokal M/dag"),errors="coerce")

    # Trend lens: favors sustained strength without requiring extreme extension.
    trend=(
        .18*_rank_score(m1,True)
        +.32*_rank_score(m3,True)
        +.25*_rank_score(m6,True)
        +.15*_rank_score(dist,True)
        +.10*_rank_score(turnover,True)
    )

    # Pullback lens: looks for liquid shares that have pulled back without a fully
    # broken long trend. These are cheap-to-compute technical conditions only.
    draw_ideal=(100*np.exp(-((draw+.18)/.18)**2)).where(draw.notna(),50)
    rsi_ideal=(100*np.exp(-((rsi-45)/18)**2)).where(rsi.notna(),50)
    pullback=(
        .30*draw_ideal
        +.25*rsi_ideal
        +.20*_rank_score(m3,True)
        +.15*_rank_score(turnover,True)
        +.10*_rank_score(dist,True)
    )

    # Reversal lens: allows recent weakness to remain in the pool so the prefilter
    # does not only select momentum names.
    daily_selloff=((-.01-daily)/.08*100).clip(0,100).fillna(0)
    oversold=((52-rsi)/25*100).clip(0,100).fillna(30)
    reversal=(
        .28*daily_selloff
        +.24*oversold
        +.18*draw_ideal
        +.15*_rank_score(turnover,True)
        +.15*_rank_score(m1,False)
    )

    # Stability/diversity lens: flat-to-positive long trend with adequate history
    # gets representation even when it is neither strong momentum nor oversold.
    stable_dist=(100*np.exp(-((dist-.04)/.12)**2)).where(dist.notna(),50)
    stable_m3=(100*np.exp(-((m3-.04)/.18)**2)).where(m3.notna(),50)
    stability=.45*stable_dist+.35*stable_m3+.20*_rank_score(turnover,True)

    out["Prefilter trend"]=trend.round(1)
    out["Prefilter rekyl"]=pullback.round(1)
    out["Prefilter vändning"]=reversal.round(1)
    out["Prefilter stabilitet"]=stability.round(1)
    out["Prefilter bästa pris-signal"]=out[
        ["Prefilter trend","Prefilter rekyl","Prefilter vändning","Prefilter stabilitet"]
    ].max(axis=1)
    return out


def build_candidate_pool(
    df: pd.DataFrame,
    fraction: float=.60,
    minimum: int=80,
) -> pd.DataFrame:
    """Diversified union of several price-only lenses.

    The requested size is approximately max(minimum, fraction*universe), capped at
    the universe size. Equal quotas across lenses reduce one-factor concentration.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()

    scored=add_price_only_prefilter_scores(df)
    n=len(scored)
    target=min(n,max(int(math.ceil(n*float(fraction))),int(minimum)))
    lenses=["Prefilter trend","Prefilter rekyl","Prefilter vändning","Prefilter stabilitet"]
    quota=max(1,int(math.ceil(target/len(lenses))))

    selected=[]
    seen=set()
    for lens in lenses:
        for idx in scored.sort_values([lens,"Ticker"],ascending=[False,True]).index[:quota]:
            if idx not in seen:
                seen.add(idx); selected.append(idx)

    # Fill remaining places using the strongest result from any price-only lens.
    if len(selected)<target:
        for idx in scored.sort_values(
            ["Prefilter bästa pris-signal","Ticker"],ascending=[False,True]
        ).index:
            if idx not in seen:
                seen.add(idx); selected.append(idx)
                if len(selected)>=target:
                    break

    return scored.loc[selected[:target]].copy()


def validate_candidate_pool(
    full_df: pd.DataFrame,
    target_symbols: list[str] | set[str],
    fraction: float=.60,
    minimum: int=80,
) -> dict[str,Any]:
    if full_df is None or full_df.empty:
        return {
            "status":"För lite underlag","universe":0,"pool":0,
            "targets":0,"retained":0,"retention":np.nan,"missed":[],
        }

    targets={str(x) for x in target_symbols if str(x)}
    pool=build_candidate_pool(full_df,fraction=fraction,minimum=minimum)
    pool_symbols=set(pool.get("Ticker",pd.Series(dtype=str)).astype(str))
    retained=targets & pool_symbols
    missed=sorted(targets-pool_symbols)
    retention=(len(retained)/len(targets)) if targets else np.nan

    if not targets:
        status="Inga toppcase att jämföra"
    elif retention >= .98:
        status="Mycket hög träff"
    elif retention >= .95:
        status="Hög träff"
    elif retention >= .90:
        status="För osäkert"
    else:
        status="Inte tillräckligt säkert"

    return {
        "status":status,
        "universe":int(len(full_df)),
        "pool":int(len(pool)),
        "targets":int(len(targets)),
        "retained":int(len(retained)),
        "retention":float(retention) if np.isfinite(retention) else np.nan,
        "missed":missed,
        "fraction":float(len(pool)/len(full_df)) if len(full_df) else np.nan,
    }


def activation_readiness(history: pd.DataFrame, minimum_runs: int=5) -> dict[str,Any]:
    """Require repeated high recall before recommending real API pruning."""
    if history is None or history.empty or "retention" not in history.columns:
        return {"ready":False,"status":"För lite historik","runs":0}

    work=history.copy()
    work["retention"]=pd.to_numeric(work["retention"],errors="coerce")
    work=work.dropna(subset=["retention"])
    if len(work)<minimum_runs:
        return {
            "ready":False,
            "status":f"För lite historik – {len(work)}/{minimum_runs} körningar",
            "runs":int(len(work)),
        }

    recent=work.tail(max(minimum_runs,10))
    mean=float(recent["retention"].mean())
    minimum=float(recent["retention"].min())
    ready=bool(mean>=.98 and minimum>=.95)
    return {
        "ready":ready,
        "status":"Tillräckligt stabil för kontrollerat test" if ready else "Inte tillräckligt säker ännu",
        "runs":int(len(recent)),
        "mean_retention":mean,
        "min_retention":minimum,
    }
