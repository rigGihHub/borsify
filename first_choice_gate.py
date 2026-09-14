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


def first_choice_blockers(row: pd.Series | dict[str, Any]) -> list[str]:
    """Hard presentation gates; these never add investment score."""
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
    return reasons


def add_first_choice_gate(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    reasons = [first_choice_blockers(row) for _, row in out.iterrows()]
    out["Förstaval blockerare"] = ["; ".join(items) for items in reasons]
    out["Förstaval godkänd"] = [not items for items in reasons]
    return out
