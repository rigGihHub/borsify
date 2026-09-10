from __future__ import annotations

"""Discovery Engine 2.0.

Creates a diversified doorway into expensive deep analysis without inventing a new
mega-score. Existing horizon/lens scores decide which candidates get represented;
subsequent deep-analysis gates still decide whether a case survives.
"""

import math
from typing import Any

import numpy as np
import pandas as pd

from horizon_rankings import add_horizon_scores
from fundamental_discovery import FUNDAMENTAL_LENSES, add_fundamental_discovery, select_fundamental_candidates
from fundamental_change_radar import select_change_radar_candidates
from underfollowed_discovery import add_underfollowed_discovery, select_underfollowed_candidates


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


LENSES: tuple[tuple[str, str, int, float | None], ...] = (
    ("Köp nu", "Mellan Score", 5, 55.0),
    ("Upp till ett år", "Års Score", 5, 58.0),
    ("Livstid", "Livstid Score", 5, 62.0),
    ("Kvalitet", "Kvalitet", 4, 65.0),
    ("Värdering", "Värdering", 3, 65.0),
    ("Vändning", "REVERSAL Score", 2, 55.0),
)


def _ensure_horizon_scores(df: pd.DataFrame) -> pd.DataFrame:
    needed = {"Mellan Score", "Års Score", "Livstid Score"}
    if needed.issubset(df.columns):
        return df.copy()
    overlap = [c for c in ["Daytrade Score", "Mellan Score", "Års Score", "Lång Score", "Livstid Score"] if c in df.columns]
    return add_horizon_scores(df.drop(columns=overlap, errors="ignore"))


def build_discovery_pool(df: pd.DataFrame, max_candidates: int = 24) -> pd.DataFrame:
    """Select a deterministic, multi-lens candidate pool for deeper analysis.

    No aggregate Discovery Score is created. A candidate enters because it is strong
    in at least one already-existing lens. This prevents the deep-analysis budget from
    being consumed only by the same kind of high-INVEST/momentum name.
    """
    if df is None or df.empty or max_candidates <= 0:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    work = add_underfollowed_discovery(add_fundamental_discovery(_ensure_horizon_scores(df)))
    selected: list[Any] = []
    seen: set[Any] = set()
    reasons: dict[Any, list[str]] = {}

    def consider(idx: Any, label: str) -> None:
        reasons.setdefault(idx, [])
        if label not in reasons[idx]:
            reasons[idx].append(label)
        if idx not in seen and len(selected) < max_candidates:
            seen.add(idx)
            selected.append(idx)

    # Fundamental Change Radar: before static lenses, reserve a few doorways for
    # companies whose broad point-in-time fundamentals have *just improved* versus
    # their latest older frozen scan. No history => no radar advantage.
    for idx, label in select_change_radar_candidates(work, quota=min(4, max_candidates)):
        consider(idx, label)

    # Underfollowed Discovery: low analyst coverage is only context. A slot is
    # reserved only when a Nordic company also has verified PIT fundamental improvement.
    for idx, label in select_underfollowed_candidates(work, quota=min(3, max_candidates)):
        consider(idx, label)

    # Fundamental Discovery 2.0: reserve a small part of the deep-analysis budget
    # for profitable growth/cash-generation patterns that can be missed by the
    # incumbent aggregate ordering. These are transparent boolean rules, not a score.
    for idx, label in select_fundamental_candidates(work, quota_per_lens=2, max_candidates=min(6, max_candidates)):
        consider(idx, label)

    # Reserve doorway capacity for genuinely different investment questions.
    for label, column, quota, minimum in LENSES:
        if column not in work.columns or len(selected) >= max_candidates:
            continue
        ranked = work.copy()
        ranked["__lens"] = pd.to_numeric(ranked[column], errors="coerce")
        ranked = ranked[ranked["__lens"].notna()]
        if minimum is not None:
            ranked = ranked[ranked["__lens"] >= minimum]
        if ranked.empty:
            continue
        ticker_sort = ranked.get("Ticker", pd.Series("", index=ranked.index)).astype(str)
        ranked = ranked.assign(__ticker=ticker_sort).sort_values(["__lens", "__ticker"], ascending=[False, True])
        taken = 0
        for idx in ranked.index:
            before = len(selected)
            consider(idx, label)
            if len(selected) > before:
                taken += 1
            # A candidate already selected by another lens still receives the extra
            # reason but does not consume this lens' quota.
            if taken >= quota or len(selected) >= max_candidates:
                break

    # Fill any unused capacity using the incumbent Borsify ordering. This preserves
    # continuity while the reserved lens slots increase diversity.
    fill_columns = [c for c in ["Borsify Score", "Datatäckning"] if c in work.columns]
    if len(selected) < max_candidates:
        fill = work.copy()
        if fill_columns:
            fill = fill.sort_values(fill_columns, ascending=[False] * len(fill_columns))
        for idx in fill.index:
            before = len(selected)
            consider(idx, "Samlad Borsify-bedömning")
            if len(selected) >= max_candidates:
                break

    result = work.loc[selected].copy()

    # Add all qualifying lenses for auditability, even if they did not create the
    # candidate's initial slot. These are labels only, never a ranking score.
    for idx, row in result.iterrows():
        for label, column, _, minimum in LENSES:
            value = _num(row.get(column))
            if math.isfinite(value) and (minimum is None or value >= minimum):
                if label not in reasons.setdefault(idx, []):
                    reasons[idx].append(label)

    result["Upptäcktslinser"] = [", ".join(reasons.get(idx, [])) for idx in result.index]
    result["Upptäcktslins antal"] = [len(reasons.get(idx, [])) for idx in result.index]
    return result


def discovery_coverage_summary(full_df: pd.DataFrame, pool: pd.DataFrame) -> dict[str, Any]:
    """Compact audit summary for hidden diagnostics/UI."""
    if full_df is None:
        full_df = pd.DataFrame()
    if pool is None:
        pool = pd.DataFrame()
    countries = 0
    if not pool.empty and "Land" in pool.columns:
        countries = int(pool["Land"].dropna().astype(str).nunique())
    lens_counts: dict[str, int] = {}
    if not pool.empty and "Upptäcktslinser" in pool.columns:
        for label in ["Fundamental förändring", "Underfollowed förbättring", *(x[0] for x in LENSES), *FUNDAMENTAL_LENSES]:
            lens_counts[label] = int(pool["Upptäcktslinser"].astype(str).str.contains(label, regex=False).sum())
    return {
        "universe": int(len(full_df)),
        "pool": int(len(pool)),
        "countries": countries,
        "lens_counts": lens_counts,
        "fraction": float(len(pool) / len(full_df)) if len(full_df) else np.nan,
    }
