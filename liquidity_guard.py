from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


DAY_HARD_MIN_TURNOVER_MSEK = 2.0
DAY_COMFORT_TURNOVER_MSEK = 10.0
MEDIUM_HARD_MIN_TURNOVER_MSEK = 1.0
MEDIUM_COMFORT_TURNOVER_MSEK = 5.0


def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def assess_liquidity(row: pd.Series | dict[str,Any], horizon: str) -> dict[str,Any]:
    """Coarse execution/liquidity guard from average daily turnover.

    This deliberately does NOT pretend to know live spread, order-book depth,
    slippage or number of trades because Borsify's current Yahoo daily feed does
    not provide them reliably.
    """
    if horizon not in {"day","medium","long","lifetime"}:
        raise ValueError("unknown horizon")

    turnover=_num(row.get("Omsättning MSEK/dag"))
    volume_ratio=_num(row.get("Volymkvot"))

    if horizon in {"long","lifetime"}:
        return {
            "Likviditetskontroll":"INTE HÅRT FILTER",
            "Likviditet godkänd":True,
            "Likviditet omsättning MSEK":turnover,
            "Likviditet förklaring":"Kortfristig handelslikviditet används inte som hårt filter för fleråriga case.",
            "Likviditet begränsning":"Borsify har inte tillförlitlig realtidsspread eller orderboksdjup.",
            "Datafrekvens":"Dagsdata / EOD eller fördröjd",
        }

    hard_min=DAY_HARD_MIN_TURNOVER_MSEK if horizon=="day" else MEDIUM_HARD_MIN_TURNOVER_MSEK
    comfort=DAY_COMFORT_TURNOVER_MSEK if horizon=="day" else MEDIUM_COMFORT_TURNOVER_MSEK

    if not np.isfinite(turnover):
        return {
            "Likviditetskontroll":"FÖR LITE DATA",
            "Likviditet godkänd":False,
            "Likviditet omsättning MSEK":np.nan,
            "Likviditet förklaring":"Borsify kan inte verifiera normal daglig handelsomsättning för aktien.",
            "Likviditet begränsning":"Aktuell spread och orderboksdjup saknas också i dagsdatan.",
            "Datafrekvens":"Dagsdata / EOD eller fördröjd",
        }

    if turnover < hard_min:
        status="FÖR LÅG HANDEL"
        allowed=False
        explanation=(
            f"Den normala handeln är cirka {turnover:.1f} MSEK per dag, under Borsifys "
            f"miniminivå {hard_min:.1f} MSEK för den här korta tidshorisonten."
        )
    elif turnover < comfort:
        status="TUNNARE HANDEL"
        allowed=True
        explanation=(
            f"Den normala handeln är cirka {turnover:.1f} MSEK per dag. Det är över "
            "miniminivån men fortfarande tillräckligt lågt för att köp- och säljkurs kan skilja mer."
        )
    else:
        status="GODTAGBAR HANDEL"
        allowed=True
        explanation=f"Den normala handeln är cirka {turnover:.1f} MSEK per dag."

    if np.isfinite(volume_ratio):
        if volume_ratio >= 1.5:
            explanation += " Den senaste handelsdagen var aktivare än normalt."
        elif volume_ratio < .65:
            explanation += " Den senaste handelsdagen var ovanligt lugn."

    return {
        "Likviditetskontroll":status,
        "Likviditet godkänd":bool(allowed),
        "Likviditet omsättning MSEK":turnover,
        "Likviditet förklaring":explanation,
        "Likviditet begränsning":"Borsify kan inte mäta aktuell spread, orderboksdjup eller verklig slippage med dagens Yahoo-data.",
        "Datafrekvens":"Dagsdata / EOD eller fördröjd",
    }


def add_liquidity_guard(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    q=pd.DataFrame(
        [assess_liquidity(r,horizon) for _,r in out.iterrows()],
        index=out.index,
    )
    overlap=[c for c in q.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(q)


def filter_execution_ready(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    if horizon not in {"day","medium"}:
        return df.copy()
    if "Likviditet godkänd" not in df.columns:
        return df.copy()
    return df[df["Likviditet godkänd"].eq(True)].copy()
