from __future__ import annotations
"""Compare observable expectation burden with improving business evidence.

This is not a reverse DCF and does not claim to recover the market's exact
forecast. It is an advisory, point-in-time classification and never ranks stocks.
"""

import math
from typing import Any

import numpy as np
import pandas as pd


def _n(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else np.nan
    except Exception:
        return np.nan


def assess_market_implied_expectations(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    valuation = _n(row.get("Värdering"))
    coverage = _n(row.get("Värdering täckning"))
    metric_count = _n(row.get("Värderingsmått antal"))
    forward_pe = _n(row.get("Forward P/E"))
    fcf_yield = _n(row.get("FCF-yield"))
    kpi = _n(row.get("KPI Inflection nivå"))
    revisions = _n(row.get("Revision breadth nivå"))
    change_families = _n(row.get("Förändringsbekräftelse positiva familjer antal"))
    confidence = _n(row.get("Analysis Confidence Score"))
    m1 = _n(row.get("1 mån"))
    relative_market = _n(row.get("Relativ marknad 3 mån"))
    relative_sector = _n(row.get("Relativ sektor 3 mån"))
    value_trap = str(row.get("Value Trap verdict") or "")

    support: list[str] = []
    warnings: list[str] = []
    evidence_count = int(sum([
        np.isfinite(valuation), np.isfinite(forward_pe), np.isfinite(fcf_yield)
    ]))
    valuation_reliable = (
        np.isfinite(valuation)
        and (not np.isfinite(coverage) or coverage >= .50)
        and (not np.isfinite(metric_count) or metric_count >= 2)
    )

    burden = "UNKNOWN"
    if valuation_reliable:
        if valuation >= 65:
            burden = "LOW"
            support.append("sektorjusterad värdering antyder relativt låg förväntningsbörda")
        elif valuation >= 42:
            burden = "MODERATE"
            support.append("sektorjusterad värdering antyder en måttlig förväntningsbörda")
        else:
            burden = "HIGH"
            warnings.append("värderingen antyder att marknaden redan kräver mycket")
    else:
        warnings.append("värderingsunderlaget är för tunt för att bedöma förväntningsbördan")

    # Absolute multiples are supporting context only; sector-aware valuation owns
    # the burden classification because business models differ materially.
    if np.isfinite(forward_pe):
        support.append(f"observerad Forward P/E {forward_pe:.1f}")
    if np.isfinite(fcf_yield):
        support.append(f"observerad FCF-yield {fcf_yield:.1%}")

    improvement = 0
    if np.isfinite(kpi) and kpi >= 2:
        improvement += 1
        support.append("verksamhets-KPI förbättras")
    if np.isfinite(revisions) and revisions >= 2:
        improvement += 1
        support.append("estimatrevideringarna breddas positivt")
    if np.isfinite(change_families) and change_families >= 2:
        improvement += 1
        support.append("minst två förändringsfamiljer bekräftar förbättring")

    muted = 0
    if np.isfinite(m1) and m1 <= .12:
        muted += 1
    if np.isfinite(relative_market) and relative_market <= .12:
        muted += 1
    if np.isfinite(relative_sector) and relative_sector <= .12:
        muted += 1
    if muted >= 2:
        support.append("kursen har ännu inte gjort en tydlig relativ re-rating")

    rerated = any([
        np.isfinite(m1) and m1 >= .25,
        np.isfinite(relative_market) and relative_market >= .25,
        np.isfinite(relative_sector) and relative_sector >= .25,
    ])
    if rerated:
        warnings.append("kursreaktionen antyder att högre förväntningar redan kan vara på väg in i priset")
    if value_trap in {"VALUE_TRAP", "TRAP_RISK"}:
        warnings.append("den låga värderingen kan vara fundamentalt motiverad")

    status = "UNQUANTIFIABLE"
    level = 0
    label = "❔ Marknadens förväntningsbörda kan inte bedömas"
    if burden == "LOW" and improvement >= 2 and muted >= 2 and not rerated and value_trap not in {"VALUE_TRAP", "TRAP_RISK"}:
        status = "LOW_EXPECTATIONS_BEING_BEATEN"
        level = 3
        label = "💎 Låga förväntningar börjar överträffas"
    elif burden in {"LOW", "MODERATE"} and improvement >= 1 and not rerated and value_trap not in {"VALUE_TRAP", "TRAP_RISK"}:
        status = "MANAGEABLE_EXPECTATIONS_IMPROVING"
        level = 2
        label = "🟢 Hanterbara förväntningar · förbättring syns"
    elif burden == "HIGH" or rerated:
        status = "EXPECTATIONS_DEMANDING"
        level = 1
        label = "🟠 Mycket kan redan krävas eller vara inprisat"
    elif burden in {"LOW", "MODERATE"}:
        status = "NO_IMPROVEMENT_CONFIRMATION"
        level = 1
        label = "🟡 Rimlig förväntningsbörda · förbättring ej bekräftad"

    if np.isfinite(confidence) and confidence < 45 and level > 1:
        status = "LOW_CONFIDENCE"
        level = 1
        label = "🟡 Möjligt förväntningsgap · svagt analysunderlag"
        warnings.append("lågt analysförtroende blockerar en stark bedömning")

    explanation = f"{label}. "
    if support:
        explanation += "Stöd: " + "; ".join(support[:5]) + ". "
    if warnings:
        explanation += "Motargument: " + "; ".join(warnings[:4]) + ". "
    explanation += "Detta är en grov jämförelse av observerad värderingsbörda och förändring, inte en reverse DCF eller en exakt prognos, och den påverkar inte rankingen."

    return {
        "Market-Implied Expectations": label,
        "Market-Implied Expectations status": status,
        "Market-Implied Expectations nivå": level,
        "Market-Implied Expectations burden": burden,
        "Market-Implied Expectations improvement families": improvement,
        "Market-Implied Expectations muted reactions": muted,
        "Market-Implied Expectations evidence count": evidence_count,
        "Market-Implied Expectations stöd": "; ".join(support),
        "Market-Implied Expectations varningar": "; ".join(warnings),
        "Market-Implied Expectations förklaring": explanation,
    }


def add_market_implied_expectations(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    extra = pd.DataFrame([assess_market_implied_expectations(row) for _, row in out.iterrows()], index=out.index)
    overlap = [column for column in extra.columns if column in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
