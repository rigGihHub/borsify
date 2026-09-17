from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _number(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _is_false(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    return str(value or "").strip().lower() in {"false", "0", "nej", "no"}


def first_choice_blockers(row: pd.Series | dict[str, Any]) -> list[str]:
    """Final presentation firewall; safeguards here never add investment score."""
    reasons: list[str] = []
    if str(row.get("Value Trap verdict") or "") == "VALUE_TRAP":
        reasons.append("trolig value trap")
    if str(row.get("Ingångsläge nivå") or "").lower() == "red":
        reasons.append("rött köpläge")
    if str(row.get("Bolagsbedömning nivå") or "").lower() == "red":
        reasons.append("röd bolagsbedömning")
    confidence_level = _number(row.get("Analysis Confidence nivå"))
    if math.isfinite(confidence_level) and confidence_level <= 1:
        reasons.append("lågt analysförtroende")

    # Respect decisions already made by specialist quality/readiness engines.
    if "Case Readiness godkänd" in row and _is_false(row.get("Case Readiness godkänd")):
        reasons.append("caset är inte tillräckligt underbyggt")
    if "Köpfilter godkänd" in row and _is_false(row.get("Köpfilter godkänd")):
        reasons.append("klarar inte köpfiltrets hårda krav")

    # Investment companies must not bypass their NAV/look-through specialist check.
    if bool(row.get("Investmentbolag")):
        cap = _number(row.get("Investmentbolag rankningstak"))
        headline = _number(row.get("Borsify Score"))
        direct = str(row.get("Investmentbolag direktval") or "")
        if math.isfinite(cap) and math.isfinite(headline) and headline > cap:
            reasons.append(f"investmentbolagskontroll begränsar caset till {cap:.0f}")
        if direct in {"Innehaven direkt kan vara bättre", "Otillräcklig data"}:
            reasons.append("investmentbolaget saknar tydlig paketfördel")

    return list(dict.fromkeys(reasons))


def add_first_choice_gate(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    reasons = [first_choice_blockers(row) for _, row in out.iterrows()]
    out["Förstaval blockerare"] = ["; ".join(items) for items in reasons]
    out["Förstaval godkänd"] = [not items for items in reasons]
    return out
