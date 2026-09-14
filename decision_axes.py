from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def assess_company_quality(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    """A deliberately simple, horizon-neutral company-quality label.

    This does not create a new score. It translates Borsify's existing Kvalitet and
    Risk fields into plain-language company quality, separate from entry timing.
    """
    quality = _num(row.get("Kvalitet"))
    risk = _num(row.get("Risk"))

    if not np.isfinite(quality):
        return {
            "Bolagsbedömning": "⚪ För lite data",
            "Bolagsbedömning nivå": "unknown",
            "Bolagsbedömning skäl": "Borsify saknar tillräckligt kvalitetsunderlag.",
        }

    # Risk is a quality-of-balance-sheet / robustness input in Borsify where higher is better.
    if quality >= 80 and (not np.isfinite(risk) or risk >= 60):
        label, level = "🟢 Mycket bra bolag", "green"
    elif quality >= 68 and (not np.isfinite(risk) or risk >= 50):
        label, level = "🟢 Bra bolag", "green"
    elif quality >= 55:
        label, level = "🟡 Okej bolag", "yellow"
    else:
        label, level = "🔴 Svagt bolag", "red"

    parts = [f"kvalitet {quality:.0f}/100"]
    if np.isfinite(risk):
        parts.append(f"riskrobusthet {risk:.0f}/100")
    return {
        "Bolagsbedömning": label,
        "Bolagsbedömning nivå": level,
        "Bolagsbedömning skäl": ", ".join(parts),
    }


def add_company_quality(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    rows = [assess_company_quality(r) for _, r in out.iterrows()]
    quality = pd.DataFrame(rows, index=out.index)
    overlap = [c for c in quality.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(quality)
