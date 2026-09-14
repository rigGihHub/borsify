from __future__ import annotations
"""Compress Borsify's internal evidence into a user-facing decision brief.

The brief is presentation-only. It does not create a score, upgrade a signal or
participate in ranking. Every sentence is derived from an existing frozen field.
"""

from typing import Any

import pandas as pd


_EMPTY = {"", "—", "-", "nan", "none"}


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _EMPTY else text


def _first(row: pd.Series | dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return default


def build_decision_brief(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    decision = _first(row, "Signal", "Decision Support action", default="BEVAKA")
    decision_short = _first(row, "Signal kort", "Decision Support", default="Otillräckligt underlag för ett tydligt beslut")

    thesis = _first(
        row, "Varför köpa", "Horisontförklaring", "Affärsläge förklaring",
        default="Ingen tillräckligt tydlig affärstes är verifierad.",
    )
    market_wrong = _first(
        row, "Market-Implied Expectations förklaring", "Market Blind Spot reasons", "Early Mispricing stöd", "Value Trap stöd",
        default="Borsify kan inte verifiera varför marknaden skulle ha fel.",
    )
    expectations = _first(
        row, "Market-Implied Expectations", default="❔ Marknadens förväntningsbörda kan inte bedömas",
    )
    recognition = _first(
        row, "Catalyst-to-Recognition reasons", "Catalyst Why Now", "Varför nu",
        default="Ingen konkret väg till omvärdering är verifierad.",
    )
    timing = _first(
        row, "Recognition Window", default="❔ Recognition-timing okänd",
    )
    payoff = _first(
        row, "Recognition Window payoff", default="— Uppsida/väntetid kan inte bedömas",
    )
    risk = _first(
        row, "Största risk", "Riskflaggor", "Value Trap varningar",
        default="Ingen specifik risk är verifierad; bolags- och marknadsrisk kvarstår.",
    )
    invalidation = _first(
        row, "Vad ändrar Borsifys syn", "Vänta på",
        default="Ompröva om verksamhetsförbättringen uteblir eller riskbilden försämras.",
    )
    confidence = _first(row, "Analysis Confidence", default="— Datatillit okänd")

    return {
        "Decision Brief beslut": decision,
        "Decision Brief kort": decision_short,
        "Decision Brief tes": thesis,
        "Decision Brief market wrong": market_wrong,
        "Decision Brief expectations": expectations,
        "Decision Brief recognition": recognition,
        "Decision Brief timing": timing,
        "Decision Brief payoff": payoff,
        "Decision Brief risk": risk,
        "Decision Brief invalidation": invalidation,
        "Decision Brief confidence": confidence,
    }


def add_decision_briefs(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    extra = pd.DataFrame([build_decision_brief(row) for _, row in out.iterrows()], index=out.index)
    overlap = [column for column in extra.columns if column in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
