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


def assess_balance_sheet_optionality(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Find durable businesses with real financing/capital-allocation headroom.

    Optionality means capacity, not a forecast that management will make a good acquisition,
    buy back shares, or increase dividends. Strong labels require observable balance-sheet
    and cash-generation evidence; missing cash data is not interpreted as net cash.
    """
    r=row
    net_debt=_num(r.get("Kapitalallokering nettoskuld"))
    debt_trend=_num(r.get("Kapitalallokering skuldtrend"))
    debt_eq=_num(r.get("Skuld/eget kapital"))
    fcf_yield=_num(r.get("FCF-yield"))
    if not np.isfinite(fcf_yield):
        fcf_yield=_num(r.get("FCF yield"))
    buyback=_num(r.get("Kapitalallokering återköpsyield"))
    issuance=_num(r.get("Kapitalallokering emissionsyield"))
    dividend=_num(r.get("Kapitalallokering kontantutdelningsyield"))
    quality=_num(r.get("Kvalitet"))
    risk=_num(r.get("Risk"))
    invest=_num(r.get("INVEST Score"))
    valuation=_num(r.get("Värdering"))
    coverage=_num(r.get("Datatäckning"))
    market_cap=_num(r.get("Börsvärde"))

    supports=[]; warnings=[]
    net_cash=False
    low_net_debt=False
    if np.isfinite(net_debt):
        if net_debt <= 0:
            net_cash=True
            supports.append("balansräkningen visar nettokassa")
        elif np.isfinite(market_cap) and market_cap > 0 and net_debt/market_cap <= .15:
            low_net_debt=True
            supports.append("nettosed/skuld är låg relativt börsvärdet")
        else:
            warnings.append("observerad nettoskuld är inte låg")
    else:
        warnings.append("nettosed/skuld kan inte verifieras från aktuell balansdata")

    if np.isfinite(debt_eq):
        if debt_eq <= 50:
            supports.append("skuld/eget kapital är låg")
        elif debt_eq > 150:
            warnings.append("skuld/eget kapital är hög")

    if np.isfinite(debt_trend):
        if debt_trend <= -.10:
            supports.append("nettosed/skuldtrenden förbättras tydligt")
        elif debt_trend >= .20:
            warnings.append("nettosed/skuldtrenden försämras")

    if np.isfinite(fcf_yield):
        if fcf_yield >= .04:
            supports.append("stark fri-kassaflödesyield ger finansieringsutrymme")
        elif fcf_yield <= 0:
            warnings.append("fri-kassaflödesyield ger inget finansieringsstöd")

    if np.isfinite(quality) and quality >= 70:
        supports.append("bolagskvaliteten är hög")
    if np.isfinite(risk) and risk >= 60:
        supports.append("riskprofilen är robust")
    if np.isfinite(invest) and invest >= 65:
        supports.append("långsiktig INVEST-bedömning är stark")
    if np.isfinite(coverage) and coverage < .60:
        warnings.append("datatäckningen är för tunn för stark optionality-bedömning")

    # Capital allocation is evidence of use, not a requirement for latent capacity.
    if np.isfinite(buyback) and buyback >= .01:
        supports.append(f"observerade nettoåterköp motsvarar cirka {buyback:.1%} av börsvärdet")
    if np.isfinite(dividend) and dividend >= .015:
        supports.append("bolaget återför redan kapital via kontantutdelning")
    if np.isfinite(issuance) and issuance >= .03:
        warnings.append("betydande aktieemission motverkar ägarvänlig optionalitet")

    long_horizon=horizon in {"year","long","lifetime"}
    severe = (
        (np.isfinite(debt_eq) and debt_eq > 200)
        or (np.isfinite(debt_trend) and debt_trend >= .35)
        or (np.isfinite(fcf_yield) and fcf_yield < 0)
        or (np.isfinite(issuance) and issuance >= .05)
    )
    balance_verified=np.isfinite(net_debt)
    capacity = (
        (net_cash or low_net_debt or (np.isfinite(debt_eq) and debt_eq <= 50))
        and np.isfinite(fcf_yield) and fcf_yield > 0
        and (not np.isfinite(quality) or quality >= 60)
        and (not np.isfinite(risk) or risk >= 50)
    )

    if not long_horizon:
        tier=0; label="— Balance-sheet optionality används bara långsiktigt"
    elif severe:
        tier=-1; label="⚠️ Begränsad optionalitet – balans/kassaflöde ger motvind"
    elif not capacity:
        tier=0; label="— För lite verifierat finansiellt handlingsutrymme"
    elif balance_verified and net_cash and len(supports) >= 5 and (not np.isfinite(coverage) or coverage >= .65):
        tier=3; label="💎 Balance-sheet optionality · starkt finansiellt handlingsutrymme"
    elif balance_verified and len(supports) >= 4:
        tier=2; label="🟢 Stark balansräkning ger strategisk optionalitet"
    else:
        tier=1; label="🟡 Finansiellt handlingsutrymme finns – men nettokassa är inte verifierad"

    rank=float(max(tier,0)*100 + min(len(supports),8)*5 - min(len(warnings),5)*8)
    if tier < 0:
        rank=-100.0

    why="; ".join(supports[:6]) if supports else "inget tillräckligt verifierat finansiellt handlingsutrymme"
    why += ". Optionalitet betyder kapacitet, inte att Borsify antar att framtida förvärv, återköp eller utdelningar automatiskt skapar värde."
    if warnings:
        why += " Motargument: " + "; ".join(warnings[:3])

    return {
        "Balance-sheet optionality": label,
        "Balance-sheet optionality nivå": tier,
        "Balance-sheet optionality rangvärde": rank,
        "Balance-sheet optionality nettoskuld": net_debt,
        "Balance-sheet optionality nettokassa verifierad": bool(net_cash and balance_verified),
        "Balance-sheet optionality stöd": "; ".join(supports[:8]),
        "Balance-sheet optionality varningar": "; ".join(warnings[:6]),
        "Balance-sheet optionality förklaring": why,
    }


def add_balance_sheet_optionality(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_balance_sheet_optionality(r,horizon) for _,r in out.iterrows()], index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(extra)
