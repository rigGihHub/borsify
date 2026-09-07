from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

SHORT_WEIGHTS = {
    "Relativ styrka": ("Short Relative Strength", 0.27),
    "Trend": ("Short Trend", 0.23),
    "Momentum": ("Short Momentum", 0.17),
    "Handelsaktivitet": ("Short Participation", 0.10),
    "Förväntningsförändring": ("Short Revisions", 0.13),
    "Katalysator": ("Short Catalyst", 0.10),
}

MIN_ABLATION_CASES = 24
MIN_BUCKET = 6


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def prepare_short_ablation_data(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> pd.DataFrame:
    """Build an exact, point-in-time sample for the Short Alpha weighted blend.

    The additive Short Alpha model has six frozen 0–100 components with fixed weights.
    We only use rows where all six components were actually stored and where no hard
    veto capped the final score. Repeated same-stock observations with overlapping
    forward windows are removed before any statistics are calculated.
    """
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    req_r = {"record_id", "horizon_type", "snapshot_json"}
    req_o = {"record_id", "horizon", "return_pct"}
    if not req_r.issubset(recommendations.columns) or not req_o.issubset(outcomes.columns):
        return pd.DataFrame()

    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if outs.empty:
        return pd.DataFrame()
    keep = [c for c in ["record_id", "symbol", "captured_date", "horizon_type", "snapshot_json"] if c in recommendations.columns]
    merged = recommendations[keep].merge(outs, on="record_id", how="inner", suffixes=("", "_out"))
    merged = merged[merged["horizon_type"].astype(str).str.lower().eq("short")].copy()
    if merged.empty:
        return merged

    snaps = merged["snapshot_json"].map(_snapshot)
    for _, (field, _) in SHORT_WEIGHTS.items():
        merged[field] = snaps.map(lambda s, f=field: _num(s.get(f)))
    merged["_vetoes"] = snaps.map(lambda s: str(s.get("Short Vetoes") or "—").strip())

    fields = [field for field, _ in SHORT_WEIGHTS.values()]
    for col in fields + ["return_pct"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged.dropna(subset=fields + ["return_pct"]).copy()
    # A hard veto caps the production score at 54. Ablation of the additive blend would
    # not be an apples-to-apples test on those rows, so keep veto logic out of this test.
    merged = merged[merged["_vetoes"].isin({"", "—", "-", "None", "nan"})].copy()
    if merged.empty:
        return merged

    return independent_case_sample(merged, str(horizon))


def _weighted_score(frame: pd.DataFrame, excluded_label: str | None = None) -> pd.Series:
    parts = []
    total = 0.0
    for label, (field, weight) in SHORT_WEIGHTS.items():
        if label == excluded_label:
            continue
        parts.append(pd.to_numeric(frame[field], errors="coerce") * float(weight))
        total += float(weight)
    if not parts or total <= 0:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    score = sum(parts) / total
    return pd.to_numeric(score, errors="coerce")


def _rank_corr(score: pd.Series, outcome: pd.Series) -> float:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna()
    if len(work) < 4 or work["score"].nunique() < 2 or work["outcome"].nunique() < 2:
        return np.nan
    return float(work["score"].rank(method="average").corr(work["outcome"].rank(method="average")))


def _top_bottom_spread(score: pd.Series, outcome: pd.Series) -> tuple[float, int, int]:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna().sort_values("score")
    n = len(work)
    bucket = n // 3
    if bucket < MIN_BUCKET:
        return np.nan, 0, 0
    low = work.head(bucket)["outcome"]
    high = work.tail(bucket)["outcome"]
    return float(high.median() - low.median()), int(len(high)), int(len(low))


def _status(delta_spread: float, delta_corr: float, n: int) -> str:
    if n < MIN_ABLATION_CASES:
        return "För lite underlag"
    ds = delta_spread if math.isfinite(delta_spread) else 0.0
    dc = delta_corr if math.isfinite(delta_corr) else 0.0
    # Require meaningful movement and no clear contradiction from the other metric.
    if (ds >= 0.02 and dc >= 0.0) or (dc >= 0.05 and ds >= 0.0):
        return "Verkar tillföra information"
    if (ds <= -0.02 and dc <= 0.0) or (dc <= -0.05 and ds <= 0.0):
        return "Bör granskas"
    return "Ingen tydlig skillnad"


def short_signal_ablation(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> pd.DataFrame:
    """Leave one frozen Short Alpha component out at a time.

    This tests the *actual weighted additive blend*, not a newly invented score. The
    remaining weights are renormalized after one component is removed. It is a
    descriptive out-of-sample diagnostic; it never changes production weights.
    """
    data = prepare_short_ablation_data(recommendations, outcomes, horizon)
    columns = [
        "Signal", "Oberoende case", "Baslinje korrelation", "Utan signal korrelation",
        "Förändring korrelation", "Baslinje topp-botten", "Utan signal topp-botten",
        "Förändring topp-botten", "Mätning", "Status",
    ]
    if data.empty:
        return pd.DataFrame(columns=columns)

    metric_col, metric_label = _outcome_basis(data)
    outcome = pd.to_numeric(data[metric_col], errors="coerce")
    base_score = _weighted_score(data)
    base_corr = _rank_corr(base_score, outcome)
    base_spread, _, _ = _top_bottom_spread(base_score, outcome)

    rows = []
    for label in SHORT_WEIGHTS:
        ablated = _weighted_score(data, excluded_label=label)
        corr = _rank_corr(ablated, outcome)
        spread, _, _ = _top_bottom_spread(ablated, outcome)
        dc = base_corr - corr if math.isfinite(base_corr) and math.isfinite(corr) else np.nan
        ds = base_spread - spread if math.isfinite(base_spread) and math.isfinite(spread) else np.nan
        rows.append({
            "Signal": label,
            "Oberoende case": int(len(data)),
            "Baslinje korrelation": base_corr,
            "Utan signal korrelation": corr,
            "Förändring korrelation": dc,
            "Baslinje topp-botten": base_spread,
            "Utan signal topp-botten": spread,
            "Förändring topp-botten": ds,
            "Mätning": metric_label,
            "Status": _status(ds, dc, len(data)),
        })
    result = pd.DataFrame(rows)
    order = {"Bör granskas": 0, "Verkar tillföra information": 1, "Ingen tydlig skillnad": 2, "För lite underlag": 3}
    result["_order"] = result["Status"].map(order).fillna(9)
    return result.sort_values(["_order", "Förändring topp-botten"], ascending=[True, True]).drop(columns="_order").reset_index(drop=True)


def ablation_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {
            "status": "Ingen analys ännu",
            "text": "Det finns ännu inga mogna kortsiktiga case med komplett fryst signaldata för den valda perioden.",
        }
    n = int(table["Oberoende case"].max()) if "Oberoende case" in table.columns else 0
    if n < MIN_ABLATION_CASES:
        return {
            "status": "För lite underlag",
            "text": f"{n} oberoende case finns. Borsify väntar tills minst {MIN_ABLATION_CASES} finns innan en signal bedöms som möjlig nytta eller möjlig belastning.",
        }
    review = table[table["Status"].eq("Bör granskas")]
    useful = table[table["Status"].eq("Verkar tillföra information")]
    if not review.empty:
        names = ", ".join(review["Signal"].head(2).astype(str).tolist())
        return {
            "status": "Signal värd att granska",
            "text": f"När {names} tas bort förbättras den historiska rangordningen i det här urvalet. Det är en granskningssignal, inte bevis för att vikten ska sänkas.",
        }
    if not useful.empty:
        names = ", ".join(useful["Signal"].head(2).astype(str).tolist())
        return {
            "status": "Möjlig informationsnytta",
            "text": f"{names} verkar hittills tillföra information: resultatet försämras när signalen tas bort. Underlaget är fortfarande observationsdata och får inte styra vikterna automatiskt.",
        }
    return {
        "status": "Ingen tydlig skillnad",
        "text": "Ingen enskild signal ändrar den historiska rangordningen tillräckligt mycket för en praktisk slutsats ännu.",
    }
