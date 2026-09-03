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

def _history(row: pd.Series | dict[str,Any]) -> pd.DataFrame:
    hist=row.get("_history")
    if not isinstance(hist,pd.DataFrame) or hist.empty:
        return pd.DataFrame()
    out=hist.copy()
    # yfinance sometimes returns one-level frames here; keep only needed numeric cols.
    for c in ("Open","High","Low","Close"):
        if c in out.columns:
            out[c]=pd.to_numeric(out[c],errors="coerce")
    return out

def _atr14(hist: pd.DataFrame) -> float:
    if hist.empty or not {"High","Low","Close"}.issubset(hist.columns):
        return np.nan
    h=hist["High"]; l=hist["Low"]; c=hist["Close"]
    prev=c.shift(1)
    tr=pd.concat([(h-l).abs(),(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    val=tr.rolling(14,min_periods=10).mean().iloc[-1]
    return _num(val)

def _nearest_above(values: pd.Series, price: float) -> float:
    vals=pd.to_numeric(values,errors="coerce").dropna()
    vals=vals[vals>price*1.002]
    return float(vals.min()) if not vals.empty else np.nan

def _nearest_below(values: pd.Series, price: float) -> float:
    vals=pd.to_numeric(values,errors="coerce").dropna()
    vals=vals[vals<price*0.998]
    return float(vals.max()) if not vals.empty else np.nan

def build_risk_reward(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,Any]:
    """Build a transparent, deterministic trade plan from price history.

    No AI targets. Entry is anchored to the latest price. The stop is based on a
    recent low with an ATR sanity bound. Targets come from previously traded highs.
    If price history cannot support those levels, the engine returns insufficient
    data rather than fabricating a target.
    """
    if horizon not in {"day","medium"}:
        return {
            "RR status":"EJ TILLÄMPLIGT",
            "RR förklaring":"Risk/uppsida-planen används bara för kortare handel i denna version.",
        }

    price=_num(row.get("Pris"))
    hist=_history(row)
    if not np.isfinite(price) or hist.empty or not {"High","Low","Close"}.issubset(hist.columns):
        return {
            "RR status":"FÖR LITE DATA",
            "RR förklaring":"Borsify saknar tillräcklig kurshistorik för att räkna fram nivåerna utan att gissa.",
        }

    hist=hist.dropna(subset=["High","Low","Close"]).copy()
    if len(hist)<20:
        return {
            "RR status":"FÖR LITE DATA",
            "RR förklaring":"Minst ungefär 20 handelsdagar behövs för en rimlig risk/uppsida-bedömning.",
        }

    atr=_atr14(hist)
    if not np.isfinite(atr) or atr<=0:
        return {
            "RR status":"FÖR LITE DATA",
            "RR förklaring":"Borsify kunde inte räkna ut aktiens normala dagsrörelse.",
        }

    lookback=10 if horizon=="day" else min(40,len(hist))
    recent=hist.tail(lookback)
    recent_low=_num(recent["Low"].min())

    # Stop: below recent support, but not unrealistically tight. For short horizons
    # use at least 1 ATR; medium at least 1.5 ATR below current price.
    atr_mult=1.0 if horizon=="day" else 1.5
    atr_stop=price-atr_mult*atr
    stop=min(recent_low,atr_stop) if np.isfinite(recent_low) else atr_stop

    # Prevent a historical one-off spike low from making the plan useless.
    max_risk_pct=.08 if horizon=="day" else .15
    floor_stop=price*(1-max_risk_pct)
    stop=max(stop,floor_stop)

    if not np.isfinite(stop) or stop>=price:
        return {
            "RR status":"FÖR LITE DATA",
            "RR förklaring":"Borsify hittade ingen rimlig nivå där den kortsiktiga analysen kan betraktas som fel.",
        }

    risk_per_share=price-stop
    risk_pct=risk_per_share/price

    # Targets must come from observed prior highs above the current price.
    # Exclude latest bar so today's high isn't falsely treated as a future target.
    prior=hist.iloc[:-1] if len(hist)>1 else hist
    window1=prior.tail(60 if horizon=="medium" else 30)
    window2=prior.tail(126 if len(prior)>=60 else len(prior))
    t1=_nearest_above(window1["High"],price)
    t2=_nearest_above(window2["High"],price)

    # Ensure target 2 is genuinely beyond target 1 if possible.
    if np.isfinite(t1) and np.isfinite(t2) and t2<=t1*1.002:
        higher=pd.to_numeric(window2["High"],errors="coerce").dropna()
        higher=higher[higher>t1*1.002]
        t2=float(higher.min()) if not higher.empty else np.nan

    if not np.isfinite(t1):
        return {
            "RR status":"INGEN TYDLIG MÅLNIVÅ",
            "Entry låg":price,
            "Entry hög":price+0.25*atr,
            "Stop":stop,
            "Risk %":risk_pct,
            "ATR14":atr,
            "RR förklaring":"Borsify hittar ingen tidigare tydlig kurstopp ovanför dagens pris. Därför skapas ingen påhittad målnivå.",
        }

    reward1=t1-price
    rr1=reward1/risk_per_share if risk_per_share>0 else np.nan
    rr2=(t2-price)/risk_per_share if np.isfinite(t2) and risk_per_share>0 else np.nan

    if rr1>=2.0:
        status="ATTRAKTIVT"
    elif rr1>=1.4:
        status="GODKÄNT"
    elif rr1>=1.0:
        status="SVAGT"
    else:
        status="DÅLIGT"

    return {
        "RR status":status,
        "Entry låg":price,
        "Entry hög":price+0.25*atr,
        "Stop":stop,
        "Mål 1":t1,
        "Mål 2":t2,
        "Risk %":risk_pct,
        "RR 1":rr1,
        "RR 2":rr2,
        "ATR14":atr,
        "RR förklaring":(
            "Nivåerna bygger på dagens kurs, aktiens normala dagsrörelse, en nylig botten och tidigare kurstoppar. "
            "De är tekniska referensnivåer – inte en prognos om vart kursen kommer gå."
        ),
    }

def risk_reward_rank_value(plan: dict[str,Any]) -> float:
    rr=_num(plan.get("RR 1"))
    if not np.isfinite(rr):
        return -1.0
    return float(rr)
