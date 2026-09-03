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


def _find_row(frame: pd.DataFrame | None, names: list[str]) -> pd.Series:
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:
        return pd.Series(dtype=float)
    for name in names:
        if name in frame.index:
            s=pd.to_numeric(frame.loc[name],errors="coerce").dropna()
            if not s.empty:
                try:
                    s.index=pd.to_datetime(s.index)
                    return s.sort_index(ascending=False)
                except Exception:
                    return s
    return pd.Series(dtype=float)


def _ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    if a.empty or b.empty:
        return pd.Series(dtype=float)
    common=a.index.intersection(b.index)
    if len(common)==0:
        return pd.Series(dtype=float)
    av=pd.to_numeric(a.loc[common],errors="coerce")
    bv=pd.to_numeric(b.loc[common],errors="coerce")
    out=av/bv.replace(0,np.nan)
    return out.replace([np.inf,-np.inf],np.nan).dropna().sort_index(ascending=False)


def _latest(s: pd.Series) -> float:
    return _num(s.iloc[0]) if not s.empty else np.nan


def _median_recent(s: pd.Series, n: int=4) -> float:
    if s.empty:
        return np.nan
    vals=pd.to_numeric(s.iloc[:n],errors="coerce").dropna()
    return float(vals.median()) if len(vals) else np.nan


def build_earnings_quality_metrics(
    income: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
) -> dict[str,Any]:
    """Measure whether accounting earnings are supported by cash generation.

    The engine uses only reported statement rows. Missing rows remain missing.
    Ratios are descriptive diagnostics, not forecasts.
    """
    net_income=_find_row(income,["Net Income","Net Income Common Stockholders"])
    revenue=_find_row(income,["Total Revenue","Operating Revenue"])
    ocf=_find_row(cashflow,["Operating Cash Flow","Total Cash From Operating Activities"])
    fcf=_find_row(cashflow,["Free Cash Flow"])
    if fcf.empty:
        capex=_find_row(cashflow,["Capital Expenditure","Capital Expenditures"])
        if not ocf.empty and not capex.empty:
            common=ocf.index.intersection(capex.index)
            cap=capex.loc[common]
            fcf=(ocf.loc[common] + cap.where(cap<=0,-cap)).dropna().sort_index(ascending=False)

    change_wc=_find_row(cashflow,["Change In Working Capital","Change To Working Capital"])
    receivables=_find_row(balance,["Accounts Receivable","Receivables","Net Receivables"])
    inventory=_find_row(balance,["Inventory","Inventories"])

    ocf_to_income=_ratio(ocf,net_income)
    fcf_to_income=_ratio(fcf,net_income)
    receivables_to_sales=_ratio(receivables,revenue)
    inventory_to_sales=_ratio(inventory,revenue)

    wc_to_ocf=_ratio(change_wc.abs(),ocf.abs())
    latest_wc=_latest(change_wc)

    def trend(series: pd.Series) -> float:
        if len(series)<2:
            return np.nan
        return _num(series.iloc[0])-_num(series.iloc[-1])

    return {
        "Kassaflöde/vinst senaste":_latest(ocf_to_income),
        "Kassaflöde/vinst median":_median_recent(ocf_to_income),
        "FCF/vinst senaste":_latest(fcf_to_income),
        "FCF/vinst median":_median_recent(fcf_to_income),
        "Rörelsekapital senaste förändring":latest_wc,
        "Rörelsekapitalpåverkan/OCF":_latest(wc_to_ocf),
        "Kundfordringar/omsättning":_latest(receivables_to_sales),
        "Kundfordringar/omsättning trend":trend(receivables_to_sales),
        "Lager/omsättning":_latest(inventory_to_sales),
        "Lager/omsättning trend":trend(inventory_to_sales),
        "Earnings Quality år":int(max(len(ocf_to_income.iloc[:4]),len(fcf_to_income.iloc[:4]))),
    }


def assess_earnings_quality(metrics: dict[str,Any]) -> dict[str,Any]:
    positives=[]
    warnings=[]
    hard=[]

    ocf_latest=_num(metrics.get("Kassaflöde/vinst senaste"))
    ocf_med=_num(metrics.get("Kassaflöde/vinst median"))
    fcf_latest=_num(metrics.get("FCF/vinst senaste"))
    fcf_med=_num(metrics.get("FCF/vinst median"))
    wc_impact=_num(metrics.get("Rörelsekapitalpåverkan/OCF"))
    recv_trend=_num(metrics.get("Kundfordringar/omsättning trend"))
    inv_trend=_num(metrics.get("Lager/omsättning trend"))
    years=int(_num(metrics.get("Earnings Quality år")) if np.isfinite(_num(metrics.get("Earnings Quality år"))) else 0)

    evidence=sum(np.isfinite(x) for x in [ocf_latest,ocf_med,fcf_latest,fcf_med,wc_impact,recv_trend,inv_trend])

    score=50.0
    if np.isfinite(ocf_med):
        if ocf_med >= 1.0:
            score += 15; positives.append("redovisad vinst stöds väl av pengar från den löpande verksamheten")
        elif ocf_med < .65:
            score -= 20; warnings.append("den redovisade vinsten har omvandlats svagt till kassaflöde")
    if np.isfinite(fcf_med):
        if fcf_med >= .75:
            score += 12; positives.append("en stor del av vinsten har även blivit fritt kassaflöde")
        elif fcf_med < .35:
            score -= 16; warnings.append("lite av vinsten har blivit fritt kassaflöde efter investeringar")

    # A single recent collapse matters even when the multi-year median looks good.
    if np.isfinite(ocf_latest) and ocf_latest < .45:
        score -= 12; warnings.append("senaste året visar ovanligt svag omvandling från vinst till kassaflöde")
    if np.isfinite(fcf_latest) and fcf_latest < 0:
        score -= 18; warnings.append("senaste fria kassaflödet är negativt trots redovisad vinst")
        hard.append("negativt fritt kassaflöde trots redovisad vinst")

    if np.isfinite(wc_impact) and wc_impact > .45:
        score -= 8; warnings.append("förändringar i rörelsekapitalet har haft stor påverkan på kassaflödet")

    if np.isfinite(recv_trend):
        if recv_trend > .05:
            score -= 9; warnings.append("kundfordringar har vuxit snabbare än omsättningen")
        elif recv_trend < -.03:
            score += 4; positives.append("kundfordringar har inte dragit iväg relativt omsättningen")

    if np.isfinite(inv_trend):
        if inv_trend > .05:
            score -= 7; warnings.append("lagret har vuxit snabbare än omsättningen")
        elif inv_trend < -.03:
            score += 3; positives.append("lagret har minskat relativt omsättningen")

    score=float(np.clip(score,0,100))

    if evidence < 2 or years < 2:
        status="FÖR LITE UNDERLAG"
    elif hard or score < 35:
        status="SVAG VINSTKVALITET"
    elif score < 55:
        status="KRÄVER KONTROLL"
    elif score >= 72:
        status="STARK VINSTKVALITET"
    else:
        status="NORMAL VINSTKVALITET"

    return {
        **metrics,
        "Vinstkvalitet":round(score,1),
        "Vinstkvalitet status":status,
        "Vinstkvalitet underlag":int(evidence),
        "Vinstkvalitet styrkor":"; ".join(positives[:3]) if positives else "inga tydliga positiva kassaflödessignaler",
        "Vinstkvalitet varningar":"; ".join(warnings[:3]) if warnings else "inga tydliga varningssignaler i tillgängliga data",
        "Vinstkvalitet hårt stopp":"; ".join(hard),
    }


def apply_earnings_quality_gate(case: dict[str,Any]) -> dict[str,Any]:
    out=dict(case)
    status=str(out.get("Vinstkvalitet status",""))
    gate=str(out.get("Djupkontroll",""))
    if status=="SVAG VINSTKVALITET" and gate in {"Klarar djupkontroll","Neutral djupkontroll"}:
        out["Djupkontroll"]="Kräver extra kontroll"
        out["Vinstkvalitet gate note"]="Djupcaset sänktes eftersom redovisad vinst inte stöds tillräckligt väl av kassaflödet."
    else:
        out["Vinstkvalitet gate note"]=""
    return out
