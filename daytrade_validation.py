from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


DAYTRADE_BUY_THRESHOLD = 66.0


def _num(value: Any) -> float:
    try:
        x=float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _clip_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").clip(0, 100)


def _linear(series: pd.Series, low: float, high: float) -> pd.Series:
    return _clip_series((series-low)/(high-low)*100)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta=close.diff()
    gain=delta.clip(lower=0)
    loss=-delta.clip(upper=0)
    avg_gain=gain.rolling(window,min_periods=window).mean()
    avg_loss=loss.rolling(window,min_periods=window).mean()
    rs=avg_gain/avg_loss.replace(0,np.nan)
    return (100-(100/(1+rs))).fillna(50.0)


def _ideal_rsi(rsi: pd.Series) -> pd.Series:
    return _clip_series(100-(rsi-62).abs()*3.0)


def _flatten_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices is None or prices.empty:
        return pd.DataFrame()
    out=prices.copy()
    if isinstance(out.columns,pd.MultiIndex):
        fields={"Open","High","Low","Close","Adj Close","Volume"}
        l0=set(map(str,out.columns.get_level_values(0)))
        l1=set(map(str,out.columns.get_level_values(1)))
        if "Close" in l0:
            out.columns=out.columns.get_level_values(0)
        elif "Close" in l1:
            out.columns=out.columns.get_level_values(1)
    out=out.loc[:,~out.columns.duplicated()].copy()
    return out


def build_point_in_time_daytrade(prices: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct the *technical* part of Borsify's 1–2 day model causally.

    The live Daytrade Score includes a 10% Risk component that partly uses current
    fundamentals. Historical point-in-time fundamentals are not available, so this
    validator substitutes a causal technical risk proxy. It must therefore be read as
    validation of a close proxy to the live model, not an exact historical replay.
    """
    p=_flatten_prices(prices)
    if p.empty or "Close" not in p.columns or "Open" not in p.columns:
        return pd.DataFrame()

    close=pd.to_numeric(p["Close"],errors="coerce")
    open_=pd.to_numeric(p["Open"],errors="coerce")
    volume=pd.to_numeric(p.get("Volume",pd.Series(index=p.index,dtype=float)),errors="coerce")

    daily=close.pct_change(fill_method=None)
    m1=close.pct_change(21,fill_method=None)
    sma200=close.rolling(200,min_periods=200).mean()
    dist200=close/sma200-1
    rsi=_rsi(close)

    vol_avg=volume.rolling(20,min_periods=20).mean()
    vol_ratio=volume/vol_avg.replace(0,np.nan)

    # Point-in-time technical approximation of the live risk score.
    high252=close.rolling(252,min_periods=60).max()
    draw=close/high252-1
    risk_proxy=pd.Series(75.0,index=close.index)
    risk_proxy-=np.where(draw < -.50,16,np.where(draw < -.35,8,0))
    risk_proxy-=np.where((dist200 < -.10) & (close.pct_change(63,fill_method=None) < -.15),18,0)
    risk_proxy=risk_proxy.clip(0,100)

    score=(
        .22*_linear(daily,-.03,.04)
        +.18*_linear(m1,-.12,.18)
        +.18*_linear(vol_ratio,.6,2.0)
        +.17*_ideal_rsi(rsi)
        +.15*_linear(dist200,-.12,.15)
        +.10*risk_proxy
    ).clip(0,100)

    gate=(
        (score >= DAYTRADE_BUY_THRESHOLD)
        & (vol_ratio.isna() | (vol_ratio >= .80))
        & (rsi >= 42) & (rsi <= 79)
        & (m1.isna() | (m1 >= -.15))
        & (daily.isna() | (daily >= -.06))
    )

    # Signal is known after close on day t. Entry is next session's open, avoiding
    # the optimistic assumption that we could trade at the same close used by signal.
    entry_next_open=open_.shift(-1)
    exit_1d=close.shift(-1)
    exit_2d=close.shift(-2)
    gross_1d=exit_1d/entry_next_open-1
    gross_2d=exit_2d/entry_next_open-1

    return pd.DataFrame({
        "Close":close,
        "Open":open_,
        "Daily":daily,
        "M1":m1,
        "VolumeRatio":vol_ratio,
        "RSI":rsi,
        "Dist200":dist200,
        "RiskProxy":risk_proxy,
        "DaytradeProxy":score,
        "BuyGateProxy":gate.astype(bool),
        "EntryNextOpen":entry_next_open,
        "Gross1d":gross_1d,
        "Gross2d":gross_2d,
    })


def _spaced_signals(frame: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    candidates=frame[frame["BuyGateProxy"].eq(True)].copy()
    if candidates.empty:
        return candidates
    positions={idx:i for i,idx in enumerate(frame.index)}
    chosen=[]
    last=-10**9
    spacing=max(1,int(horizon_days))
    for idx in candidates.index:
        pos=positions[idx]
        if pos-last >= spacing:
            chosen.append(idx)
            last=pos
    return candidates.loc[chosen].copy()


def evaluate_daytrade(
    signals: pd.DataFrame,
    horizon_days: int,
    roundtrip_cost_bps: float = 20.0,
) -> dict[str,Any]:
    if signals is None or signals.empty or horizon_days not in (1,2):
        return {"signals":0}
    col="Gross1d" if horizon_days==1 else "Gross2d"
    work=_spaced_signals(signals,horizon_days)
    vals=pd.to_numeric(work.get(col),errors="coerce").dropna()
    baseline=pd.to_numeric(signals.get(col),errors="coerce").dropna()
    if vals.empty:
        return {"signals":0}

    cost=float(roundtrip_cost_bps)/10000.0
    net=vals-cost
    wins=net[net>0]
    losses=net[net<0]
    gross_profit=float(wins.sum()) if not wins.empty else 0.0
    gross_loss=abs(float(losses.sum())) if not losses.empty else 0.0
    pf=gross_profit/gross_loss if gross_loss>0 else np.nan

    return {
        "signals":int(len(net)),
        "gross_median":float(vals.median()),
        "net_median":float(net.median()),
        "net_mean":float(net.mean()),
        "hit_rate":float((net>0).mean()),
        "baseline_median":float(baseline.median()-cost) if not baseline.empty else np.nan,
        "median_excess":float(net.median()-(baseline.median()-cost)) if not baseline.empty else np.nan,
        "profit_factor":float(pf) if np.isfinite(pf) else np.nan,
        "worst_trade":float(net.min()),
        "p05":float(net.quantile(.05)),
        "cost_bps":float(roundtrip_cost_bps),
    }


def walk_forward_fixed_gate(
    signals: pd.DataFrame,
    horizon_days: int,
    roundtrip_cost_bps: float = 20.0,
    min_train_days: int = 504,
    test_days: int = 126,
) -> pd.DataFrame:
    """Sequential OOS windows with the rule frozen at today's threshold.

    No threshold or weight is optimized on the training window. The training span is
    retained only to ensure that each test window occurs after a meaningful history.
    """
    if signals is None or signals.empty:
        return pd.DataFrame()
    rows=[]
    start=max(int(min_train_days),200)
    n=len(signals)
    while start < n-horizon_days:
        test=signals.iloc[start:min(n,start+int(test_days))]
        stats=evaluate_daytrade(test,horizon_days,roundtrip_cost_bps)
        rows.append({
            "TestStart":test.index[0],
            "TestEnd":test.index[-1],
            "Signals":int(stats.get("signals",0)),
            "NetMedian":stats.get("net_median",np.nan),
            "HitRate":stats.get("hit_rate",np.nan),
            "MedianExcess":stats.get("median_excess",np.nan),
        })
        start += int(test_days)
    return pd.DataFrame(rows)


def validation_grade(full_stats: dict[str,Any], walk_forward: pd.DataFrame) -> dict[str,str]:
    n=int(full_stats.get("signals",0) or 0)
    med=_num(full_stats.get("net_median"))
    hit=_num(full_stats.get("hit_rate"))
    excess=_num(full_stats.get("median_excess"))

    if n < 20:
        return {
            "status":"Ej validerad",
            "message":"För få oberoende signaler för att dra en användbar slutsats.",
        }

    wf=walk_forward.copy() if isinstance(walk_forward,pd.DataFrame) else pd.DataFrame()
    wf_valid=wf[pd.to_numeric(wf.get("Signals",0),errors="coerce").fillna(0)>=3] if not wf.empty else pd.DataFrame()
    positive_share=np.nan
    if not wf_valid.empty:
        positive_share=float((pd.to_numeric(wf_valid["NetMedian"],errors="coerce")>0).mean())

    positives=sum([
        bool(np.isfinite(med) and med>0),
        bool(np.isfinite(hit) and hit>.52),
        bool(np.isfinite(excess) and excess>0),
        bool(np.isfinite(positive_share) and positive_share>=.60),
    ])

    if n >= 40 and positives >= 4:
        return {
            "status":"Historiskt lovande – ej bevisad edge",
            "message":"Den fasta modellen visar positivt stöd även efter kostnadsantagande och över flera OOS-fönster. Det är fortfarande inte bevis på framtida alpha.",
        }
    if positives >= 2:
        return {
            "status":"Svagt/blandat historiskt stöd",
            "message":"Vissa mått är positiva men stödet är inte tillräckligt konsekvent för att kalla modellen historiskt robust.",
        }
    return {
        "status":"Ingen tydlig historisk edge",
        "message":"Den fasta 1–2-dagarsregeln visar inte tillräckligt konsekvent nettostöd i detta test.",
    }


def compare_horizons(
    signals: pd.DataFrame,
    roundtrip_cost_bps: float = 20.0,
    min_train_days: int = 504,
    test_days: int = 126,
) -> pd.DataFrame:
    rows=[]
    for h in (1,2):
        stats=evaluate_daytrade(signals,h,roundtrip_cost_bps)
        wf=walk_forward_fixed_gate(signals,h,roundtrip_cost_bps,min_train_days,test_days)
        grade=validation_grade(stats,wf)
        rows.append({
            "Horisont":f"{h} handelsdag" + ("" if h==1 else "ar"),
            "Signaler":int(stats.get("signals",0)),
            "Netto median":stats.get("net_median",np.nan),
            "Träffsäkerhet":stats.get("hit_rate",np.nan),
            "Median över baseline":stats.get("median_excess",np.nan),
            "Profit factor":stats.get("profit_factor",np.nan),
            "Status":grade["status"],
        })
    return pd.DataFrame(rows)
