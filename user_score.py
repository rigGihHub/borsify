from __future__ import annotations

import math
from typing import Any
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def user_score(row: Any) -> float:
    """Score safe to show as Borsify's final user-facing rating.

    Keeps the raw model score intact for diagnostics, but specialist engines get
    the final word when they have a stricter cap.
    """
    raw = _num(row.get("Borsify Score"))
    if not math.isfinite(raw):
        return float("nan")
    final = raw

    if bool(row.get("Investmentbolag")):
        cap = _num(row.get("Investmentbolag rankningstak"))
        if math.isfinite(cap):
            final = min(final, cap)

    return max(0.0, min(100.0, final))


def user_score_explanation(row: Any) -> str:
    raw = _num(row.get("Borsify Score"))
    final = user_score(row)
    if bool(row.get("Investmentbolag")) and math.isfinite(raw) and math.isfinite(final) and final < raw:
        return (
            "Grundanalysen gav ett högre betyg, men Borsify sänker betyget efter "
            "kontrollen av investmentbolagets pris jämfört med värdet på innehaven."
        )
    return "Det här är Borsifys slutliga betyg efter de kontroller som gäller för aktien."


def add_user_scores(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    out["Borsify slutbetyg"] = [user_score(row) for _, row in out.iterrows()]\n    # Presentation-safe alias. User-facing cards that still read Borsify Score now\n    # receive the specialist-aware value; the untouched raw score is preserved separately.\n    if "Borsify Score" in out.columns:\n        out["Borsify grundbetyg"] = out["Borsify Score"]\n        out["Borsify Score"] = out["Borsify slutbetyg"]
    out["Borsify slutbetyg förklaring"] = [user_score_explanation(row) for _, row in out.iterrows()]
    return out
