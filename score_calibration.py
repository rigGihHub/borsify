from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

MIN_CALIBRATION_CASES = 24
MIN_BAND_CASES = 6
SCORE_BANDS = [(-np.inf, 60, "Under 60"), (60, 70, "60–69"), (70, 80, "70–79"), (80, np.inf, "80+")]


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    """Use benchmark-relative outcomes only when the whole cohort has them."""
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def _band(score: Any) -> str:
    try:
        x = float(score)
    except Exception:
        return "Score saknas"
    if not math.isfinite(x):
        return "Score saknas"
    for low, high, label in SCORE_BANDS:
        if low <= x < high:
            return label
    return "Score saknas"


def _rank_corr(score: pd.Series, outcome: pd.Series) -> float:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna()
    if len(work) < 4 or work["score"].nunique() < 2 or work["outcome"].nunique() < 2:
        return np.nan
    return float(work["score"].rank(method="average").corr(work["outcome"].rank(method="average")))


def prepare_score_calibration_data(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    horizon_type: str,
) -> pd.DataFrame:
    """Return independent, point-in-time score/outcome observations for one model type."""
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    need_r = {"record_id", "horizon_type", "score"}
    need_o = {"record_id", "horizon", "return_pct"}
    if not need_r.issubset(recommendations.columns) or not need_o.issubset(outcomes.columns):
        return pd.DataFrame()

    rec = recommendations[recommendations["horizon_type"].astype(str).str.lower().eq(str(horizon_type).lower())].copy()
    out = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if rec.empty or out.empty:
        return pd.DataFrame()

    keep = [c for c in ["record_id", "symbol", "captured_date", "horizon_type", "score", "gate", "model_version"] if c in rec.columns]
    merged = rec[keep].merge(out, on="record_id", how="inner", suffixes=("", "_out"))
    merged["score"] = pd.to_numeric(merged["score"], errors="coerce")
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    if "excess_return_pct" in merged.columns:
        merged["excess_return_pct"] = pd.to_numeric(merged["excess_return_pct"], errors="coerce")
    merged = merged.dropna(subset=["score", "return_pct"]).copy()
    if merged.empty:
        return merged
    return independent_case_sample(merged, str(horizon))


def score_calibration_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> pd.DataFrame:
    """Check whether higher frozen Borsify scores map to better later outcomes.

    Short and long models are never mixed, even for the shared 6m outcome horizon.
    Fixed score bands make the diagnostic stable across runs and easy to interpret.
    """
    rows: list[dict[str, Any]] = []
    order = {label: i for i, (_, _, label) in enumerate(SCORE_BANDS)}
    for horizon_type, label in [("short", "Kortsiktig"), ("long", "Långsiktig")]:
        data = prepare_score_calibration_data(recommendations, outcomes, horizon, horizon_type)
        if data.empty:
            continue
        metric_col, metric_label = _outcome_basis(data)
        metric = pd.to_numeric(data[metric_col], errors="coerce")
        work = data.assign(_metric=metric, _band=data["score"].map(_band)).dropna(subset=["_metric"])
        for band, group in work.groupby("_band", dropna=False):
            if band == "Score saknas":
                continue
            rows.append({
                "Typ": label,
                "Scoregrupp": str(band),
                "Ordning": order.get(str(band), 99),
                "Oberoende case": int(len(group)),
                "Medianutfall": float(group["_metric"].median()),
                "Snittutfall": float(group["_metric"].mean()),
                "Positiva": float((group["_metric"] > 0).mean()),
                "Mätning": metric_label,
                "Tillräckligt per grupp": bool(len(group) >= MIN_BAND_CASES),
            })
    if not rows:
        return pd.DataFrame(columns=["Typ", "Scoregrupp", "Ordning", "Oberoende case", "Medianutfall", "Snittutfall", "Positiva", "Mätning", "Tillräckligt per grupp"])
    return pd.DataFrame(rows).sort_values(["Typ", "Ordning"]).reset_index(drop=True)


def score_calibration_summary(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> dict[str, Any]:
    """Cautious monotonic-calibration summary; never changes model weights."""
    table = score_calibration_table(recommendations, outcomes, horizon)
    details: list[dict[str, Any]] = []
    if table.empty:
        return {"status": "För lite underlag", "text": "Det finns ännu inga mogna oberoende case med sparad score för vald period.", "details": details}

    for typ, t in table.groupby("Typ", sort=False):
        enough = t[t["Tillräckligt per grupp"]].sort_values("Ordning").copy()
        # Count all independent rows from the underlying type sample, not only bands >= min bucket.
        horizon_type = "short" if typ == "Kortsiktig" else "long"
        raw = prepare_score_calibration_data(recommendations, outcomes, horizon, horizon_type)
        n = int(len(raw))
        metric_col, metric_label = _outcome_basis(raw) if not raw.empty else ("return_pct", "Rå kursutveckling")
        corr = _rank_corr(pd.to_numeric(raw.get("score"), errors="coerce"), pd.to_numeric(raw.get(metric_col), errors="coerce")) if not raw.empty else np.nan
        if n < MIN_CALIBRATION_CASES or len(enough) < 2:
            details.append({"typ": typ, "status": "För lite underlag", "n": n, "groups": int(len(enough)), "corr": corr, "measurement": metric_label})
            continue

        med = enough["Medianutfall"].to_numpy(dtype=float)
        diffs = np.diff(med)
        monotonic = bool(np.all(diffs >= 0))
        inversions = int(np.sum(diffs < 0))
        spread = float(med[-1] - med[0])

        if monotonic and spread >= 0.03 and (not math.isfinite(corr) or corr >= 0.05):
            status = "Bra ordning"
        elif inversions >= 2 or spread <= -0.03 or (math.isfinite(corr) and corr <= -0.05):
            status = "Kalibreringen bör granskas"
        else:
            status = "Ingen tydlig ordning"
        details.append({
            "typ": typ,
            "status": status,
            "n": n,
            "groups": int(len(enough)),
            "corr": corr,
            "spread": spread,
            "inversions": inversions,
            "measurement": metric_label,
        })

    reviewed = [d for d in details if d["status"] != "För lite underlag"]
    if not reviewed:
        total = sum(int(d.get("n", 0)) for d in details)
        return {
            "status": "För lite underlag",
            "text": f"{total} oberoende case finns, men Borsify väntar på minst {MIN_CALIBRATION_CASES} per modelltyp och minst två scoregrupper med {MIN_BAND_CASES} case vardera.",
            "details": details,
        }
    bad = [d for d in reviewed if d["status"] == "Kalibreringen bör granskas"]
    good = [d for d in reviewed if d["status"] == "Bra ordning"]
    if bad:
        names = ", ".join(d["typ"].lower() for d in bad)
        return {
            "status": "Kalibreringen bör granskas",
            "text": f"Högre Borsify-betyg har inte gett tydligt bättre utfall i rätt ordning för {names}. Det är en varningssignal, inte bevis på att modellen är fel.",
            "details": details,
        }
    if len(good) == len(reviewed):
        names = ", ".join(d["typ"].lower() for d in good)
        return {
            "status": "Bra ordning",
            "text": f"Högre Borsify-betyg har hittills följts av bättre utfall i stigande ordning för {names}. Underlaget är fortfarande historiskt och ska inte tolkas som en sannolikhet.",
            "details": details,
        }
    return {
        "status": "Ingen tydlig ordning",
        "text": "Det finns tillräckligt med historik för att mäta kalibreringen, men högre betyg följs ännu inte av ett stabilt bättre utfall i varje scoregrupp.",
        "details": details,
    }
