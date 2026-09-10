from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

HORIZONS = {
    "1m": {"min_age_days": 28, "winner_return": 0.10, "label": "1 månad"},
    "3m": {"min_age_days": 84, "winner_return": 0.15, "label": "3 månader"},
}
MIN_COHORT = 20
TOP_QUANTILE = 0.90


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def build_universe_snapshot(
    frame: pd.DataFrame,
    profile: str,
    market: str,
    captured_date: str,
    recommended: dict[str, set[str]] | None = None,
    discovery_flags: pd.DataFrame | None = None,
    model_version: str = "",
) -> pd.DataFrame:
    """Freeze the broad discovery universe before future returns are known.

    This is deliberately broader than the recommendation ledger. Missing rankings are
    stored as false, never reconstructed later with a newer model.
    """
    cols = [
        "symbol", "name", "profile", "market", "captured_date", "entry_price",
        "borsify_score", "medium_score", "year_score", "lifetime_score",
        "valuation", "quality", "setup", "risk", "coverage",
        "revenue_growth", "earnings_growth", "profit_margin", "roe", "fcf_yield", "forward_pe",
        "recommended_medium", "recommended_year", "recommended_lifetime",
        "discovery_champion_selected", "discovery_challenger_flags", "discovery_registry_version", "model_version",
    ]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=cols)
    rec = recommended or {}
    rec_m = {str(x).upper() for x in rec.get("medium", set())}
    rec_y = {str(x).upper() for x in rec.get("year", set())}
    rec_l = {str(x).upper() for x in rec.get("lifetime", set())}

    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        symbol = str(row.get("Ticker") or "").upper().strip()
        price = _num(row.get("Pris"))
        if not symbol or not np.isfinite(price) or price <= 0:
            continue
        rows.append({
            "symbol": symbol,
            "name": str(row.get("Namn") or symbol),
            "profile": str(profile),
            "market": str(market),
            "captured_date": str(captured_date),
            "entry_price": float(price),
            "borsify_score": _num(row.get("Borsify Score")),
            "medium_score": _num(row.get("Mellan Score")),
            "year_score": _num(row.get("Års Score")),
            "lifetime_score": _num(row.get("Livstid Score")),
            "valuation": _num(row.get("Värdering")),
            "quality": _num(row.get("Kvalitet")),
            "setup": _num(row.get("Marknadsläge")),
            "risk": _num(row.get("Risk")),
            "coverage": _num(row.get("Datatäckning")),
            "revenue_growth": _num(row.get("Omsättningstillväxt")),
            "earnings_growth": _num(row.get("Vinsttillväxt")),
            "profit_margin": _num(row.get("Vinstmarginal")),
            "roe": _num(row.get("ROE")),
            "fcf_yield": _num(row.get("FCF-yield")),
            "forward_pe": _num(row.get("Forward P/E")),
            "recommended_medium": int(symbol in rec_m),
            "recommended_year": int(symbol in rec_y),
            "recommended_lifetime": int(symbol in rec_l),
            "discovery_champion_selected": int(discovery_flags.at[row.name, "discovery_champion_selected"]) if discovery_flags is not None and row.name in discovery_flags.index and "discovery_champion_selected" in discovery_flags.columns else None,
            "discovery_challenger_flags": __import__("discovery_champion_challenger").encode_challenger_flags(discovery_flags, row.name) if discovery_flags is not None else None,
            "discovery_registry_version": "1" if discovery_flags is not None else None,
            "model_version": str(model_version or ""),
        })
    return pd.DataFrame(rows, columns=cols)


def explain_miss(row: pd.Series | dict[str, Any], horizon: str) -> str:
    """Explain a miss only from values frozen at discovery time."""
    reasons: list[str] = []
    score_col = "medium_score" if horizon == "1m" else "year_score"
    score = _num(row.get(score_col))
    quality = _num(row.get("quality")); valuation = _num(row.get("valuation"))
    setup = _num(row.get("setup")); risk = _num(row.get("risk")); coverage = _num(row.get("coverage"))
    if np.isfinite(score) and score < 60: reasons.append("lågt fryst horisontscore")
    if np.isfinite(setup) and setup < 50: reasons.append("svagt marknadsläge")
    if np.isfinite(quality) and quality < 50: reasons.append("svag kvalitetsbedömning")
    if np.isfinite(valuation) and valuation < 45: reasons.append("värderingen såg inte attraktiv ut")
    if np.isfinite(risk) and risk < 50: reasons.append("riskbilden drog ned caset")
    if np.isfinite(coverage) and coverage < .65: reasons.append("begränsad datatäckning")
    return "; ".join(reasons[:3]) or "nådde inte topp 10 trots tillgängligt underlag"


def evaluate_snapshot_cohort(
    snapshots: pd.DataFrame,
    current_prices: pd.DataFrame,
    horizon: str,
    evaluated_date: str,
    min_cohort: int = MIN_COHORT,
    top_quantile: float = TOP_QUANTILE,
) -> pd.DataFrame:
    """Evaluate one frozen cohort using only its old snapshot and later prices.

    A missed winner must both be in the cohort's top return decile and clear a raw
    return hurdle. This avoids calling every rising stock a miss in a broad bull run.
    """
    cols = [
        "snapshot_id", "symbol", "name", "captured_date", "evaluated_date", "horizon",
        "entry_price", "evaluated_price", "return_pct", "return_percentile",
        "was_recommended", "missed_winner", "frozen_score", "why_missed",
    ]
    if horizon not in HORIZONS or snapshots is None or snapshots.empty or current_prices is None or current_prices.empty:
        return pd.DataFrame(columns=cols)

    cur = current_prices.copy()
    if "Ticker" in cur.columns:
        cur = cur.rename(columns={"Ticker": "symbol", "Pris": "evaluated_price"})
    if not {"symbol", "evaluated_price"}.issubset(cur.columns):
        return pd.DataFrame(columns=cols)
    cur["symbol"] = cur["symbol"].astype(str).str.upper()
    cur["evaluated_price"] = pd.to_numeric(cur["evaluated_price"], errors="coerce")
    cur = cur.dropna(subset=["evaluated_price"]).drop_duplicates("symbol", keep="last")

    snap = snapshots.copy()
    snap["symbol"] = snap["symbol"].astype(str).str.upper()
    merged = snap.merge(cur[["symbol", "evaluated_price"]], on="symbol", how="inner")
    merged["entry_price"] = pd.to_numeric(merged["entry_price"], errors="coerce")
    merged = merged[(merged["entry_price"] > 0) & (merged["evaluated_price"] > 0)].copy()
    if len(merged) < int(min_cohort):
        return pd.DataFrame(columns=cols)

    merged["return_pct"] = merged["evaluated_price"] / merged["entry_price"] - 1.0
    merged["return_percentile"] = merged["return_pct"].rank(method="average", pct=True)
    rec_col = {"1m": "recommended_medium", "3m": "recommended_year"}[horizon]
    score_col = {"1m": "medium_score", "3m": "year_score"}[horizon]
    merged["was_recommended"] = pd.to_numeric(merged.get(rec_col), errors="coerce").fillna(0).astype(int)
    merged["frozen_score"] = pd.to_numeric(merged.get(score_col), errors="coerce")
    hurdle = float(HORIZONS[horizon]["winner_return"])
    merged["missed_winner"] = (
        (merged["was_recommended"] == 0)
        & (merged["return_pct"] >= hurdle)
        & (merged["return_percentile"] >= float(top_quantile))
    ).astype(int)
    merged["evaluated_date"] = str(evaluated_date)
    merged["horizon"] = horizon
    merged["why_missed"] = [explain_miss(r, horizon) if int(r.get("missed_winner", 0)) else "" for _, r in merged.iterrows()]
    if "snapshot_id" not in merged.columns:
        merged["snapshot_id"] = merged["captured_date"].astype(str) + "::" + merged["profile"].astype(str) + "::" + merged["symbol"].astype(str)
    return merged[cols].sort_values(["missed_winner", "return_pct"], ascending=[False, False]).reset_index(drop=True)


def missed_winner_summary(outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    label = HORIZONS.get(horizon, {}).get("label", horizon)
    if outcomes is None or outcomes.empty:
        return {
            "status": "Bygger historik",
            "evaluated": 0,
            "misses": 0,
            "miss_rate": np.nan,
            "text": f"Borsify samlar nu bred point-in-time-historik. Inga mogna {label}-kohorter finns ännu.",
        }
    frame = outcomes[outcomes["horizon"].astype(str).eq(horizon)].copy() if "horizon" in outcomes.columns else pd.DataFrame()
    if frame.empty:
        return {
            "status": "Bygger historik", "evaluated": 0, "misses": 0, "miss_rate": np.nan,
            "text": f"Inga mogna {label}-kohorter finns ännu.",
        }
    evaluated = int(len(frame))
    misses = int(pd.to_numeric(frame["missed_winner"], errors="coerce").fillna(0).sum())
    rate = misses / evaluated if evaluated else np.nan
    return {
        "status": "Historik finns",
        "evaluated": evaluated,
        "misses": misses,
        "miss_rate": rate,
        "text": f"{misses} tydliga missade vinnare bland {evaluated} utvärderade aktieobservationer för {label}. Motorn visar vad Borsify missat; den ändrar inte score automatiskt.",
    }
