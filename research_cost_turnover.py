from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from research_dossier_robustness import CHECK_PENDING, _positive_classifier, _sample_for, _snapshot

BASE_COST_BPS = 30.0
STRESS_COST_BPS = 100.0
MIN_POSITIVE_OUTCOMES = 10
MIN_LIQUIDITY_COVERAGE = 0.60
MIN_CHURN_SYMBOLS = 3
MIN_CHURN_SPAN_DAYS = 90
EPISODE_GAP_DAYS = 14


def _metric_name(df: pd.DataFrame) -> str:
    if "excess_return_pct" in df.columns:
        excess = pd.to_numeric(df["excess_return_pct"], errors="coerce")
        if excess.notna().all():
            return "excess_return_pct"
    return "return_pct"


def _turnover_msek(snapshot: dict[str, Any]) -> float:
    for key in ("Omsättning MSEK/dag", "Likviditet omsättning MSEK", "Omsättning lokal M/dag"):
        try:
            x = float(snapshot.get(key))
            if math.isfinite(x) and x >= 0:
                return x
        except Exception:
            pass
    return np.nan


def _positive_recommendations(name: str, recommendations: pd.DataFrame) -> pd.DataFrame:
    if recommendations is None or recommendations.empty or "snapshot_json" not in recommendations.columns:
        return pd.DataFrame()
    classifier = _positive_classifier(name)
    if classifier is None:
        return pd.DataFrame()
    work = recommendations.copy()
    work["_snapshot"] = work["snapshot_json"].map(_snapshot)
    work["_positive"] = work["_snapshot"].map(lambda snap: bool(classifier(snap)))
    return work[work["_positive"]].copy()


def _observed_churn(name: str, recommendations: pd.DataFrame) -> dict[str, Any]:
    """Estimate signal re-entry frequency from ledger observations only.

    This is deliberately labelled observed churn: the recommendation ledger is not a
    complete daily portfolio history, so it must never be presented as true portfolio
    turnover. Positive observations within 14 days are treated as one episode.
    """
    positive = _positive_recommendations(name, recommendations)
    if positive.empty or "symbol" not in positive.columns or "captured_date" not in positive.columns:
        return {"status": CHECK_PENDING, "symbols": 0, "episodes_per_year": np.nan, "text": "För lite ledgerdata för att uppskatta observerad signalomsättning."}

    all_obs = recommendations.copy()
    all_obs["_date"] = pd.to_datetime(all_obs.get("captured_date"), errors="coerce")
    positive["_date"] = pd.to_datetime(positive.get("captured_date"), errors="coerce")
    positive = positive.dropna(subset=["_date", "symbol"])
    all_obs = all_obs.dropna(subset=["_date", "symbol"])

    rates: list[float] = []
    episode_counts = 0
    eligible_symbols = 0
    for symbol, pos_group in positive.groupby("symbol"):
        obs_dates = all_obs.loc[all_obs["symbol"].eq(symbol), "_date"].sort_values()
        if obs_dates.empty:
            continue
        span_days = int((obs_dates.iloc[-1] - obs_dates.iloc[0]).days)
        if span_days < MIN_CHURN_SPAN_DAYS:
            continue
        dates = pos_group["_date"].sort_values().drop_duplicates()
        if dates.empty:
            continue
        episodes = 1
        prev = dates.iloc[0]
        for current in dates.iloc[1:]:
            if int((current - prev).days) > EPISODE_GAP_DAYS:
                episodes += 1
            prev = current
        years = max(span_days / 365.25, 1 / 365.25)
        rates.append(float(episodes / years))
        episode_counts += episodes
        eligible_symbols += 1

    if eligible_symbols < MIN_CHURN_SYMBOLS:
        return {
            "status": CHECK_PENDING,
            "symbols": eligible_symbols,
            "episodes_per_year": np.nan,
            "text": f"Endast {eligible_symbols} symbol(er) har minst {MIN_CHURN_SPAN_DAYS} dagars observerad ledgerhistorik; minst {MIN_CHURN_SYMBOLS} krävs.",
        }

    rate = float(np.median(rates)) if rates else np.nan
    if rate >= 8:
        status = "Hög observerad signalomsättning"
    elif rate >= 4:
        status = "Måttlig observerad signalomsättning"
    else:
        status = "Låg observerad signalomsättning"
    return {
        "status": status,
        "symbols": eligible_symbols,
        "episodes": episode_counts,
        "episodes_per_year": rate,
        "text": f"Medianen är {rate:.1f} positiva signalepisoder per symbol-år bland {eligible_symbols} symboler med tillräcklig ledgerhistorik. Detta är observerad churn, inte full portföljomsättning.",
    }


def cost_turnover_robustness(
    name: str,
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: tuple[str, ...] = ("1m", "3m", "6m"),
) -> dict[str, Any]:
    """Stress-test gross favorable outcomes against explicit round-trip cost assumptions.

    Borsify does not have frozen historical bid/ask/order-book execution for these
    research observations. We therefore test transparent fixed cost scenarios (30 and
    100 bps round trip) and separately report frozen daily traded-value coverage. The
    function never claims those scenarios are realized execution costs.
    """
    mature: list[dict[str, Any]] = []
    liquidity_values: list[float] = []
    liquidity_total = 0

    for horizon in horizons:
        sample, state_col = _sample_for(name, recommendations, outcomes, horizon)
        if sample is None or sample.empty or not state_col:
            continue
        work = sample.copy()
        state = pd.to_numeric(work[state_col], errors="coerce")
        good = work.loc[state.eq(1)].copy()
        if good.empty:
            continue
        metric = _metric_name(good)
        vals = pd.to_numeric(good.get(metric), errors="coerce").dropna()
        if len(vals) < MIN_POSITIVE_OUTCOMES:
            continue
        gross = float(vals.median())
        base_net = gross - BASE_COST_BPS / 10000.0
        stress_net = gross - STRESS_COST_BPS / 10000.0
        mature.append({"horizon": horizon, "n": int(len(vals)), "gross": gross, "base_net": base_net, "stress_net": stress_net})

        if "snapshot_json" in good.columns:
            snaps = good["snapshot_json"].map(_snapshot)
            liquidity_total += int(len(snaps))
            for snap in snaps:
                x = _turnover_msek(snap)
                if math.isfinite(x):
                    liquidity_values.append(float(x))

    churn = _observed_churn(name, recommendations)
    if not mature:
        return {
            "status": CHECK_PENDING,
            "mature_horizons": 0,
            "largest_sample": 0,
            "gross_median": np.nan,
            "stress_net_median": np.nan,
            "liquidity_coverage": 0.0,
            "median_turnover_msek": np.nan,
            "churn_status": churn["status"],
            "text": f"För få mogna positiva utfall; minst {MIN_POSITIVE_OUTCOMES} per horisont krävs för kostnadsstress. {churn['text']}",
        }

    stress_positive = sum(r["stress_net"] > 0 for r in mature)
    base_positive = sum(r["base_net"] > 0 for r in mature)
    gross_med = float(np.median([r["gross"] for r in mature]))
    stress_med = float(np.median([r["stress_net"] for r in mature]))
    coverage = float(len(liquidity_values) / liquidity_total) if liquidity_total else 0.0
    turnover_med = float(np.median(liquidity_values)) if liquidity_values else np.nan

    if stress_positive == len(mature):
        cost_status = "Robust mot kostnadsstress"
    elif base_positive == len(mature):
        cost_status = "Tål baskostnad men inte stress"
    else:
        cost_status = "Kostnadskänslig"

    liquidity_ok = coverage >= MIN_LIQUIDITY_COVERAGE
    churn_ok = churn["status"] != CHECK_PENDING
    if not liquidity_ok or not churn_ok:
        status = "Delvis verifierad"
    elif cost_status == "Kostnadskänslig":
        status = "Kostnad/omsättning ifrågasatt"
    else:
        status = "Kostnad/omsättning verifierad"

    liq_text = (
        f"Fryst daglig handelsomsättning finns för {coverage:.0%} av mogna positiva case"
        + (f"; median {turnover_med:.1f} MSEK/dag." if math.isfinite(turnover_med) else ".")
    )
    text = (
        f"{cost_status}: median brutto {gross_med:+.1%}; efter 100 bps tur/retur {stress_med:+.1%} över {len(mature)} mogen horisont(er). "
        f"Kostnaderna är transparenta stressantaganden, inte rekonstruerad historisk spread/slippage. {liq_text} {churn['text']}"
    )
    return {
        "status": status,
        "cost_status": cost_status,
        "mature_horizons": len(mature),
        "largest_sample": max(r["n"] for r in mature),
        "gross_median": gross_med,
        "stress_net_median": stress_med,
        "liquidity_coverage": coverage,
        "median_turnover_msek": turnover_med,
        "churn_status": churn["status"],
        "observed_episodes_per_year": churn.get("episodes_per_year", np.nan),
        "text": text,
    }


def apply_cost_turnover(dossiers: pd.DataFrame, recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if dossiers is None or dossiers.empty:
        return dossiers.copy() if isinstance(dossiers, pd.DataFrame) else pd.DataFrame()
    out = dossiers.copy()
    if "Kostnad/omsättning" not in out.columns:
        out["Kostnad/omsättning"] = CHECK_PENDING
    for idx, row in out.iterrows():
        result = cost_turnover_robustness(str(row.get("Hypotes", "")), recommendations, outcomes)
        out.at[idx, "Kostnad/omsättning"] = result["status"]
        blockers = [b.strip() for b in str(row.get("Blockerare", "")).split(",") if b.strip()]
        # Only a fully measured result clears the blocker. Partial verification is explicit.
        if result["status"] in {"Kostnad/omsättning verifierad", "Kostnad/omsättning ifrågasatt"}:
            blockers = [b for b in blockers if b != "kostnad/omsättning"]
        out.at[idx, "Blockerare"] = ", ".join(blockers)
        current = str(row.get("Nästa beslut", ""))
        out.at[idx, "Nästa beslut"] = current + f" Kostnad/omsättning: {result['text']}"
    return out
