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

def _yes(v: Any) -> bool:
    if isinstance(v,bool): return v
    return str(v or "").strip().lower() in {"1","true","ja","yes"}

def assess_margin_recovery_before_consensus(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    """Detect early margin recovery before analyst consensus and price fully re-rate."""
    r=row
    margin_now=_num(r.get("Marginal YoY förändring"))
    margin_prev=_num(r.get("Marginal YoY föregående kvartal"))
    earn_now=_num(r.get("Vinst YoY senaste kvartal"))
    earn_prev=_num(r.get("Vinst YoY föregående kvartal"))
    rev_acc=_num(r.get("Omsättning acceleration"))
    eps_rev=_num(r.get("EPS-estimat förändring"))
    rev_bal=_num(r.get("EPS-revisionsbalans"))
    bullish=_num(r.get("Konsensus bullish andel"))
    analysts=_num(r.get("Analytiker antal"))
    quality=_num(r.get("Kvalitet"))
    valuation=_num(r.get("Värdering"))
    m1=_num(r.get("1 mån"))
    m3=_num(r.get("3 mån"))
    dist=_num(r.get("Avstånd SMA200"))
    entry=str(r.get("Ingångsläge nivå") or "").lower()
    crowded=_yes(r.get("Crowded varning")) or _yes(r.get("Crowded stark varning"))

    supports=[]; warnings=[]
    margin_delta=np.nan
    if np.isfinite(margin_now) and np.isfinite(margin_prev):
        margin_delta=margin_now-margin_prev
        if margin_delta >= .015:
            supports.append(f"marginalutvecklingen förbättras tydligt ({margin_prev:+.1%} → {margin_now:+.1%})")
        if margin_prev < 0 <= margin_now:
            supports.append("marginalutvecklingen har vänt från negativ till positiv")
    if np.isfinite(earn_now) and np.isfinite(earn_prev) and earn_now > earn_prev:
        supports.append("vinsttillväxten börjar också förbättras")
    if np.isfinite(rev_acc) and rev_acc >= 0:
        supports.append("omsättningen ger inget tydligt bromsargument")
    if np.isfinite(quality) and quality >= 65:
        supports.append("bolagskvaliteten är hög")

    # "Before consensus" means estimates are not already aggressively positive.
    consensus_cautious = True
    if np.isfinite(eps_rev) and eps_rev > .04:
        consensus_cautious=False
        warnings.append("EPS-estimaten har redan skruvats upp tydligt")
    elif np.isfinite(eps_rev) and eps_rev <= .02:
        supports.append("EPS-estimaten är fortfarande försiktiga")

    if np.isfinite(rev_bal) and rev_bal > .40:
        consensus_cautious=False
        warnings.append("revisionsbalansen är redan starkt positiv")
    elif np.isfinite(rev_bal) and rev_bal <= .25:
        supports.append("revisionsbalansen är ännu inte bredt positiv")

    if np.isfinite(bullish) and np.isfinite(analysts) and analysts >= 5 and bullish >= .75:
        consensus_cautious=False
        warnings.append("bred analytikerkonsensus är redan tydligt positiv")
    if crowded:
        consensus_cautious=False
        warnings.append("förväntningsbilden är redan trång")

    price_caught_up = (
        entry in {"orange","red"}
        or (np.isfinite(m1) and m1 >= .18)
        or (np.isfinite(m3) and m3 >= .30)
        or (np.isfinite(dist) and dist >= .18)
    )
    if price_caught_up:
        warnings.append("kursen har redan börjat prisa in återhämtningen")
    if np.isfinite(valuation) and valuation < 45:
        warnings.append("värderingen är redan ansträngd")

    bad = (
        (np.isfinite(margin_delta) and margin_delta <= -.015)
        or (np.isfinite(margin_now) and margin_now <= -.05 and (not np.isfinite(margin_delta) or margin_delta <= 0))
        or (np.isfinite(quality) and quality < 55)
    )
    core=np.isfinite(margin_delta) and margin_delta >= .015

    if bad:
        tier=-1; label="⚠️ Ingen margin recovery – marginalbilden försämras"
    elif not core:
        tier=0; label="— Ingen tydlig marginalåterhämtning ännu"
    elif consensus_cautious and not price_caught_up and len(supports) >= 4:
        tier=3; label="💎 Margin recovery before consensus · stark tidig fyndkandidat"
    elif consensus_cautious and not price_caught_up:
        tier=2; label="🟢 Marginalåterhämtning före bred konsensus"
    else:
        tier=1; label="🟡 Marginalerna återhämtas – men marknaden har börjat hinna med"

    rank=float(max(tier,0)*100 + min(len(supports),7)*6 - min(len(warnings),5)*7)
    if tier < 0: rank=-100.0
    why="; ".join(supports[:5]) if supports else "ingen verifierad marginalåterhämtning mellan jämförbara kvartal"
    if warnings: why += ". Motargument: " + "; ".join(warnings[:4])
    return {
        "Margin recovery": label,
        "Margin recovery nivå": tier,
        "Margin recovery rangvärde": rank,
        "Margin recovery stöd": "; ".join(supports[:7]),
        "Margin recovery varningar": "; ".join(warnings[:6]),
        "Margin recovery förklaring": why,
    }

def add_margin_recovery_before_consensus(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_margin_recovery_before_consensus(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
