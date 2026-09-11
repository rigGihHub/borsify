from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from research_dossier_robustness import (
    CHECK_PENDING,
    _positive_classifier,
    _sample_for,
    _snapshot,
)
from literature_signal_validation import SIGNALS

MIN_MATCHED_GROUP = 4
MIN_MATCHED_STRATA = 2
MIN_TOTAL_MATCHED = 16
MEANINGFUL_INCREMENT = 0.03


def _other_signal_names(target: str) -> list[str]:
    names = ["News Underreaction", "Expectation Gap"] + [s.name for s in SIGNALS]
    return [n for n in names if n != target and _positive_classifier(n) is not None]


def _background_signature(snapshot: dict[str, Any], target: str) -> tuple[str, ...]:
    """Exact frozen signature of other positive research signals.

    Exact signatures are intentionally conservative. They reduce the chance that a target
    merely receives credit for appearing alongside another already-positive hypothesis.
    Missing/neutral states are not imputed as positive.
    """
    active: list[str] = []
    for name in _other_signal_names(target):
        fn = _positive_classifier(name)
        if fn is not None and bool(fn(snapshot)):
            active.append(name)
    return tuple(sorted(active))


def incremental_value(
    name: str,
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: tuple[str, ...] = ("1m", "3m", "6m"),
) -> dict[str, Any]:
    """Test whether a research hypothesis adds outcome separation after matching on peers.

    For each horizon, favorable target cases are compared with adverse/control target cases
    only inside the same exact frozen signature of all *other* positive research signals.
    This is a matched association diagnostic, not causal proof and not a production weight.
    """
    horizon_results: list[dict[str, Any]] = []
    for horizon in horizons:
        sample, state_col = _sample_for(name, recommendations, outcomes, horizon)
        if sample is None or sample.empty or not state_col or "snapshot_json" not in sample.columns:
            continue
        work = sample.copy()
        work["_target_state"] = pd.to_numeric(work[state_col], errors="coerce")
        work = work[work["_target_state"].isin({-1, 1})].copy()
        if work.empty:
            continue
        metric = "excess_return_pct" if "excess_return_pct" in work.columns and pd.to_numeric(work["excess_return_pct"], errors="coerce").notna().all() else "return_pct"
        work["_metric"] = pd.to_numeric(work[metric], errors="coerce")
        work = work.dropna(subset=["_metric"])
        work["_background"] = work["snapshot_json"].map(lambda raw: _background_signature(_snapshot(raw), name))

        strata: list[dict[str, Any]] = []
        for signature, group in work.groupby("_background", sort=False):
            good = group.loc[group["_target_state"].eq(1), "_metric"].dropna()
            control = group.loc[group["_target_state"].eq(-1), "_metric"].dropna()
            if len(good) < MIN_MATCHED_GROUP or len(control) < MIN_MATCHED_GROUP:
                continue
            gap = float(good.median() - control.median())
            strata.append({
                "signature": signature,
                "good": int(len(good)),
                "control": int(len(control)),
                "gap": gap,
            })

        matched = sum(s["good"] + s["control"] for s in strata)
        if len(strata) < MIN_MATCHED_STRATA or matched < MIN_TOTAL_MATCHED:
            horizon_results.append({"horizon": horizon, "strata": len(strata), "matched": matched, "gap": np.nan})
            continue

        # Equal weight by matched background stratum prevents one large context from dominating.
        gaps = [s["gap"] for s in strata if math.isfinite(s["gap"])]
        gap = float(np.median(gaps)) if gaps else np.nan
        horizon_results.append({"horizon": horizon, "strata": len(strata), "matched": matched, "gap": gap})

    mature = [r for r in horizon_results if r["strata"] >= MIN_MATCHED_STRATA and r["matched"] >= MIN_TOTAL_MATCHED and math.isfinite(r["gap"])]
    if not mature:
        best_strata = max([r["strata"] for r in horizon_results], default=0)
        best_matched = max([r["matched"] for r in horizon_results], default=0)
        return {
            "status": CHECK_PENDING,
            "mature_horizons": 0,
            "matched_cases": best_matched,
            "matched_strata": best_strata,
            "median_increment": np.nan,
            "text": (
                f"För få exakt matchade case. Bästa horisonten har {best_strata} mogna bakgrundsstrata och {best_matched} case; "
                f"minst {MIN_MATCHED_STRATA} strata, {MIN_MATCHED_GROUP}+{MIN_MATCHED_GROUP} case per stratum och {MIN_TOTAL_MATCHED} totalt krävs."
            ),
        }

    positive = sum(r["gap"] >= MEANINGFUL_INCREMENT for r in mature)
    negative = sum(r["gap"] <= -MEANINGFUL_INCREMENT for r in mature)
    med = float(np.median([r["gap"] for r in mature]))
    total = len(mature)
    matched = max(r["matched"] for r in mature)
    strata = max(r["strata"] for r in mature)

    if positive == total:
        status = "Tydligt inkrementellt stöd"
        text = f"Target-signalen skiljer ut bättre utfall även inom samma övriga signalbakgrund i {total} mogen horisont(er). Median av matchade stratumgap är {med:+.1%}."
    elif negative == total:
        status = "Inget inkrementellt värde"
        text = f"Target-signalen går åt fel håll efter matchning mot samma övriga signalbakgrund i {total} mogen horisont(er). Median av stratumgap är {med:+.1%}."
    elif positive and negative:
        status = "Inkrementellt värde är instabilt"
        text = f"Det matchade mervärdet byter riktning mellan mogna horisonter. Median av stratumgap är {med:+.1%}; ingen unik effekt bör antas."
    else:
        status = "Inget tydligt inkrementellt värde"
        text = f"Matchade jämförelser ger inget tillräckligt stort stabilt mervärde. Median av stratumgap är {med:+.1%}."

    return {
        "status": status,
        "mature_horizons": total,
        "matched_cases": matched,
        "matched_strata": strata,
        "median_increment": med,
        "text": text + " Testet är associativt och ändrar aldrig produktionen automatiskt.",
    }


def apply_incremental_value(dossiers: pd.DataFrame, recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if dossiers is None or dossiers.empty:
        return dossiers.copy() if isinstance(dossiers, pd.DataFrame) else pd.DataFrame()
    out = dossiers.copy()
    if "Incrementellt värde" not in out.columns:
        out["Incrementellt värde"] = CHECK_PENDING
    for idx, row in out.iterrows():
        name = str(row.get("Hypotes", ""))
        result = incremental_value(name, recommendations, outcomes)
        out.at[idx, "Incrementellt värde"] = result["status"]
        blockers = [b.strip() for b in str(row.get("Blockerare", "")).split(",") if b.strip()]
        if result["status"] != CHECK_PENDING:
            blockers = [b for b in blockers if b != "inkrementellt värde"]
        out.at[idx, "Blockerare"] = ", ".join(blockers)
        current = str(row.get("Nästa beslut", ""))
        out.at[idx, "Nästa beslut"] = current + f" Inkrementellt värde: {result['text']}"
    return out
