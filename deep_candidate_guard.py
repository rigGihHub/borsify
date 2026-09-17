from __future__ import annotations

import math
from typing import Any


def _num(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else math.nan
    except (TypeError, ValueError):
        return math.nan


def deep_candidate_blockers(row: Any) -> list[str]:
    """Return already-known reasons not to spend a deep-analysis slot on a candidate."""
    reasons: list[str] = []
    if str(row.get("Universe QC") or "") == "EXKLUDERA":
        reasons.append("otillräcklig marknadsdatakvalitet")
    coverage = _num(row.get("Datatäckning"))
    if math.isfinite(coverage) and coverage < .40:
        reasons.append("för lite bolagsdata")
    confidence = _num(row.get("Analysis Confidence nivå"))
    if math.isfinite(confidence) and confidence <= 1:
        reasons.append("lågt analysförtroende")
    if str(row.get("Value Trap verdict") or "") == "VALUE_TRAP":
        reasons.append("trolig value trap")
    if bool(row.get("Investmentbolag")):
        cap = _num(row.get("Investmentbolag rankningstak"))
        score = _num(row.get("Borsify Score"))
        direct = str(row.get("Investmentbolag direktval") or "")
        if direct in {"Innehaven direkt kan vara bättre", "Otillräcklig data"}:
            reasons.append("investmentbolaget saknar tydlig paketfördel")
        if math.isfinite(cap) and math.isfinite(score) and score > cap:
            reasons.append("investmentbolagets specialisttak underskrids inte")
    return reasons


def deep_candidate_eligible(row: Any) -> bool:
    return not deep_candidate_blockers(row)
