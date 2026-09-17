from __future__ import annotations

import pandas as pd

from anti_chase_gate import anti_chase_decision
from buy_quality_gate import apply_buy_gate


def select_buy_now(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Single safe selector for user-facing Köp nu lists.

    Keeps company quality and entry timing separate: a strong company that has
    already surged may remain interesting, but it must not be labelled Köp nu.
    """
    gated = apply_buy_gate(df, horizon)
    if gated is None or gated.empty:
        return gated
    gated = gated[gated["Köpfilter godkänd"].eq(True)].copy()
    if gated.empty:
        return gated

    anti_horizon = "year" if horizon == "long" else horizon
    decisions = [anti_chase_decision(row, anti_horizon) for _, row in gated.iterrows()]
    anti = pd.DataFrame(decisions, index=gated.index)
    overlap = [column for column in anti.columns if column in gated.columns]
    if overlap:
        gated = gated.drop(columns=overlap)
    gated = gated.join(anti)
    return gated[gated["Köp nu efter rusning"].eq(True)].copy()


def select_good_but_wait(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Strong cases blocked only because today's entry is too stretched."""
    gated = apply_buy_gate(df, horizon)
    if gated is None or gated.empty:
        return gated
    gated = gated[gated["Köpfilter godkänd"].eq(True)].copy()
    if gated.empty:
        return gated
    anti_horizon = "year" if horizon == "long" else horizon
    decisions = [anti_chase_decision(row, anti_horizon) for _, row in gated.iterrows()]
    anti = pd.DataFrame(decisions, index=gated.index)
    overlap = [column for column in anti.columns if column in gated.columns]
    if overlap:
        gated = gated.drop(columns=overlap)
    gated = gated.join(anti)
    return gated[gated["Köp nu efter rusning"].eq(False)].copy()
