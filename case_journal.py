from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

COMPONENTS = [
    ("valuation", "Värdering"),
    ("quality", "Kvalitet"),
    ("setup", "Marknadsläge"),
    ("income", "Utdelning"),
    ("risk", "Risk"),
]


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def prepare_history(history: pd.DataFrame) -> pd.DataFrame:
    """Normalize score history from SQLite/Supabase into one chronological frame."""
    cols = ["score", "valuation", "quality", "setup", "income", "risk", "coverage", "captured_date"]
    if history is None or history.empty:
        return pd.DataFrame(columns=cols)
    out = history.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = np.nan if col != "captured_date" else None
    out["captured_date"] = pd.to_datetime(out["captured_date"], errors="coerce")
    for col in cols[:-1]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["score", "captured_date"]).sort_values("captured_date")
    out = out.drop_duplicates(subset=["captured_date"], keep="last").reset_index(drop=True)
    return out[cols]


def assess_case_change(
    history: pd.DataFrame,
    current: dict[str, Any],
    added_at: Any = None,
) -> dict[str, Any]:
    """Explain how Borsify's measured picture has changed since the first stored snapshot.

    This deliberately describes changes in Borsify's data, not whether the investment itself
    objectively became better or worse.
    """
    hist = prepare_history(history)
    current_score = _num(current.get("score"))
    if hist.empty or not np.isfinite(current_score):
        return {
            "status": "Historiken byggs upp",
            "tone": "neutral",
            "score_delta": np.nan,
            "first_score": np.nan,
            "current_score": current_score,
            "days_followed": None,
            "changes": ["Det finns ännu inte tillräckligt med sparad historik för att jämföra utvecklingen över tid."],
        }

    first = hist.iloc[0]
    first_score = _num(first.get("score"))
    delta = current_score - first_score if np.isfinite(first_score) else np.nan
    if np.isfinite(delta) and delta >= 5:
        status, tone = "Borsifys mätbild har stärkts", "positive"
    elif np.isfinite(delta) and delta <= -5:
        status, tone = "Borsifys mätbild har försvagats", "negative"
    else:
        status, tone = "Borsifys mätbild är ungefär oförändrad", "neutral"

    changes: list[str] = []
    for key, label in COMPONENTS:
        start = _num(first.get(key))
        now = _num(current.get(key))
        if not (np.isfinite(start) and np.isfinite(now)):
            continue
        component_delta = now - start
        if component_delta >= 8:
            changes.append(f"{label} har förbättrats tydligt i modellen ({start:.0f} → {now:.0f}).")
        elif component_delta <= -8:
            changes.append(f"{label} har försvagats tydligt i modellen ({start:.0f} → {now:.0f}).")
    if not changes:
        changes.append("Ingen av de stora delpoängen har förändrats kraftigt sedan den första sparade analysen.")

    start_date = _date(added_at) or _date(first.get("captured_date"))
    days_followed = max(0, (date.today() - start_date).days) if start_date else None
    return {
        "status": status,
        "tone": tone,
        "score_delta": delta,
        "first_score": first_score,
        "current_score": current_score,
        "first_date": _date(first.get("captured_date")),
        "days_followed": days_followed,
        "changes": changes[:4],
    }


def journal_table(history: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    hist = prepare_history(history)
    if hist.empty:
        return pd.DataFrame(columns=["Datum", "Borsify Score", "Förändring från start", "Kvalitet", "Värdering", "Risk"])
    first_score = float(hist.iloc[0]["score"])
    out = hist.tail(max(1, int(limit))).copy()
    result = pd.DataFrame({
        "Datum": out["captured_date"].dt.strftime("%Y-%m-%d"),
        "Borsify Score": out["score"].round(1),
        "Förändring från start": (out["score"] - first_score).round(1),
        "Kvalitet": out["quality"].round(0),
        "Värdering": out["valuation"].round(0),
        "Risk": out["risk"].round(0),
    })
    return result.reset_index(drop=True)
