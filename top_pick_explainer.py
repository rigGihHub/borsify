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


def _entry_rank(v: Any) -> int:
    return {"green": 4, "yellow": 3, "orange": 2, "red": 1}.get(str(v or "").lower(), 0)


def _company_rank(v: Any) -> int:
    return {"green": 3, "yellow": 2, "red": 1}.get(str(v or "").lower(), 0)


def _fmt_delta(delta: float, suffix: str = " p") -> str:
    return f"{delta:+.0f}{suffix}" if np.isfinite(delta) else "—"


def _pair_edges(winner: pd.Series, other: pd.Series, score_col: str) -> tuple[list[str], list[str]]:
    """Return observable winner edges and challenger edges.

    The order mirrors Borsify's ranking philosophy: core horizon score first, then
    independent conviction, deal asymmetry/readiness and finally entry/risk context.
    """
    wins: list[str] = []
    losses: list[str] = []

    ws, os = _num(winner.get(score_col)), _num(other.get(score_col))
    if np.isfinite(ws) and np.isfinite(os) and abs(ws - os) >= 0.5:
        (wins if ws > os else losses).append(
            f"högre Borsify-score ({ws:.0f} mot {os:.0f}, {_fmt_delta(ws-os)})" if ws > os
            else f"utmanaren har högre Borsify-score ({os:.0f} mot {ws:.0f})"
        )

    wc, oc = _num(winner.get("Deal Conviction Score")), _num(other.get("Deal Conviction Score"))
    wf, of = _num(winner.get("Deal Conviction oberoende familjer")), _num(other.get("Deal Conviction oberoende familjer"))
    if np.isfinite(wc) and np.isfinite(oc) and abs(wc - oc) >= 3:
        text = f"starkare Deal Conviction ({wc:.0f} mot {oc:.0f})"
        if np.isfinite(wf) and np.isfinite(of):
            text += f" med {wf:.0f} mot {of:.0f} oberoende evidensfamiljer"
        (wins if wc > oc else losses).append(text if wc > oc else f"utmanaren har starkare Deal Conviction ({oc:.0f} mot {wc:.0f})")

    wg, og = _num(winner.get("Affärsläge nivå")), _num(other.get("Affärsläge nivå"))
    if np.isfinite(wg) and np.isfinite(og) and wg != og:
        (wins if wg > og else losses).append("starkare affärsasymmetri" if wg > og else "utmanaren har starkare affärsasymmetri")

    wr, or_ = _num(winner.get("Case Readiness")), _num(other.get("Case Readiness"))
    if np.isfinite(wr) and np.isfinite(or_) and abs(wr-or_) >= 3:
        (wins if wr > or_ else losses).append(
            f"högre case readiness ({wr:.0f} mot {or_:.0f})" if wr > or_ else f"utmanaren har högre case readiness ({or_:.0f} mot {wr:.0f})"
        )

    we, oe = _entry_rank(winner.get("Ingångsläge nivå")), _entry_rank(other.get("Ingångsläge nivå"))
    if we and oe and we != oe:
        (wins if we > oe else losses).append("bättre köpläge just nu" if we > oe else "utmanaren har bättre köpläge just nu")

    wb, ob = _company_rank(winner.get("Bolagsbedömning nivå")), _company_rank(other.get("Bolagsbedömning nivå"))
    if wb and ob and wb != ob:
        (wins if wb > ob else losses).append("starkare bolagsbedömning" if wb > ob else "utmanaren har starkare bolagsbedömning")

    wu, ou = _num(winner.get("Riktkurs potential")), _num(other.get("Riktkurs potential"))
    if np.isfinite(wu) and np.isfinite(ou) and abs(wu-ou) >= .05:
        (wins if wu > ou else losses).append(
            f"större observerad riktkurspotential ({wu:.0%} mot {ou:.0%})" if wu > ou else f"utmanaren har större observerad riktkurspotential ({ou:.0%} mot {wu:.0%})"
        )

    return wins, losses


def explain_top_pick(ranked: pd.DataFrame, score_col: str, horizon: str) -> dict[str, Any]:
    if ranked is None or ranked.empty:
        return {
            "Varför #1": "Ingen kandidat att jämföra.",
            "Förstavalets fördelar": "",
            "Utmanarnas fördelar": "",
            "Jämförelseunderlag": pd.DataFrame(),
        }

    top = ranked.head(3).copy()
    winner = top.iloc[0]
    comparisons: list[str] = []
    challenger_strengths: list[str] = []

    for pos in range(1, len(top)):
        other = top.iloc[pos]
        wins, losses = _pair_edges(winner, other, score_col)
        label = _label(other)
        if wins:
            comparisons.append(f"mot #{pos+1} {label}: " + "; ".join(wins[:3]))
        else:
            comparisons.append(f"mot #{pos+1} {label}: ingen tydlig separat fördel utöver rankningsordningen")
        if losses:
            challenger_strengths.append(f"#{pos+1} {label}: " + "; ".join(losses[:2]))

    headline = f"{_label(winner)} är #1 för {horizon} eftersom "
    if comparisons:
        headline += " | ".join(comparisons) + "."
    else:
        headline += "den är ensam godkänd kandidat i jämförelsen."

    if challenger_strengths:
        headline += " Men förstavalet är inte bäst på allt."

    view_cols = [
        c for c in ["Ticker", "Namn", score_col, "Deal Conviction Score",
                    "Deal Conviction oberoende familjer", "Affärsläge", "Ingångsläge",
                    "Bolagsbedömning", "Case Readiness", "Riktkurs potential"]
        if c in top.columns
    ]
    view = top[view_cols].copy()
    view.insert(0, "#", range(1, len(view)+1))

    return {
        "Varför #1": headline,
        "Förstavalets fördelar": " | ".join(comparisons),
        "Utmanarnas fördelar": " | ".join(challenger_strengths) if challenger_strengths else "Inga tydligt starkare dimensioner identifierade hos #2–#3.",
        "Jämförelseunderlag": view,
    }
