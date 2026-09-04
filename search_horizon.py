from __future__ import annotations

import pandas as pd


SEARCH_HORIZONS = [
    "Alla tidshorisonter",
    "1–2 dagar",
    "1 vecka–3 månader",
    "1–5 år",
    "Mycket lång sikt",
]


def apply_search_horizon(df: pd.DataFrame, horizon_label: str, score_builder) -> pd.DataFrame:
    """Prioritize a selected time horizon using existing horizon scores."""
    if df is None or df.empty or horizon_label == "Alla tidshorisonter":
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = score_builder(df)
    score_col = {
        "1–2 dagar": "Daytrade Score",
        "1 vecka–3 månader": "Mellan Score",
        "1–5 år": "Lång Score",
        "Mycket lång sikt": "Livstid Score",
    }.get(horizon_label)
    if not score_col or score_col not in out.columns:
        return out

    horizon_score = pd.to_numeric(out[score_col], errors="coerce").fillna(0)
    if "Match Score" in out.columns:
        intent_score = pd.to_numeric(out["Match Score"], errors="coerce").fillna(horizon_score)
    else:
        intent_score = horizon_score
    out["Sökpoäng"] = (0.65 * horizon_score + 0.35 * intent_score).round(1)
    return out.sort_values(["Sökpoäng", "Datatäckning"], ascending=[False, False])
