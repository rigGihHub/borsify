from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from signal_ablation import SHORT_WEIGHTS, prepare_short_ablation_data

MIN_HORIZON_CASES = 24
MIN_REVIEW_HORIZONS = 2

STATUS_BETTER = "Challenger bättre"
STATUS_WORSE = "Champion bättre"
STATUS_TIE = "Ingen tydlig skillnad"
STATUS_WAIT = "För lite underlag"

ACTION_CONTINUE = "Kandidat för fortsatt test"
ACTION_KEEP = "Behåll champion"
ACTION_UNCLEAR = "Oklart – samla mer data"
ACTION_WAIT = "Vänta på mer data"


@dataclass(frozen=True)
class ChallengerSpec:
    challenger_id: str
    name: str
    excluded_signal: str
    rationale: str


def default_short_challengers() -> list[ChallengerSpec]:
    """Pre-registered leave-one-signal-out challengers for the additive Short Alpha blend.

    These variants are intentionally simple and interpretable. They are not promoted
    automatically and do not mutate the production model.
    """
    return [
        ChallengerSpec(
            challenger_id=f"short_without_{i}",
            name=f"Utan {label}",
            excluded_signal=label,
            rationale=f"Testar om Short Alpha blir robustare när signalfamiljen {label.lower()} tas bort.",
        )
        for i, label in enumerate(SHORT_WEIGHTS.keys(), start=1)
    ]


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def _weighted_score(frame: pd.DataFrame, excluded_signal: str | None = None) -> pd.Series:
    pieces: list[pd.Series] = []
    weight_sum = 0.0
    for label, (field, weight) in SHORT_WEIGHTS.items():
        if label == excluded_signal:
            continue
        pieces.append(pd.to_numeric(frame[field], errors="coerce") * float(weight))
        weight_sum += float(weight)
    if not pieces or weight_sum <= 0:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(sum(pieces) / weight_sum, errors="coerce")


def _rank_corr(score: pd.Series, outcome: pd.Series) -> float:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna()
    if len(work) < 4 or work["score"].nunique() < 2 or work["outcome"].nunique() < 2:
        return np.nan
    return float(work["score"].rank(method="average").corr(work["outcome"].rank(method="average")))


def _top_bottom_spread(score: pd.Series, outcome: pd.Series) -> float:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna().sort_values("score")
    bucket = len(work) // 3
    if bucket < 6:
        return np.nan
    return float(work.tail(bucket)["outcome"].median() - work.head(bucket)["outcome"].median())


def _horizon_status(n: int, delta_spread: float, delta_corr: float) -> str:
    if n < MIN_HORIZON_CASES:
        return STATUS_WAIT
    ds = delta_spread if math.isfinite(delta_spread) else 0.0
    dc = delta_corr if math.isfinite(delta_corr) else 0.0
    if (ds >= 0.02 and dc >= 0.0) or (dc >= 0.05 and ds >= 0.0):
        return STATUS_BETTER
    if (ds <= -0.02 and dc <= 0.0) or (dc <= -0.05 and ds <= 0.0):
        return STATUS_WORSE
    return STATUS_TIE


def compare_short_challenger(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    challenger: ChallengerSpec,
) -> dict[str, Any]:
    """Compare one pre-registered challenger with the current Short Alpha champion.

    The same point-in-time independent case sample is used for both models. The only
    difference is the pre-declared signal removal, with remaining original weights
    renormalized. No thresholds, labels or data are tuned using the evaluated outcome.
    """
    data = prepare_short_ablation_data(recommendations, outcomes, horizon)
    if data.empty:
        return {
            "Challenger ID": challenger.challenger_id,
            "Challenger": challenger.name,
            "Horisont": str(horizon),
            "Oberoende case": 0,
            "Status": STATUS_WAIT,
            "Mätning": "—",
            "Champion korrelation": np.nan,
            "Challenger korrelation": np.nan,
            "Förändring korrelation": np.nan,
            "Champion topp-botten": np.nan,
            "Challenger topp-botten": np.nan,
            "Förändring topp-botten": np.nan,
            "Hypotes": challenger.rationale,
        }

    metric_col, metric_label = _outcome_basis(data)
    outcome = pd.to_numeric(data[metric_col], errors="coerce")
    champion = _weighted_score(data)
    challenger_score = _weighted_score(data, excluded_signal=challenger.excluded_signal)
    champion_corr = _rank_corr(champion, outcome)
    challenger_corr = _rank_corr(challenger_score, outcome)
    champion_spread = _top_bottom_spread(champion, outcome)
    challenger_spread = _top_bottom_spread(challenger_score, outcome)
    delta_corr = challenger_corr - champion_corr if math.isfinite(champion_corr) and math.isfinite(challenger_corr) else np.nan
    delta_spread = challenger_spread - champion_spread if math.isfinite(champion_spread) and math.isfinite(challenger_spread) else np.nan

    return {
        "Challenger ID": challenger.challenger_id,
        "Challenger": challenger.name,
        "Horisont": str(horizon),
        "Oberoende case": int(len(data)),
        "Status": _horizon_status(int(len(data)), delta_spread, delta_corr),
        "Mätning": metric_label,
        "Champion korrelation": champion_corr,
        "Challenger korrelation": challenger_corr,
        "Förändring korrelation": delta_corr,
        "Champion topp-botten": champion_spread,
        "Challenger topp-botten": challenger_spread,
        "Förändring topp-botten": delta_spread,
        "Hypotes": challenger.rationale,
    }


def champion_challenger_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: Iterable[str] | None = None,
    challengers: Iterable[ChallengerSpec] | None = None,
) -> pd.DataFrame:
    if outcomes is None or outcomes.empty:
        return pd.DataFrame()
    if horizons is None:
        if "horizon" not in outcomes.columns:
            return pd.DataFrame()
        preferred = ["1m", "3m", "6m", "1y", "2y"]
        present = {str(x) for x in outcomes["horizon"].dropna().tolist()}
        horizon_list = [h for h in preferred if h in present]
    else:
        horizon_list = [str(h) for h in horizons]
    specs = list(challengers or default_short_challengers())
    rows = [
        compare_short_challenger(recommendations, outcomes, horizon, spec)
        for spec in specs for horizon in horizon_list
    ]
    return pd.DataFrame(rows)


def challenger_governance(table: pd.DataFrame) -> pd.DataFrame:
    """Aggregate horizon comparisons into manual review actions.

    A challenger never becomes production automatically. Even a challenger that wins
    on multiple horizons is only eligible for continued prospective testing.
    """
    if table is None or table.empty:
        return pd.DataFrame(columns=[
            "Challenger", "Åtgärd", "Utvärderade horisonter", "Bättre horisonter",
            "Sämre horisonter", "Största oberoende sample", "Skäl",
        ])
    rows: list[dict[str, Any]] = []
    for name, group in table.groupby("Challenger", sort=False):
        evaluated = group[group["Status"].isin({STATUS_BETTER, STATUS_WORSE, STATUS_TIE})]
        better = int((evaluated["Status"] == STATUS_BETTER).sum())
        worse = int((evaluated["Status"] == STATUS_WORSE).sum())
        n_eval = int(len(evaluated))
        max_cases = int(pd.to_numeric(group["Oberoende case"], errors="coerce").fillna(0).max())

        if n_eval < MIN_REVIEW_HORIZONS or max_cases < MIN_HORIZON_CASES:
            action = ACTION_WAIT
            reason = "För få mogna oberoende case eller horisonter för en rättvis champion–challenger-jämförelse."
        elif better >= MIN_REVIEW_HORIZONS and worse == 0:
            action = ACTION_CONTINUE
            reason = (
                f"Challengern är bättre på {better} av {n_eval} utvärderade horisonter utan en tydligt sämre horisont. "
                "Den får fortsätta som kandidat, men ska inte ersätta champion utan ny prospektiv evidens."
            )
        elif worse >= MIN_REVIEW_HORIZONS and better == 0:
            action = ACTION_KEEP
            reason = (
                f"Nuvarande champion är bättre på {worse} av {n_eval} utvärderade horisonter. "
                "Challengern bör inte gå vidare på detta underlag."
            )
        else:
            action = ACTION_UNCLEAR
            reason = (
                f"Resultaten är blandade: {better} bättre och {worse} sämre horisonter. "
                "Behåll champion och samla mer point-in-time-historik."
            )
        rows.append({
            "Challenger": name,
            "Åtgärd": action,
            "Utvärderade horisonter": n_eval,
            "Bättre horisonter": better,
            "Sämre horisonter": worse,
            "Största oberoende sample": max_cases,
            "Skäl": reason,
        })
    priority = {ACTION_CONTINUE: 0, ACTION_KEEP: 1, ACTION_UNCLEAR: 2, ACTION_WAIT: 3}
    out = pd.DataFrame(rows)
    out["_order"] = out["Åtgärd"].map(priority).fillna(9)
    return out.sort_values(["_order", "Challenger"], kind="stable").drop(columns="_order").reset_index(drop=True)


def challenger_summary(governance: pd.DataFrame) -> dict[str, str]:
    if governance is None or governance.empty:
        return {"status": ACTION_WAIT, "text": "Det finns ännu ingen mogen historik för champion–challenger-test."}
    candidates = governance[governance["Åtgärd"].eq(ACTION_CONTINUE)]
    if not candidates.empty:
        names = ", ".join(candidates["Challenger"].head(2).astype(str))
        return {
            "status": ACTION_CONTINUE,
            "text": f"{names} har slagit nuvarande champion på flera horisonter och får fortsätta som challenger. Produktionsmodellen ändras inte.",
        }
    keep = governance[governance["Åtgärd"].eq(ACTION_KEEP)]
    if not keep.empty:
        return {
            "status": ACTION_KEEP,
            "text": "Nuvarande champion står sig bättre än minst en challenger på flera horisonter. Ingen modelländring rekommenderas.",
        }
    unclear = governance[governance["Åtgärd"].eq(ACTION_UNCLEAR)]
    if not unclear.empty:
        return {
            "status": ACTION_UNCLEAR,
            "text": "Challenger-resultaten är blandade. Borsify behåller champion och samlar mer prospektiv historik.",
        }
    return {"status": ACTION_WAIT, "text": "Historiken är fortfarande för tunn för champion–challenger-beslut."}
