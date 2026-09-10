from __future__ import annotations

from typing import Any
import math
import numpy as np
import pandas as pd

MIN_MISSES_FOR_PATTERN = 3


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def classify_frozen_patterns(row: pd.Series | dict[str, Any]) -> list[str]:
    """Classify a frozen discovery snapshot. Never infer from future/current data."""
    q = _num(row.get("quality")); v = _num(row.get("valuation")); s = _num(row.get("setup"))
    r = _num(row.get("risk")); c = _num(row.get("coverage"))
    tags: list[str] = []
    if np.isfinite(q) and q >= 70 and np.isfinite(v) and v < 45:
        tags.append("Dyra kvalitetsbolag")
    if np.isfinite(q) and q < 55 and np.isfinite(s) and s >= 60:
        tags.append("Vändningscase")
    if np.isfinite(q) and q >= 70:
        tags.append("Hög kvalitet")
    if np.isfinite(v) and v < 45:
        tags.append("Svag värderingssignal")
    if np.isfinite(s) and s < 50:
        tags.append("Svagt marknadsläge")
    if np.isfinite(r) and r < 50:
        tags.append("Hög risk")
    if np.isfinite(c) and c < 0.65:
        tags.append("Låg datatäckning")
    return tags or ["Ingen tydlig fryst faktor"]


def build_miss_pattern_table(outcomes: pd.DataFrame, snapshots: pd.DataFrame, horizon: str | None = None,
                             min_misses: int = MIN_MISSES_FOR_PATTERN) -> pd.DataFrame:
    """Find patterns overrepresented among missed winners vs the evaluated cohort.

    Uses only fields frozen in the original snapshot plus later realized outcome labels.
    It is diagnostic only and returns no ranking/model score.
    """
    cols = ["pattern", "misses", "miss_share", "cohort_share", "overrepresentation", "median_return", "status"]
    if outcomes is None or outcomes.empty or snapshots is None or snapshots.empty:
        return pd.DataFrame(columns=cols)
    out = outcomes.copy()
    if horizon is not None and "horizon" in out.columns:
        out = out[out["horizon"].astype(str).eq(str(horizon))].copy()
    if out.empty or "snapshot_id" not in out.columns or "snapshot_id" not in snapshots.columns:
        return pd.DataFrame(columns=cols)
    snap_cols = [c for c in ["snapshot_id", "quality", "valuation", "setup", "risk", "coverage"] if c in snapshots.columns]
    snap = snapshots[snap_cols].drop_duplicates("snapshot_id", keep="last")
    frame = out.merge(snap, on="snapshot_id", how="left")
    frame["is_miss"] = pd.to_numeric(frame.get("missed_winner"), errors="coerce").fillna(0).eq(1)
    if not frame["is_miss"].any():
        return pd.DataFrame(columns=cols)
    rows = []
    all_tags = [classify_frozen_patterns(r) for _, r in frame.iterrows()]
    miss_n = int(frame["is_miss"].sum()); cohort_n = len(frame)
    patterns = sorted({tag for tags in all_tags for tag in tags})
    for pattern in patterns:
        has = np.array([pattern in tags for tags in all_tags], dtype=bool)
        miss_mask = frame["is_miss"].to_numpy(dtype=bool)
        misses = int((has & miss_mask).sum())
        miss_share = misses / miss_n if miss_n else np.nan
        cohort_share = int(has.sum()) / cohort_n if cohort_n else np.nan
        over = miss_share / cohort_share if cohort_share and np.isfinite(cohort_share) else np.nan
        returns = pd.to_numeric(frame.loc[has & miss_mask, "return_pct"], errors="coerce").dropna()
        med = float(returns.median()) if not returns.empty else np.nan
        status = "Återkommande missmönster" if misses >= int(min_misses) and np.isfinite(over) and over >= 1.25 else "För lite/ingen tydlig överrepresentation"
        rows.append({"pattern": pattern, "misses": misses, "miss_share": miss_share, "cohort_share": cohort_share,
                     "overrepresentation": over, "median_return": med, "status": status})
    result = pd.DataFrame(rows, columns=cols)
    if result.empty:
        return result
    return result.sort_values(["misses", "overrepresentation"], ascending=[False, False], na_position="last").reset_index(drop=True)


def miss_pattern_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": "Bygger historik", "text": "För få prospektiva missar för att identifiera återkommande mönster ännu.", "pattern": None}
    strong = table[table["status"].eq("Återkommande missmönster")]
    if strong.empty:
        return {"status": "Inget tydligt mönster", "text": "Det finns missade vinnare, men ännu inget fryst faktormönster som återkommer tillräckligt ofta och är tydligt överrepresenterat.", "pattern": None}
    top = strong.iloc[0]
    return {"status": "Mönster hittat", "pattern": str(top["pattern"]),
            "text": f"Borsify missar oproportionerligt ofta: {top['pattern']}. {int(top['misses'])} missade vinnare tillhör mönstret. Detta är diagnostik, inte en automatisk modelländring."}
