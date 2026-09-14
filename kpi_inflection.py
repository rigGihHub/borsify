from __future__ import annotations
"""Sector-aware KPI inflection detection using only observed structured KPI changes."""
import math
from typing import Any
import numpy as np
import pandas as pd

def _n(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def assess_kpi_inflection(row:pd.Series|dict[str,Any])->dict[str,Any]:
    profile=str(row.get("Business profile") or "")
    rev=_n(row.get("KPI Omsättning QoQ")); fcf=_n(row.get("KPI FCF QoQ"))
    inv=_n(row.get("KPI Lager QoQ")); gm=_n(row.get("KPI Bruttomarginal")); om=_n(row.get("KPI Rörelsemarginal"))
    observed=str(row.get("KPI-specifika observerade") or "")
    missing=str(row.get("KPI-specifika saknas") or "")
    supports=[]; warnings=[]

    if math.isfinite(rev):
        if rev>=.08:supports.append(f"omsättningen accelererar {rev:+.1%} QoQ")
        elif rev<=-.08:warnings.append(f"omsättningen faller {rev:+.1%} QoQ")
    if math.isfinite(fcf):
        if fcf>=.15:supports.append(f"FCF förbättras {fcf:+.1%} QoQ")
        elif fcf<=-.20:warnings.append(f"FCF försämras {fcf:+.1%} QoQ")
    if profile=="Retail/konsument" and math.isfinite(inv) and math.isfinite(rev):
        # Inventory rising much faster than sales is a warning; inventory restraint
        # alongside positive sales is supportive. No claim about LFL is made.
        if inv-rev>=.12:warnings.append("lagret växer klart snabbare än omsättningen")
        elif rev>0 and inv<=rev:supports.append("lagerutvecklingen är disciplinerad relativt försäljningen")
    if math.isfinite(gm) and gm>=.40 and profile=="Mjukvara/tech":
        supports.append("observerad bruttomarginal är hög")
    if math.isfinite(om) and om<0:
        warnings.append("rörelsemarginalen är negativ")

    # A leading-sector inflection can only be claimed if a sector-specific leading KPI
    # was actually observed. Generic financial acceleration is labelled separately.
    leading_terms=("orderingång","orderbok","NRR","ARR","like-for-like","CET1","kreditförlust","produktion")
    leading_observed=any(x.lower() in observed.lower() for x in leading_terms)
    if leading_observed and len(supports)>=1 and not warnings:
        level=3; label="💎 Bransch-KPI inflection · ledande mått bekräftar"
    elif len(supports)>=2 and len(warnings)==0:
        level=2; label="🟢 Verksamhets-KPI förbättras"
    elif supports and warnings:
        level=1; label="🟡 Blandad KPI-inflection"
    elif warnings and not supports:
        level=-1; label="⚠️ KPI-bilden försämras"
    else:
        level=0; label="— Ingen verifierad KPI-inflection"

    confidence=min(100,20*sum(math.isfinite(x) for x in [rev,fcf,inv,gm,om])+15*int(bool(observed)))
    if missing: confidence=max(0,confidence-10)
    why=("; ".join(supports) if supports else "ingen tydlig positiv förändring i observerade KPI:er")
    if warnings:why+=". Motargument: "+"; ".join(warnings)
    if missing:why+=". Saknade ledande KPI:er: "+missing
    return {
        "KPI Inflection":label,"KPI Inflection nivå":level,"KPI Inflection confidence":confidence,
        "KPI Inflection stöd":"; ".join(supports),"KPI Inflection varningar":"; ".join(warnings),
        "KPI Inflection ledande KPI observerad":leading_observed,"KPI Inflection förklaring":why,
    }

def add_kpi_inflection(df:pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); extra=pd.DataFrame([assess_kpi_inflection(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra if c in out.columns]
    if overlap:out=out.drop(columns=overlap)
    return out.join(extra)
