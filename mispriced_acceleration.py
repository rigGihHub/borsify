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

def assess_mispriced_acceleration(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    """Find improving operating/estimate velocity that price has not obviously outrun.

    This is a conservative ranking context layer. It requires at least two distinct
    improving evidence families and rejects cases where price/expectations already look
    stretched. Missing comparison history is neutral, never inferred.
    """
    r=row
    rev_acc=_num(r.get("Omsättning acceleration"))
    margin_now=_num(r.get("Marginal YoY förändring"))
    margin_prev=_num(r.get("Marginal YoY föregående kvartal"))
    fcf_now=_num(r.get("FCF YoY senaste kvartal"))
    fcf_prev=_num(r.get("FCF YoY föregående kvartal"))
    earn_now=_num(r.get("Vinst YoY senaste kvartal"))
    earn_prev=_num(r.get("Vinst YoY föregående kvartal"))
    eps_rev=_num(r.get("EPS-estimat förändring"))
    rev_bal=_num(r.get("EPS-revisionsbalans"))

    m1=_num(r.get("1 mån")); m3=_num(r.get("3 mån"))
    dist=_num(r.get("Avstånd SMA200")); valuation=_num(r.get("Värdering"))
    upside=_num(r.get("Riktkurs potential"))
    crowded=_yes(r.get("Crowded varning")) or _yes(r.get("Crowded stark varning"))
    entry_level=str(r.get("Ingångsläge nivå") or "").lower()
    negative_overreaction=int(_num(r.get("Negativ överreaktion nivå"))) if np.isfinite(_num(r.get("Negativ överreaktion nivå"))) else 0

    supports=[]; warnings=[]; families=0

    if np.isfinite(rev_acc) and rev_acc >= .03:
        families += 1; supports.append(f"försäljningstillväxten accelererar ({rev_acc:+.1%})")
    if np.isfinite(margin_now) and np.isfinite(margin_prev) and margin_now-margin_prev >= .01:
        families += 1; supports.append("marginalförbättringen accelererar")
    if np.isfinite(fcf_now) and np.isfinite(fcf_prev) and fcf_now-fcf_prev >= .10:
        families += 1; supports.append("kassaflödestillväxten accelererar")
    if np.isfinite(earn_now) and np.isfinite(earn_prev) and earn_now-earn_prev >= .08:
        families += 1; supports.append("vinsttillväxten accelererar")
    analyst_accel = (np.isfinite(eps_rev) and eps_rev >= .02) or (np.isfinite(rev_bal) and rev_bal >= .35)
    if analyst_accel:
        families += 1
        supports.append("analytikerestimaten/revisionsbalansen förbättras")

    negative_ops = 0
    if np.isfinite(rev_acc) and rev_acc <= -.05: negative_ops += 1
    if np.isfinite(margin_now) and np.isfinite(margin_prev) and margin_now-margin_prev <= -.015: negative_ops += 1
    if np.isfinite(fcf_now) and np.isfinite(fcf_prev) and fcf_now-fcf_prev <= -.15: negative_ops += 1
    if np.isfinite(earn_now) and np.isfinite(earn_prev) and earn_now-earn_prev <= -.12: negative_ops += 1

    price_ran=False
    if np.isfinite(m1) and m1 >= .22: price_ran=True; warnings.append("kursen har redan stigit kraftigt senaste månaden")
    if np.isfinite(m3) and m3 >= .40: price_ran=True; warnings.append("kursen har redan stigit kraftigt på tre månader")
    if np.isfinite(dist) and dist >= .20: price_ran=True; warnings.append("kursen ligger långt över 200-dagarstrenden")
    if entry_level in {"orange","red"}: price_ran=True
    if crowded: warnings.append("förväntningsbilden är redan trång")
    if np.isfinite(valuation) and valuation < 45: warnings.append("värderingen ser ansträngd ut")
    if np.isfinite(upside) and upside < .08: warnings.append("begränsad observerad riktkurspotential")
    if negative_ops >= 2: warnings.append("flera operativa jämförelser försämras")

    enough = families >= 2
    still_unpriced = (
        not price_ran and not crowded
        and (not np.isfinite(valuation) or valuation >= 50)
        and (not np.isfinite(upside) or upside >= .08)
    )

    if negative_ops >= 2:
        tier=-1; label="⚠️ Ingen acceleration – försämring dominerar"
    elif not enough:
        tier=0; label="— För lite verifierad acceleration"
    elif still_unpriced and families >= 3:
        tier=3; label="💎 Mispriced acceleration · stark fyndkandidat"
    elif still_unpriced:
        tier=2; label="🟢 Förbättringstakten före priset"
    elif families >= 2 and price_ran:
        tier=1; label="🟡 Acceleration finns – men kursen har hunnit före"
    else:
        tier=1; label="🟡 Acceleration finns – men felprissättning är inte tydlig"

    # Negative overreaction can reinforce, but never create, an acceleration case.
    bonus = 8 if tier >= 2 and negative_overreaction >= 2 else 0
    rank=float(max(tier,0)*100 + min(families,5)*6 + bonus - min(len(warnings),4)*5)
    if tier < 0: rank=-100.0

    text="; ".join(supports[:4]) if supports else "ingen verifierad acceleration mellan jämförbara perioder"
    if warnings: text += ". Motargument: " + "; ".join(warnings[:3])

    return {
        "Mispriced acceleration": label,
        "Mispriced acceleration nivå": tier,
        "Mispriced acceleration rangvärde": rank,
        "Mispriced acceleration familjer": families,
        "Mispriced acceleration stöd": "; ".join(supports[:5]),
        "Mispriced acceleration varningar": "; ".join(warnings[:5]),
        "Mispriced acceleration förklaring": text,
    }

def add_mispriced_acceleration(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_mispriced_acceleration(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
