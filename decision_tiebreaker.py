from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


CLOSE_CALL_POINTS = 3.0


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else np.nan
    except Exception:
        return np.nan


def _sort_close_group(group: pd.DataFrame) -> pd.DataFrame:
    """Order genuinely close candidates using existing evidence only.

    This is intentionally a lexicographic tie-break, not another weighted score.
    Severe risk loses first. Then evidence completeness/consistency (Case Readiness)
    comes before relative strength, which is only confirmation. The original daily
    relevance and Borsify score remain later tie-breakers.
    """
    work = group.copy()
    work["__severe"] = work.get("Severe", pd.Series(False, index=work.index)).fillna(False).astype(bool)
    for col in ["Case Readiness", "Relativ styrka", "Dagens relevans", "Borsify Score", "Datatäckning"]:
        work[f"__{col}"] = pd.to_numeric(work.get(col, pd.Series(np.nan, index=work.index)), errors="coerce").fillna(-1e9)
    work = work.sort_values(
        ["__severe", "__Case Readiness", "__Relativ styrka", "__Dagens relevans", "__Borsify Score", "__Datatäckning"],
        ascending=[True, False, False, False, False, False],
        kind="stable",
    )
    return work.drop(columns=[c for c in work.columns if c.startswith("__")])


def rank_close_daily_candidates(df: pd.DataFrame, close_points: float = CLOSE_CALL_POINTS) -> pd.DataFrame:
    """Re-order only candidates whose daily relevance is genuinely close.

    The best daily relevance still defines each local group. A candidate more than
    ``close_points`` below that group's leader can never leapfrog it because of this
    tie-breaker. This keeps the incumbent model in control while making first place
    less dependent on tiny, false-precision score differences.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if "Dagens relevans" not in df.columns:
        return df.copy()

    base = df.sort_values(
        ["Dagens relevans", "Borsify Score", "Datatäckning"],
        ascending=[False, False, False],
        kind="stable",
    ).copy()

    ordered_parts: list[pd.DataFrame] = []
    pos = 0
    while pos < len(base):
        leader = _num(base.iloc[pos].get("Dagens relevans"))
        end = pos + 1
        if np.isfinite(leader):
            while end < len(base):
                value = _num(base.iloc[end].get("Dagens relevans"))
                if not np.isfinite(value) or leader - value > float(close_points):
                    break
                end += 1
        group = base.iloc[pos:end]
        ordered_parts.append(_sort_close_group(group) if len(group) > 1 else group.copy())
        pos = end

    return pd.concat(ordered_parts, axis=0)
