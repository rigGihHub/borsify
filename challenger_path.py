from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _label(row: pd.Series | dict[str, Any]) -> str:
    name = str(row.get("Namn") or row.get("Ticker") or "aktien")
    ticker = str(row.get("Ticker") or "").strip()
    return f"{name} ({ticker})" if ticker and ticker not in name else name


def _rank_dimensions(score_col: str, horizon: str) -> list[tuple[str, str, float]]:
    # Mirrors horizon_rankings.py exactly. Epsilon is the smallest meaningful change
    # we present to the user; it is not a forecast of how the underlying inputs move.
    dims = [
        (score_col, "Borsify-score", 0.5),
        ("Deal Conviction Score", "Deal Conviction", 1.0),
        ("Affärsläge rangvärde", "affärsläge", 1.0),
        ("Case Readiness", "Case Readiness", 1.0),
    ]
    if horizon in {"day", "medium"}:
        dims += [
            ("Relativ styrka", "relativ styrka", 0.01),
            ("RR rangvärde", "risk/reward", 1.0),
        ]
    dims.append(("Datatäckning", "datatäckning", 0.01))
    return dims


def _fmt(col: str, value: float) -> str:
    if not np.isfinite(value):
        return "—"
    if col in {"Relativ styrka", "Datatäckning"}:
        return f"{value:.0%}"
    return f"{value:.0f}"


def _practical_watch(row: pd.Series | dict[str, Any]) -> list[str]:
    out: list[str] = []
    entry = str(row.get("Ingångsläge nivå") or "").lower()
    better = str(row.get("Bättre ingång") or "—")
    if entry in {"orange", "red"}:
        if better != "—":
            out.append(f"köpläget förbättras, med Borsifys nuvarande referenszon {better}")
        else:
            out.append("köpläget förbättras från dagens ansträngda nivå")
    neg = str(row.get("Deal Conviction negativa familjer") or "").strip()
    if neg:
        out.append("motstridiga evidensfamiljer försvinner: " + neg)
    return out


def path_to_number_one(winner: pd.Series | dict[str, Any], challenger: pd.Series | dict[str, Any], score_col: str, horizon: str) -> dict[str, Any]:
    """Explain the smallest *observable ranking condition* for a challenger to overtake.

    We do not claim how or when a metric will improve. We only expose the thresholds
    implied by Borsify's current sorting order and present practical watch conditions
    separately from the formal ranking condition.
    """
    dims = _rank_dimensions(score_col, horizon)
    decisive = None
    path_parts: list[str] = []

    for col, label, eps in dims:
        w, c = _num(winner.get(col)), _num(challenger.get(col))
        if not (np.isfinite(w) and np.isfinite(c)):
            continue
        if abs(w - c) <= 1e-12:
            continue
        decisive = (col, label, w, c, eps)
        break

    if decisive is None:
        formal = "Ingen tydlig mätbar rankskillnad i de tillgängliga sorteringsdimensionerna."
        threshold = "—"
        gap = np.nan
    else:
        col, label, w, c, eps = decisive
        gap = w - c
        if c < w:
            # Because sorting is descending and this is the first differing dimension,
            # equality merely moves the decision to the next key. A small epsilon above
            # winner is the clean condition for an outright pass.
            target = w + eps
            formal = (
                f"För att gå om direkt behöver {_label(challenger)} höja {label} "
                f"från {_fmt(col,c)} till minst cirka {_fmt(col,target)} om #1 står still. "
                f"Vid exakt {_fmt(col,w)} avgör nästa rankdimension."
            )
            threshold = _fmt(col, target)
        else:
            # Defensive branch if supplied rows are not currently sorted.
            formal = f"Utmanaren ligger redan före #1 på den första skiljande dimensionen {label}. Kontrollera rankordningen."
            threshold = _fmt(col, c)

    watch = _practical_watch(challenger)
    conviction = _num(challenger.get("Deal Conviction Score"))
    winner_conv = _num(winner.get("Deal Conviction Score"))
    if np.isfinite(conviction) and np.isfinite(winner_conv) and conviction < winner_conv:
        watch.append(f"Deal Conviction närmar sig eller passerar #1:s {winner_conv:.0f}/100")

    fam = _num(challenger.get("Deal Conviction oberoende familjer"))
    wfam = _num(winner.get("Deal Conviction oberoende familjer"))
    if np.isfinite(fam) and np.isfinite(wfam) and fam < wfam:
        watch.append(f"fler oberoende evidensfamiljer bekräftar caset ({fam:.0f} nu mot #1:s {wfam:.0f})")

    return {
        "Utmanare": _label(challenger),
        "Formell väg till #1": formal,
        "Första avgörande dimension": decisive[1] if decisive else "—",
        "Tröskel": threshold,
        "Nuvarande gap": gap,
        "Bevaka också": "; ".join(watch[:4]) if watch else "inga separata praktiska villkor utöver rankmåtten",
    }


def challenger_paths(ranked: pd.DataFrame, score_col: str, horizon: str) -> pd.DataFrame:
    if ranked is None or len(ranked) < 2:
        return pd.DataFrame(columns=["#", "Utmanare", "Formell väg till #1", "Bevaka också"])
    top = ranked.head(3).copy()
    winner = top.iloc[0]
    rows = []
    for pos in range(1, len(top)):
        item = path_to_number_one(winner, top.iloc[pos], score_col, horizon)
        rows.append({"#": pos + 1, **item})
    return pd.DataFrame(rows)
