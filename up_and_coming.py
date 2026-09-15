from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else np.nan
    except (TypeError, ValueError):
        return np.nan


def assess_up_and_coming(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    """Find evidence-backed emerging companies without forecasting a great future."""
    cap = _num(row.get("Börsvärde BSEK"))
    revenue_growth = _num(row.get("Omsättningstillväxt"))
    earnings_growth = _num(row.get("Vinsttillväxt"))
    margin = _num(row.get("Vinstmarginal"))
    roe = _num(row.get("ROE"))
    fcf_yield = _num(row.get("FCF-yield"))
    debt = _num(row.get("Skuld/eget kapital"))
    quality = _num(row.get("Kvalitet"))
    coverage = _num(row.get("Datatäckning"))
    confidence = _num(row.get("Analysis Confidence nivå"))
    turnover = _num(row.get("Omsättning MSEK/dag"))
    avanza_catalog = bool(row.get("Avanza-universum", False))

    blockers: list[str] = []
    if not avanza_catalog: blockers.append("saknas i Borsifys Avanza-katalog")
    if not np.isfinite(cap): blockers.append("börsvärde saknas")
    elif cap <= 0: blockers.append("ogiltigt börsvärde")
    elif cap > 50: blockers.append("inte längre ett mindre bolag")
    if not np.isfinite(turnover): blockers.append("handelsaktivitet saknas")
    elif turnover < 0.10: blockers.append("för låg observerad handelsaktivitet")
    if str(row.get("Value Trap verdict") or "") == "VALUE_TRAP": blockers.append("trolig value trap")
    if str(row.get("Bolagsbedömning nivå") or "").lower() == "red": blockers.append("röd bolagsbedömning")
    if str(row.get("Ingångsläge nivå") or "").lower() == "red": blockers.append("kursen har redan gått för långt")
    if np.isfinite(confidence) and confidence <= 1: blockers.append("lågt analysförtroende")
    if np.isfinite(coverage) and coverage < 0.50: blockers.append("för låg datatäckning")
    if np.isfinite(debt) and debt > 250: blockers.append("mycket hög skuldsättning")

    families: list[str] = []
    growth_reasons = []
    if np.isfinite(revenue_growth) and revenue_growth >= 0.10: growth_reasons.append("omsättningstillväxt")
    if np.isfinite(earnings_growth) and earnings_growth >= 0.15: growth_reasons.append("vinsttillväxt")
    if growth_reasons: families.append("tillväxt")
    economics = []
    if np.isfinite(margin) and margin >= 0.05: economics.append("positiv marginal")
    if np.isfinite(fcf_yield) and fcf_yield > 0: economics.append("positivt FCF")
    if np.isfinite(roe) and roe >= 0.10: economics.append("rimlig kapitalavkastning")
    if economics: families.append("affärsekonomi")
    change = []
    if _num(row.get("KPI Inflection nivå")) >= 1: change.append("KPI-förbättring")
    if _num(row.get("Revision breadth nivå")) >= 1: change.append("positiva estimatrevideringar")
    if _num(row.get("Fundamental förändring antal")) >= 1: change.append("verifierad fundamental förändring")
    if change: families.append("förändring")
    resilience = []
    if np.isfinite(quality) and quality >= 55: resilience.append("god kvalitet")
    if not np.isfinite(debt) or debt <= 150: resilience.append("ingen tydlig skuldblockerare")
    if resilience: families.append("uthållighet")

    eligible = not blockers and "tillväxt" in families and len(families) >= 3
    if eligible and len(families) == 4 and len(growth_reasons) == 2 and len(economics) >= 2:
        label = "💎 Stark emerging-kandidat"
    elif eligible:
        label = "🟢 Up and coming-kandidat"
    elif not blockers and growth_reasons:
        label = "🟡 Lovande men otillräckligt bekräftad"
    else:
        label = "— Kvalificerar inte"
    reasons = growth_reasons + economics + change + resilience
    return {
        "Up and coming": label,
        "Up and coming godkänd": eligible,
        "Up and coming evidensfamiljer": len(families),
        "Up and coming stöd": "; ".join(reasons),
        "Up and coming blockerare": "; ".join(blockers),
        "Up and coming förklaring": (
            "Observerad kandidatbedömning: " + ("; ".join(reasons) if reasons else "för lite positiv evidens") + ". "
            + (("Blockerare: " + "; ".join(blockers) + ". ") if blockers else "")
            + "Katalogmedlemskap och marknadsdata är inte en garanti för att Avanza accepterar order just nu. "
            + "Detta är inte en prognos om att bolaget blir en framtida vinnare och påverkar inte Borsify Score."
        ),
    }


def add_up_and_coming(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    extra = pd.DataFrame([assess_up_and_coming(row) for _, row in out.iterrows()], index=out.index)
    return out.drop(columns=[c for c in extra.columns if c in out.columns], errors="ignore").join(extra)


def select_up_and_coming(frame: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    assessed = add_up_and_coming(frame)
    if assessed.empty:
        return assessed
    selected = assessed[assessed["Up and coming godkänd"]].copy()
    if selected.empty:
        return selected
    revenue = pd.to_numeric(selected.get("Omsättningstillväxt", pd.Series(np.nan, index=selected.index)), errors="coerce")
    earnings = pd.to_numeric(selected.get("Vinsttillväxt", pd.Series(np.nan, index=selected.index)), errors="coerce")
    selected["__growth"] = pd.concat([revenue, earnings], axis=1).max(axis=1).fillna(-1)
    selected["__score"] = pd.to_numeric(selected.get("Års Score", selected.get("Borsify Score")), errors="coerce").fillna(-1)
    return selected.sort_values(
        ["Up and coming evidensfamiljer", "__growth", "__score", "Ticker"],
        ascending=[False, False, False, True],
    ).drop(columns=["__growth", "__score"]).head(max(1, int(limit)))
