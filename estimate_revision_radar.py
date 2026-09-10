from __future__ import annotations

"""Estimate Revision Radar 2.0.

A transparent discovery doorway for analyst estimate changes. This module deliberately
creates no investment score. It classifies only point-in-time estimate evidence that is
already present on a row and can reserve a small number of candidates for deep review.
"""

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def assess_estimate_revision(row: dict[str, Any] | pd.Series) -> dict[str, Any]:
    eps = _num(row.get("EPS-estimat förändring"))
    balance = _num(row.get("EPS-revisionsbalans"))
    weight = _num(row.get("Estimat tillförlitlighetsvikt"))
    analysts = _num(row.get("Analytiker antal"))
    revised = _num(row.get("Reviderande analytiker senaste period"))
    one_month = _num(row.get("1 mån"))

    if not np.isfinite(weight):
        weight = 0.0
    weight = float(np.clip(weight, 0.0, 1.0))

    usable = weight >= 0.40
    eps_up = np.isfinite(eps) and eps >= 0.02
    eps_strong = np.isfinite(eps) and eps >= 0.05
    breadth_up = np.isfinite(balance) and balance >= 0.35
    breadth_bad = np.isfinite(balance) and balance <= -0.35
    eps_bad = np.isfinite(eps) and eps <= -0.02
    enough_breadth = (np.isfinite(analysts) and analysts >= 4) or (np.isfinite(revised) and revised >= 2)

    # A small/normal price response is interesting only when it is not itself a
    # falling-knife signal. A sharp fall despite positive revisions is shown as a
    # conflict and never promoted merely because the price is down.
    muted_price = np.isfinite(one_month) and -0.08 <= one_month <= 0.08
    sharp_price_fall = np.isfinite(one_month) and one_month < -0.08

    candidate = False
    underreaction = False
    status = "Ingen tydlig estimatförändring"
    why = "Borsify kan inte verifiera en bred positiv förändring i analytikernas vinstprognoser."

    if not usable:
        status = "För lite verifierbar analytikerdata"
        why = "Analytikertäckningen är för tunn för att estimatrevideringar ska få en discovery-fördel."
    elif eps_bad or breadth_bad:
        status = "Estimaten försämras"
        why = "Vinstprognoserna eller revisionsbredden har vänt ned och får därför ingen positiv discovery-fördel."
    elif (eps_up or breadth_up) and sharp_price_fall:
        status = "Positiva estimat men svag kursreaktion"
        why = "Analytikerdata förbättras, men kursen har fallit tydligt. Borsify kräver förklaring i djupanalysen och kallar inte fallet en fördel."
    elif eps_up and breadth_up and enough_breadth:
        candidate = True
        if muted_price:
            underreaction = True
            status = "Bred estimathöjning · liten kursreaktion"
            why = "Vinstprognoserna höjs samtidigt som fler analytiker höjer än sänker, men kursen har ännu inte rört sig kraftigt."
        elif eps_strong:
            status = "Bred och tydlig estimathöjning"
            why = "Vinstprognoserna höjs tydligt och revisionsbredden är positiv hos flera analytiker."
        else:
            status = "Bred estimathöjning"
            why = "Vinstprognoserna höjs och revisionsbredden är positiv hos flera analytiker."
    elif (eps_up or breadth_up) and enough_breadth:
        candidate = True
        status = "Positiv estimatrevidering"
        why = "Analytikerdata pekar uppåt, men förändringen är ännu inte bred nog för den starkaste etiketten."

    return {
        "Estimat Radar status": status,
        "Estimat Radar kandidat": bool(candidate),
        "Estimat Radar underreaktion": bool(candidate and underreaction),
        "Estimat Radar förklaring": why,
    }


def add_estimate_revision_radar(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    records = [assess_estimate_revision(row) for _, row in out.iterrows()]
    extra = pd.DataFrame(records, index=out.index)
    for col in extra.columns:
        out[col] = extra[col]
    return out


def select_estimate_revision_candidates(df: pd.DataFrame, quota: int = 2) -> list[tuple[Any, str]]:
    """Return a small deterministic candidate set without calculating a new score."""
    if df is None or df.empty or quota <= 0:
        return []
    work = add_estimate_revision_radar(df) if "Estimat Radar kandidat" not in df.columns else df.copy()
    eligible = work[work["Estimat Radar kandidat"].fillna(False).astype(bool)].copy()
    if eligible.empty:
        return []

    eligible["__under"] = eligible["Estimat Radar underreaktion"].fillna(False).astype(int)
    eligible["__weight"] = pd.to_numeric(eligible.get("Estimat tillförlitlighetsvikt"), errors="coerce").fillna(-1)
    eligible["__balance"] = pd.to_numeric(eligible.get("EPS-revisionsbalans"), errors="coerce").fillna(-99)
    eligible["__eps"] = pd.to_numeric(eligible.get("EPS-estimat förändring"), errors="coerce").fillna(-99)
    eligible["__analysts"] = pd.to_numeric(eligible.get("Analytiker antal"), errors="coerce").fillna(-1)
    eligible["__ticker"] = eligible.get("Ticker", pd.Series("", index=eligible.index)).astype(str)
    eligible = eligible.sort_values(
        ["__under", "__weight", "__balance", "__eps", "__analysts", "__ticker"],
        ascending=[False, False, False, False, False, True],
        kind="mergesort",
    )
    return [(idx, "Estimatförändring") for idx in eligible.head(quota).index]
