from __future__ import annotations

from typing import Any
import math
import numpy as np
import pandas as pd

from horizon_rankings import add_horizon_scores


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else np.nan
    except Exception:
        return np.nan


def _ranked_indices(df: pd.DataFrame, column: str) -> list[Any]:
    if column not in df.columns:
        return []
    work = df.copy()
    work["__lens_value"] = pd.to_numeric(work[column], errors="coerce")
    work["__coverage"] = pd.to_numeric(work.get("Datatäckning"), errors="coerce").fillna(-1)
    work = work[work["__lens_value"].notna()]
    if work.empty:
        return []
    return work.sort_values(["__lens_value", "__coverage"], ascending=[False, False]).index.tolist()


def select_deep_finalist_pool(df: pd.DataFrame, pool_size: int = 6) -> pd.DataFrame:
    """Choose a small, diverse deep-analysis pool without creating a new score.

    The old flow only took the highest INVEST scores. This selector deliberately
    preserves the strongest INVEST names while reserving room for candidates that
    are unusually strong through a different existing lens (quality, durable
    lifetime profile, reversal/turnaround, or valuation). Deep analysis remains the
    evidence gate; selection into this pool is not a buy recommendation.
    """
    if df is None or df.empty or pool_size <= 0:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    horizon_cols = {"Daytrade Score", "Mellan Score", "Lång Score", "Livstid Score"}
    if horizon_cols.issubset(df.columns):
        work = df.copy()
    else:
        # Search-horizon filtering may already have added some of these columns.
        # Drop partial overlaps before rebuilding to avoid duplicate-column joins.
        work = add_horizon_scores(df.drop(columns=[c for c in horizon_cols if c in df.columns]))
    selected: list[Any] = []
    reasons: dict[Any, str] = {}
    reason_keys: dict[Any, str] = {}

    def take(column: str, reason: str, reason_key: str, count: int = 1, minimum: float | None = None) -> None:
        if len(selected) >= pool_size:
            return
        taken = 0
        for idx in _ranked_indices(work, column):
            if idx in selected:
                continue
            if minimum is not None and _num(work.at[idx, column]) < minimum:
                continue
            selected.append(idx)
            reasons[idx] = reason
            reason_keys[idx] = reason_key
            taken += 1
            if taken >= count or len(selected) >= pool_size:
                break

    # Preserve the incumbent model's strongest convictions.
    take("INVEST Score", "Hög INVEST-bedömning", "invest", count=min(2, pool_size))

    # Then deliberately widen the doorway to deep analysis. Thresholds stop a weak
    # candidate from getting a slot merely because it is the least-bad name in a lens.
    take("Kvalitet", "Ovanligt hög bolagskvalitet", "quality", minimum=65)
    take("Livstid Score", "Stark profil för mycket lång ägarhorisont", "lifetime", minimum=65)
    take("REVERSAL Score", "Möjligt vändningscase som behöver djupkontroll", "reversal", minimum=55)
    take("Värdering", "Ovanligt attraktiv värdering", "valuation", minimum=65)

    # Fill any unused slots with the broad existing long-horizon model, then INVEST.
    take("Lång Score", "Stark flerårsprofil", "long", count=pool_size)
    take("INVEST Score", "Hög INVEST-bedömning", "invest", count=pool_size)

    result = work.loc[selected[:pool_size]].copy()
    result["Djupurval"] = [reasons.get(idx, "Stark samlad profil") for idx in result.index]
    result["Djupurval Nyckel"] = [reason_keys.get(idx, "other") for idx in result.index]

    # Freeze which existing lenses were genuinely strong at selection time. This is
    # audit metadata, not a new score, and can later be linked to realised outcomes.
    lens_rules = [
        ("invest", "INVEST", "INVEST Score", 65),
        ("quality", "Kvalitet", "Kvalitet", 65),
        ("lifetime", "Mycket lång sikt", "Livstid Score", 65),
        ("reversal", "Vändning", "REVERSAL Score", 55),
        ("valuation", "Värdering", "Värdering", 65),
        ("long", "Flerårig profil", "Lång Score", 65),
    ]
    lens_keys = []
    lens_labels = []
    for _, row in result.iterrows():
        keys, labels = [], []
        for key, label, column, minimum in lens_rules:
            value = _num(row.get(column))
            if math.isfinite(value) and value >= minimum:
                keys.append(key)
                labels.append(label)
        lens_keys.append(keys)
        lens_labels.append(labels)
    result["Djupurval Linser"] = lens_keys
    result["Djupurval Linser text"] = [", ".join(x) if x else "Ingen stark extralins" for x in lens_labels]
    return result
