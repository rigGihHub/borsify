from __future__ import annotations

from collections.abc import Iterable
from typing import Any
import math

import pandas as pd

from finalist_selection import select_deep_finalist_pool

DEFAULT_POOL_SIZES = (4, 6, 8, 10)


def _ticker_set(frame: pd.DataFrame) -> set[str]:
    if frame is None or frame.empty or "Ticker" not in frame.columns:
        return set()
    return {str(x) for x in frame["Ticker"].dropna().astype(str) if str(x).strip()}


def evaluate_finalist_pool_coverage(
    shallow_candidates: pd.DataFrame,
    deep_reference_ranked: pd.DataFrame,
    pool_sizes: Iterable[int] = DEFAULT_POOL_SIZES,
    target_limit: int = 5,
    reference_size: int | None = None,
) -> pd.DataFrame:
    """Compare cheaper finalist-pool sizes against one already deep-checked reference run.

    ``deep_reference_ranked`` must be ordered by the same post-deep evidence gate used by
    Borsify. The function performs *no* network work: a reference pool is deep-checked once,
    then 4/6/8/10 candidate selectors are compared against the strongest cases found in that
    reference. This avoids fetching the same statements four separate times.

    Coverage is a diagnostic, not proof of future return and not a reason to auto-change the
    production pool after one run.
    """
    columns = [
        "pool_size", "selected", "target_cases", "target_hits", "target_coverage",
        "missed_targets", "extra_deep_calls_vs_6", "reference_size",
    ]
    if shallow_candidates is None or shallow_candidates.empty or deep_reference_ranked is None or deep_reference_ranked.empty:
        return pd.DataFrame(columns=columns)
    if "Ticker" not in shallow_candidates.columns or "Ticker" not in deep_reference_ranked.columns:
        return pd.DataFrame(columns=columns)

    ref_size = int(reference_size or len(deep_reference_ranked))
    ref_size = max(0, min(ref_size, len(deep_reference_ranked)))
    reference = deep_reference_ranked.head(ref_size)
    target_n = max(0, min(int(target_limit), len(reference)))
    target_order = [str(x) for x in reference.head(target_n)["Ticker"].dropna().astype(str)]
    target_set = set(target_order)

    rows: list[dict[str, Any]] = []
    seen_sizes: set[int] = set()
    for raw_size in pool_sizes:
        try:
            size = int(raw_size)
        except Exception:
            continue
        if size <= 0 or size in seen_sizes:
            continue
        seen_sizes.add(size)
        selected = select_deep_finalist_pool(shallow_candidates, pool_size=min(size, len(shallow_candidates)))
        selected_set = _ticker_set(selected)
        hits = [ticker for ticker in target_order if ticker in selected_set]
        missed = [ticker for ticker in target_order if ticker not in selected_set]
        denom = len(target_set)
        coverage = len(hits) / denom if denom else math.nan
        rows.append({
            "pool_size": size,
            "selected": len(selected_set),
            "target_cases": denom,
            "target_hits": len(hits),
            "target_coverage": coverage,
            "missed_targets": missed,
            "extra_deep_calls_vs_6": max(0, size - 6),
            "reference_size": ref_size,
        })
    return pd.DataFrame(rows, columns=columns).sort_values("pool_size").reset_index(drop=True)


def aggregate_finalist_coverage(
    runs: pd.DataFrame,
    min_runs: int = 5,
    required_mean: float = 0.98,
    required_floor: float = 0.95,
) -> pd.DataFrame:
    """Aggregate independent reference runs and mark sizes safe enough to consider.

    The thresholds mirror Borsify's conservative staged-scan philosophy: several separate
    runs are required, average retention must be very high, and no run may be weak. This
    function only labels evidence; it never mutates the production pool size.
    """
    columns = [
        "pool_size", "runs", "mean_coverage", "min_coverage", "max_coverage",
        "mean_extra_calls_vs_6", "enough_runs", "passes_retention_gate",
    ]
    if runs is None or runs.empty or not {"pool_size", "target_coverage"}.issubset(runs.columns):
        return pd.DataFrame(columns=columns)

    work = runs.copy()
    work["pool_size"] = pd.to_numeric(work["pool_size"], errors="coerce")
    work["target_coverage"] = pd.to_numeric(work["target_coverage"], errors="coerce")
    if "extra_deep_calls_vs_6" not in work.columns:
        work["extra_deep_calls_vs_6"] = (work["pool_size"] - 6).clip(lower=0)
    work["extra_deep_calls_vs_6"] = pd.to_numeric(work["extra_deep_calls_vs_6"], errors="coerce")
    work = work.dropna(subset=["pool_size", "target_coverage"])
    if work.empty:
        return pd.DataFrame(columns=columns)

    grouped = work.groupby("pool_size", as_index=False).agg(
        runs=("target_coverage", "count"),
        mean_coverage=("target_coverage", "mean"),
        min_coverage=("target_coverage", "min"),
        max_coverage=("target_coverage", "max"),
        mean_extra_calls_vs_6=("extra_deep_calls_vs_6", "mean"),
    )
    grouped["pool_size"] = grouped["pool_size"].astype(int)
    grouped["enough_runs"] = grouped["runs"] >= int(min_runs)
    grouped["passes_retention_gate"] = (
        grouped["enough_runs"]
        & (grouped["mean_coverage"] >= float(required_mean))
        & (grouped["min_coverage"] >= float(required_floor))
    )
    return grouped[columns].sort_values("pool_size").reset_index(drop=True)


def finalist_pool_recommendation(aggregate: pd.DataFrame, current_pool_size: int = 6) -> dict[str, Any]:
    """Return a conservative human-readable recommendation from aggregated evidence."""
    if aggregate is None or aggregate.empty:
        return {
            "recommended_pool_size": int(current_pool_size),
            "status": "collect_more_runs",
            "reason": "Det finns ännu inte tillräckligt med valideringskörningar för att ändra finalistpoolen.",
        }

    valid = aggregate[aggregate.get("passes_retention_gate", False).astype(bool)].copy()
    if valid.empty:
        return {
            "recommended_pool_size": int(current_pool_size),
            "status": "keep_current",
            "reason": "Ingen testad poolstorlek har ännu klarat Borsifys konservativa täckningskrav i flera separata körningar.",
        }

    # Smallest passing pool wins: equal coverage with fewer deep calls is preferable.
    chosen = int(valid.sort_values("pool_size").iloc[0]["pool_size"])
    if chosen == int(current_pool_size):
        status = "keep_current"
        reason = f"Nuvarande finalistpool på {chosen} har tillräckligt stark och stabil täckning i valideringen."
    elif chosen < int(current_pool_size):
        status = "consider_smaller"
        reason = f"En mindre pool på {chosen} har klarat täckningskraven och kan minska deep-anrop utan tydlig täckningsförlust."
    else:
        status = "consider_larger"
        reason = f"Pool {chosen} är den minsta testade storleken som klarat täckningskraven; nuvarande {current_pool_size} verkar missa för många starka referenscase."
    return {"recommended_pool_size": chosen, "status": status, "reason": reason}
