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

def assess_revision_breadth(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    """Measure *current* analyst revision breadth without inventing prior-period breadth.

    A true breadth inflection requires historical breadth snapshots. Until those exist,
    this module detects breadth emergence and freezes the measurement prospectively.
    """
    analysts=_num(row.get("Analytiker antal"))
    revising=_num(row.get("Reviderande analytiker senaste period"))
    balance=_num(row.get("EPS-revisionsbalans"))
    eps_change=_num(row.get("EPS-estimat förändring"))
    bullish=_num(row.get("Konsensus bullish andel"))
    m1=_num(row.get("1 mån"))
    dist=_num(row.get("Avstånd SMA200"))
    crowded=_yes(row.get("Crowded varning")) or _yes(row.get("Crowded stark varning"))

    supports=[]; warnings=[]
    breadth=np.nan
    if np.isfinite(analysts) and analysts > 0 and np.isfinite(revising):
        breadth=max(0.0,min(1.0,revising/analysts))
        supports.append(f"{int(revising)} av {int(analysts)} analytiker reviderar ({breadth:.0%})")
    else:
        warnings.append("analytikerbredd kan inte beräknas")

    if np.isfinite(balance):
        if balance >= .20:
            supports.append(f"revisionsbalansen är positiv ({balance:+.0%})")
        elif balance <= -.20:
            warnings.append("revisionsbalansen är negativ")
    if np.isfinite(eps_change):
        if eps_change >= .01:
            supports.append(f"EPS-estimatet stiger ({eps_change:+.1%})")
        elif eps_change <= -.02:
            warnings.append("EPS-estimatet faller tydligt")

    already_crowded = crowded or (np.isfinite(bullish) and bullish >= .80)
    if already_crowded:
        warnings.append("konsensus ser redan crowded ut")
    price_ran = (np.isfinite(m1) and m1 >= .18) or (np.isfinite(dist) and dist >= .18)
    if price_ran:
        warnings.append("kursen har redan börjat prisa in förbättringen")

    bad=(np.isfinite(balance) and balance <= -.20) or (np.isfinite(eps_change) and eps_change <= -.02)
    enough=np.isfinite(breadth) and analysts >= 4 and breadth >= .25 and (not np.isfinite(balance) or balance > 0)

    if bad:
        tier=-1; label="⚠️ Revision breadth negativ – sänkningar dominerar"
    elif not np.isfinite(breadth):
        tier=0; label="— Revision breadth kan inte verifieras"
    elif not enough:
        tier=0; label="— För smal revisionsbredd"
    elif breadth >= .50 and not already_crowded and not price_ran and len(supports) >= 2:
        tier=3; label="💎 Revision breadth emerging · stark tidig kandidat"
    elif not already_crowded and not price_ran:
        tier=2; label="🟢 Allt fler analytiker reviderar positivt"
    else:
        tier=1; label="🟡 Positiv revisionsbredd – men marknaden har börjat hinna med"

    rank=float(max(tier,0)*100 + (breadth*40 if np.isfinite(breadth) else 0) + min(len(supports),4)*5 - min(len(warnings),4)*7)
    if tier < 0: rank=-100.0
    why="; ".join(supports[:4]) if supports else "ingen tillräckligt bred positiv revisionsaktivitet"
    why += ". Detta mäter aktuell bredd, inte historisk breddacceleration; tidigare period saknas konsekvent i äldre PIT-snapshots."
    if warnings: why += " Motargument: " + "; ".join(warnings[:3])
    return {
        "Revision breadth": label,
        "Revision breadth nivå": tier,
        "Revision breadth rangvärde": rank,
        "Revision breadth andel": breadth,
        "Revision breadth stöd": "; ".join(supports[:5]),
        "Revision breadth varningar": "; ".join(warnings[:5]),
        "Revision breadth förklaring": why,
    }

def add_revision_breadth(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_revision_breadth(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
