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

def assess_cash_conversion_inflection(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    """Detect when FCF growth improves materially faster than earnings growth."""
    fcf_now=_num(row.get("FCF YoY senaste kvartal"))
    fcf_prev=_num(row.get("FCF YoY föregående kvartal"))
    earn_now=_num(row.get("Vinst YoY senaste kvartal"))
    earn_prev=_num(row.get("Vinst YoY föregående kvartal"))
    fcf_yield=_num(row.get("FCF yield"))
    quality=_num(row.get("Kvalitet"))
    risk=_num(row.get("Risk"))
    coverage=_num(row.get("Datatäckning"))
    m1=_num(row.get("1 mån"))
    dist=_num(row.get("Avstånd SMA200"))
    entry=str(row.get("Ingångsläge nivå") or "").lower()

    supports=[]; warnings=[]
    if np.isfinite(fcf_now) and np.isfinite(fcf_prev):
        fcf_acc=fcf_now-fcf_prev
        if fcf_acc >= .15:
            supports.append(f"FCF-tillväxten accelererar kraftigt ({fcf_prev:+.1%} → {fcf_now:+.1%})")
    else:
        fcf_acc=np.nan

    if np.isfinite(earn_now) and np.isfinite(earn_prev):
        earn_acc=earn_now-earn_prev
    else:
        earn_acc=np.nan

    spread=np.nan
    if np.isfinite(fcf_now) and np.isfinite(earn_now):
        spread=fcf_now-earn_now
        if spread >= .15:
            supports.append("kassaflödestillväxten ligger tydligt före vinsttillväxten")

    if np.isfinite(fcf_yield) and fcf_yield >= .04:
        supports.append("FCF-yielden ger faktisk kassaflödesstyrka")
    if np.isfinite(quality) and quality >= 65:
        supports.append("bolagskvaliteten är hög")

    if np.isfinite(fcf_now) and fcf_now < -.15:
        warnings.append("fritt kassaflöde försämras tydligt")
    if np.isfinite(fcf_acc) and fcf_acc < -.10:
        warnings.append("FCF-tillväxten bromsar")
    if np.isfinite(quality) and quality < 55:
        warnings.append("bolagskvaliteten är för svag")
    if np.isfinite(coverage) and coverage < .55:
        warnings.append("datatäckningen är tunn")
    if entry in {"orange","red"} or (np.isfinite(m1) and m1 >= .20) or (np.isfinite(dist) and dist >= .20):
        warnings.append("kursen har redan blivit ansträngd")

    core = np.isfinite(fcf_acc) and fcf_acc >= .15 and (not np.isfinite(spread) or spread >= .10)
    bad = any(x in warnings for x in ["fritt kassaflöde försämras tydligt","FCF-tillväxten bromsar","bolagskvaliteten är för svag"])

    if bad:
        tier=-1; label="⚠️ Ingen cash-conversion-inflection – kassaflödet försämras"
    elif not core:
        tier=0; label="— Ingen tydlig cash-conversion-inflection"
    elif len(supports) >= 3 and "kursen har redan blivit ansträngd" not in warnings:
        tier=3; label="💎 Cash conversion inflection · stark fyndkandidat"
    elif "kursen har redan blivit ansträngd" not in warnings:
        tier=2; label="🟢 Kassaflödet förbättras före vinsten"
    else:
        tier=1; label="🟡 Cash conversion förbättras – men kursen har hunnit före"

    rank=float(max(tier,0)*100 + min(len(supports),5)*7 - min(len(warnings),4)*7)
    if tier < 0: rank=-100.0
    why="; ".join(supports[:4]) if supports else "ingen verifierad FCF-acceleration relativt vinst"
    if warnings: why += ". Motargument: " + "; ".join(warnings[:3])
    return {
        "Cash conversion inflection": label,
        "Cash conversion inflection nivå": tier,
        "Cash conversion inflection rangvärde": rank,
        "Cash conversion inflection stöd": "; ".join(supports[:5]),
        "Cash conversion inflection varningar": "; ".join(warnings[:5]),
        "Cash conversion inflection förklaring": why,
    }

def add_cash_conversion_inflection(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_cash_conversion_inflection(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
