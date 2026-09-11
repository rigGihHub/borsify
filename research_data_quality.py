from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from research_dossier_robustness import CHECK_PENDING, _sample_for, _snapshot

MIN_MATURE_CASES = 12
MIN_COVERAGE_OBS = 8
MIN_GOOD_COVERAGE = 0.70
MIN_ACCEPTABLE_COVERAGE = 0.50
MIN_TIMESTAMP_COVERAGE = 0.60
MAX_PRICE_AGE_DAYS = 7

# These are provenance/quality fields that the ledger actually freezes.  We do not
# invent per-vendor source counts when the snapshot does not contain them.
QUALITY_FIELDS = (
    "Datatäckning",
    "Prisdatum",
    "Fundamental hämtad",
    "_Fundamental cache",
)


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "—", "nan", "None", "NaT"}


def _age_days(captured: Any, price_date: Any) -> float:
    try:
        a = pd.Timestamp(captured).normalize()
        b = pd.Timestamp(price_date).normalize()
        return float(max(0, (a - b).days))
    except Exception:
        return np.nan


def _case_quality(row: pd.Series) -> dict[str, Any]:
    snap = _snapshot(row.get("snapshot_json"))
    coverage = _num(snap.get("Datatäckning"))
    price_age = _age_days(row.get("captured_date"), snap.get("Prisdatum"))
    has_fundamental_ts = _present(snap.get("Fundamental hämtad"))
    return {
        "coverage": coverage,
        "price_age": price_age,
        "fundamental_ts": has_fundamental_ts,
    }


def data_quality_audit(
    name: str,
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: tuple[str, ...] = ("1m", "3m", "6m"),
) -> dict[str, Any]:
    """Audit frozen input quality for mature research observations.

    This is intentionally an audit of what was frozen at decision time.  It checks
    coverage, price freshness and provenance timestamps.  It does *not* claim that
    vendor diversity or historical source redundancy was measured unless those fields
    existed in the PIT snapshot.
    """
    rows: list[pd.DataFrame] = []
    for horizon in horizons:
        sample, state_col = _sample_for(name, recommendations, outcomes, horizon)
        if sample is None or sample.empty or not state_col:
            continue
        work = sample.copy()
        state = pd.to_numeric(work[state_col], errors="coerce")
        work = work.loc[state.eq(1)].copy()
        if len(work) < MIN_MATURE_CASES:
            continue
        work["_audit_horizon"] = horizon
        rows.append(work)

    if not rows:
        return {
            "status": CHECK_PENDING,
            "mature_cases": 0,
            "coverage_observations": 0,
            "median_coverage": np.nan,
            "fresh_price_share": np.nan,
            "fundamental_timestamp_share": np.nan,
            "missingness_bias": CHECK_PENDING,
            "text": f"För få mogna positiva case; minst {MIN_MATURE_CASES} per horisont krävs för datakvalitetsrevision.",
        }

    work = pd.concat(rows, ignore_index=True)
    qualities = pd.DataFrame([_case_quality(r) for _, r in work.iterrows()])
    cov = pd.to_numeric(qualities["coverage"], errors="coerce")
    age = pd.to_numeric(qualities["price_age"], errors="coerce")
    cov_obs = int(cov.notna().sum())
    med_cov = float(cov.median()) if cov_obs else np.nan
    fresh_share = float(age.le(MAX_PRICE_AGE_DAYS).sum() / age.notna().sum()) if age.notna().any() else np.nan
    ts_share = float(qualities["fundamental_ts"].mean()) if len(qualities) else np.nan

    # Missingness-bias diagnostic: compare outcomes for cases with strong vs weak/missing
    # frozen coverage.  This is descriptive, not causal.
    metric = "excess_return_pct" if "excess_return_pct" in work.columns and pd.to_numeric(work["excess_return_pct"], errors="coerce").notna().all() else "return_pct"
    vals = pd.to_numeric(work.get(metric), errors="coerce")
    good_mask = cov.ge(MIN_GOOD_COVERAGE)
    weak_mask = cov.lt(MIN_GOOD_COVERAGE) | cov.isna()
    good_vals = vals[good_mask].dropna()
    weak_vals = vals[weak_mask].dropna()
    if len(good_vals) >= MIN_COVERAGE_OBS and len(weak_vals) >= MIN_COVERAGE_OBS:
        gap = float(good_vals.median() - weak_vals.median())
        if abs(gap) >= 0.05:
            missingness_bias = "Systematisk täckningsskillnad – granska"
        else:
            missingness_bias = "Ingen stor observerad täckningsskillnad"
    else:
        gap = np.nan
        missingness_bias = CHECK_PENDING

    measured = cov_obs >= MIN_COVERAGE_OBS and math.isfinite(fresh_share) and math.isfinite(ts_share)
    if not measured:
        status = "Datakvalitet delvis verifierad"
    elif med_cov < MIN_ACCEPTABLE_COVERAGE or fresh_share < 0.80 or ts_share < MIN_TIMESTAMP_COVERAGE:
        status = "Datakvalitet ifrågasatt"
    elif missingness_bias == "Systematisk täckningsskillnad – granska":
        status = "Datakvalitet ifrågasatt"
    else:
        status = "Datakvalitet verifierad"

    cov_text = f"median fryst datatäckning {med_cov:.0%}" if math.isfinite(med_cov) else "fryst datatäckning saknas"
    fresh_text = f"{fresh_share:.0%} har kursdatum högst {MAX_PRICE_AGE_DAYS} dagar gammalt" if math.isfinite(fresh_share) else "kursfärskhet kan inte mätas"
    ts_text = f"{ts_share:.0%} har registrerad fundamental hämtningstid" if math.isfinite(ts_share) else "fundamental hämtningstid kan inte mätas"
    bias_text = missingness_bias + (f" (median-gap {gap:+.1%})" if math.isfinite(gap) else "")
    text = (
        f"{cov_text}; {fresh_text}; {ts_text}. {bias_text}. "
        "Revisionen använder endast PIT-fält som faktiskt frysts i recommendation-ledgern. "
        "Antal oberoende dataleverantörer verifieras inte eftersom sådan provenance inte finns konsekvent i äldre snapshots."
    )
    return {
        "status": status,
        "mature_cases": int(len(work)),
        "coverage_observations": cov_obs,
        "median_coverage": med_cov,
        "fresh_price_share": fresh_share,
        "fundamental_timestamp_share": ts_share,
        "missingness_bias": missingness_bias,
        "missingness_outcome_gap": gap,
        "text": text,
    }


def apply_data_quality(dossiers: pd.DataFrame, recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if dossiers is None or dossiers.empty:
        return dossiers.copy() if isinstance(dossiers, pd.DataFrame) else pd.DataFrame()
    out = dossiers.copy()
    if "Datakvalitet" not in out.columns:
        out["Datakvalitet"] = CHECK_PENDING
    for idx, row in out.iterrows():
        result = data_quality_audit(str(row.get("Hypotes", "")), recommendations, outcomes)
        out.at[idx, "Datakvalitet"] = result["status"]
        blockers = [b.strip() for b in str(row.get("Blockerare", "")).split(",") if b.strip()]
        if result["status"] in {"Datakvalitet verifierad", "Datakvalitet ifrågasatt"}:
            blockers = [b for b in blockers if b != "datakvalitet"]
        out.at[idx, "Blockerare"] = ", ".join(blockers)
        current = str(row.get("Nästa beslut", ""))
        out.at[idx, "Nästa beslut"] = current + f" Datakvalitet: {result['text']}"
    return out
