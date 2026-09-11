from __future__ import annotations

import json
import math
from typing import Any, Callable

import numpy as np
import pandas as pd

from expectation_gap_validation import eligible_sample as expectation_gap_sample
from news_underreaction_validation import eligible_sample as news_underreaction_sample
from literature_signal_validation import SIGNALS, prepare_signal_sample

CHECK_PENDING = "Ej verifierad"
MIN_REGIME_GROUP = 4
MIN_MATURE_REGIMES = 2
MIN_OVERLAP_CASES = 10


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _regime(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("Marknadsläge") or "").strip()


def _yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "ja"}


def _sample_for(name: str, recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> tuple[pd.DataFrame, str] | tuple[None, None]:
    if name == "News Underreaction":
        sample = news_underreaction_sample(recommendations, outcomes, horizon)
        if sample is not None and not sample.empty:
            sample = sample.copy()
            sample["_robust_state"] = sample["_cohort"].map({"Underreaktion": 1, "Tydligare direkt reaktion": -1})
        return sample, "_robust_state"
    if name == "Expectation Gap":
        sample = expectation_gap_sample(recommendations, outcomes, horizon)
        if sample is not None and not sample.empty:
            sample = sample.copy()
            sample["_robust_state"] = sample["_cohort"].map({"Förbättring före förväntningarna": 1, "Bekräftad förändring utan tydligt gap": -1})
        return sample, "_robust_state"
    spec = next((s for s in SIGNALS if s.name == name), None)
    if spec is None:
        return None, None
    sample = prepare_signal_sample(recommendations, outcomes, horizon, spec)
    return sample, "_signal_state"


def regime_robustness(name: str, recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizons: tuple[str, ...] = ("1m", "3m", "6m")) -> dict[str, Any]:
    """Test whether a hypothesis keeps its direction in multiple frozen market regimes.

    The check is deliberately conservative: a regime counts only when both favorable and
    adverse/control states have enough independent observations. It is descriptive and never
    changes production policy.
    """
    best: list[dict[str, Any]] = []
    for horizon in horizons:
        sample, state_col = _sample_for(name, recommendations, outcomes, horizon)
        if sample is None or sample.empty or not state_col:
            continue
        work = sample.copy()
        if "snapshot_json" not in work.columns:
            continue
        work["_regime"] = work["snapshot_json"].map(lambda raw: _regime(_snapshot(raw)))
        work = work[work["_regime"].ne("")].copy()
        if work.empty:
            continue
        metric = "excess_return_pct" if "excess_return_pct" in work.columns and pd.to_numeric(work["excess_return_pct"], errors="coerce").notna().all() else "return_pct"
        rows: list[dict[str, Any]] = []
        for regime, group in work.groupby("_regime", sort=True):
            positive = pd.to_numeric(group.loc[group[state_col].eq(1), metric], errors="coerce").dropna()
            negative = pd.to_numeric(group.loc[group[state_col].eq(-1), metric], errors="coerce").dropna()
            if len(positive) < MIN_REGIME_GROUP or len(negative) < MIN_REGIME_GROUP:
                continue
            gap = float(positive.median() - negative.median())
            rows.append({"regime": regime, "gap": gap, "positive": len(positive), "negative": len(negative)})
        if len(rows) > len(best):
            best = rows
    if len(best) < MIN_MATURE_REGIMES:
        return {"status": CHECK_PENDING, "mature_regimes": len(best), "text": "Minst två marknadslägen med både signal- och jämförelsecase krävs."}
    positive = sum(r["gap"] > 0 for r in best)
    negative = sum(r["gap"] < 0 for r in best)
    total = len(best)
    if positive and negative:
        status = "Regimberoende"
        text = f"Riktningen skiljer sig mellan marknadslägen ({positive} positiva, {negative} negativa av {total})."
    elif positive == total:
        status = "Stöd i flera regimer"
        text = f"Hypotesen håller samma positiva riktning i {total} mogna marknadslägen. Det är robusthetsstöd, inte kausalitetsbevis."
    elif negative == total:
        status = "Ifrågasatt i flera regimer"
        text = f"Hypotesen går åt fel håll i samtliga {total} mogna marknadslägen och bör granskas kritiskt."
    else:
        status = "Ingen tydlig regimslutsats"
        text = f"{total} mogna marknadslägen finns men riktningen är inte tillräckligt tydlig."
    return {"status": status, "mature_regimes": total, "text": text}


def _positive_classifier(name: str) -> Callable[[dict[str, Any]], bool] | None:
    if name == "News Underreaction":
        def f(s: dict[str, Any]) -> bool:
            direction = str(s.get("News Surprise Primary Direction") or "").lower()
            try:
                strength = float(s.get("News Surprise Strength"))
            except Exception:
                strength = math.nan
            return direction == "positive" and math.isfinite(strength) and strength >= 3 and str(s.get("News Surprise Source Quality") or "") == "Stark källa" and _yes(s.get("News Surprise Underreaction"))
        return f
    if name == "Expectation Gap":
        return lambda s: _yes(s.get("Expectation Gap kandidat"))
    spec = next((s for s in SIGNALS if s.name == name), None)
    if spec is not None:
        return lambda s, _spec=spec: _spec.classifier(s) == 1
    return None


def signal_overlap(name: str, recommendations: pd.DataFrame) -> dict[str, Any]:
    """Measure how often a positive target signal co-occurs with another positive research signal.

    This is a uniqueness diagnostic, not a causal or incremental-alpha test. Frozen ledger
    snapshots are used exactly as stored; missing states are never reconstructed.
    """
    target = _positive_classifier(name)
    if target is None or recommendations is None or recommendations.empty or "snapshot_json" not in recommendations.columns:
        return {"status": CHECK_PENDING, "cases": 0, "max_overlap": np.nan, "partner": "—", "text": "Ingen mätbar fryst signaldefinition finns."}
    specs: list[tuple[str, Callable[[dict[str, Any]], bool]]] = []
    for candidate in ["News Underreaction", "Expectation Gap"] + [s.name for s in SIGNALS]:
        if candidate == name:
            continue
        fn = _positive_classifier(candidate)
        if fn is not None:
            specs.append((candidate, fn))
    work = recommendations.copy()
    # Avoid counting repeated horizon rows of the same frozen decision multiple times.
    dedupe_cols = [c for c in ["symbol", "captured_date", "snapshot_json"] if c in work.columns]
    if dedupe_cols:
        work = work.drop_duplicates(subset=dedupe_cols, keep="first")
    snaps = work["snapshot_json"].map(_snapshot)
    mask = snaps.map(target).astype(bool)
    target_snaps = snaps[mask]
    n = int(len(target_snaps))
    if n < MIN_OVERLAP_CASES:
        return {"status": CHECK_PENDING, "cases": n, "max_overlap": np.nan, "partner": "—", "text": f"{n} frysta positiva case finns; minst {MIN_OVERLAP_CASES} krävs för överlappskontroll."}
    overlaps: list[tuple[str, float]] = []
    for other_name, fn in specs:
        share = float(target_snaps.map(fn).mean()) if n else np.nan
        if math.isfinite(share):
            overlaps.append((other_name, share))
    if not overlaps:
        return {"status": CHECK_PENDING, "cases": n, "max_overlap": np.nan, "partner": "—", "text": "Inga jämförbara signalfamiljer kunde mätas."}
    partner, share = max(overlaps, key=lambda x: x[1])
    if share >= 0.70:
        status = "Högt överlapp"
        text = f"{share:.0%} av positiva case sammanfaller med {partner}. Unik informationsmängd måste granskas före promotion."
    elif share >= 0.40:
        status = "Måttligt överlapp"
        text = f"Största överlappet är {share:.0%} med {partner}. Delvis redundant signalbild är möjlig."
    else:
        status = "Lågt överlapp"
        text = f"Största observerade överlappet är {share:.0%} med {partner}. Det talar för viss självständighet, men bevisar inte unik alpha."
    return {"status": status, "cases": n, "max_overlap": share, "partner": partner, "text": text}


def apply_dossier_robustness(dossiers: pd.DataFrame, recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Fill only the robustness fields we can actually measure from frozen data."""
    if dossiers is None or dossiers.empty:
        return dossiers.copy() if isinstance(dossiers, pd.DataFrame) else pd.DataFrame()
    out = dossiers.copy()
    for idx, row in out.iterrows():
        name = str(row.get("Hypotes", ""))
        regime = regime_robustness(name, recommendations, outcomes)
        overlap = signal_overlap(name, recommendations)
        out.at[idx, "Regimrobusthet"] = regime["status"]
        out.at[idx, "Signalöverlapp"] = overlap["status"]
        blockers = [b.strip() for b in str(row.get("Blockerare", "")).split(",") if b.strip()]
        if regime["status"] != CHECK_PENDING:
            blockers = [b for b in blockers if b != "regimrobusthet"]
        if overlap["status"] != CHECK_PENDING:
            blockers = [b for b in blockers if b != "signalöverlapp"]
        out.at[idx, "Blockerare"] = ", ".join(blockers)
        # Preserve detail without pretending the summary label says more than the test.
        current = str(row.get("Nästa beslut", ""))
        out.at[idx, "Nästa beslut"] = current + f" Robusthet: {regime['text']} Överlapp: {overlap['text']}"
    return out
