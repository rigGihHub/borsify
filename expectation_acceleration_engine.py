from __future__ import annotations

"""Expectation Acceleration Engine.

Detects when positive analyst expectations are improving *faster recently* than over
an older comparison window. This is a discovery doorway, never an investment score.
The engine only uses point-in-time data available in the current analyst tables.
Missing evidence cannot qualify a candidate.
"""

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _pick_row(frame: pd.DataFrame | None, preferred: tuple[str, ...] = ("+1y", "0y", "+1q", "0q")) -> pd.Series:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=object)
    lookup = {str(i).strip().lower(): i for i in frame.index}
    for key in preferred:
        original = lookup.get(key.lower())
        if original is not None:
            row = frame.loc[original]
            return row if isinstance(row, pd.Series) else pd.Series(row)
    row = frame.iloc[0]
    return row if isinstance(row, pd.Series) else pd.Series(row)


def _col(row: pd.Series, aliases: Iterable[str]) -> float:
    if row.empty:
        return np.nan
    lookup = {str(c).strip().lower(): c for c in row.index}
    for alias in aliases:
        original = lookup.get(str(alias).strip().lower())
        if original is not None:
            value = _num(row.get(original))
            if np.isfinite(value):
                return value
    return np.nan


def _change(current: float, previous: float) -> float:
    if np.isfinite(current) and np.isfinite(previous) and previous != 0:
        return current / previous - 1.0
    return np.nan


def build_expectation_acceleration(
    eps_trend: pd.DataFrame | None,
    eps_revisions: pd.DataFrame | None,
    inflection_metrics: dict[str, Any] | None = None,
    scan_row: pd.Series | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify recent acceleration in expectations without creating a score.

    We compare the current estimate with 7- and 30-day snapshots when available.
    Because the 7-day window is nested inside 30 days, acceleration is treated as
    verified only when the recent change is both positive and unusually concentrated
    in the latest week. Revision breadth is an independent confirmation channel.
    """
    metrics = inflection_metrics or {}
    scan = scan_row or {}
    trend = _pick_row(eps_trend)
    revisions = _pick_row(eps_revisions)

    current = _col(trend, ["current", "currentEstimate", "avg"])
    ago7 = _col(trend, ["7daysAgo", "7DaysAgo", "7dAgo"])
    ago30 = _col(trend, ["30daysAgo", "30DaysAgo", "30dAgo"])
    ch7 = _change(current, ago7)
    ch30 = _change(current, ago30)

    up7 = _col(revisions, ["upLast7days", "upLast7Days"])
    down7 = _col(revisions, ["downLast7days", "downLast7Days"])
    up30 = _col(revisions, ["upLast30days", "upLast30Days"])
    down30 = _col(revisions, ["downLast30days", "downLast30Days"])

    total7 = (up7 if np.isfinite(up7) else 0.0) + (down7 if np.isfinite(down7) else 0.0)
    total30 = (up30 if np.isfinite(up30) else 0.0) + (down30 if np.isfinite(down30) else 0.0)
    balance7 = ((up7 if np.isfinite(up7) else 0.0) - (down7 if np.isfinite(down7) else 0.0)) / total7 if total7 > 0 else np.nan
    recent_share = total7 / total30 if total30 > 0 else np.nan

    reliability = _num(metrics.get("Estimat tillförlitlighetsvikt"))
    analysts = _num(metrics.get("Analytiker antal"))
    fundamental_count = _num(scan.get("Fundamental förändring antal"))

    usable = np.isfinite(reliability) and reliability >= 0.40 and ((np.isfinite(analysts) and analysts >= 2) or total30 >= 2)

    # Recent estimates need to be materially positive and concentrated in the latest
    # week. A 7d move that is at least 55% of the full 30d move is meaningful because
    # the windows overlap; it means much of the monthly revision happened very recently.
    estimate_accel = (
        np.isfinite(ch7) and ch7 >= 0.012 and
        ((np.isfinite(ch30) and ch30 > 0 and ch7 >= 0.55 * ch30) or (not np.isfinite(ch30)) or ch30 <= 0)
    )
    revision_accel = (
        np.isfinite(balance7) and balance7 >= 0.50 and total7 >= 2 and
        ((np.isfinite(recent_share) and recent_share >= 0.35) or total30 <= total7)
    )
    fundamental_support = np.isfinite(fundamental_count) and fundamental_count >= 1

    candidate = bool(usable and estimate_accel and (revision_accel or fundamental_support))
    strong = bool(candidate and revision_accel and fundamental_support)

    if not usable:
        status = "För lite verifierbar estimathistorik"
        why = "Borsify saknar tillräckligt bred och tillförlitlig analytikerdata för att bedöma acceleration."
    elif strong:
        status = "Förväntningar accelererar · fundamenta bekräftar"
        why = "Vinstestimaten förbättras snabbare den senaste veckan, revisionsbredden är positiv och bolagets fundamenta förbättras samtidigt."
    elif candidate and revision_accel:
        status = "Förväntningar accelererar"
        why = "En stor del av den positiva estimatförändringen har kommit nyligen och flera revideringar pekar åt samma håll."
    elif candidate and fundamental_support:
        status = "Estimaten accelererar · fundamenta stödjer"
        why = "Vinstestimaten förbättras snabbare nyligen samtidigt som den breda fundamentala radarn visar förbättring."
    elif np.isfinite(ch7) and ch7 < -0.01:
        status = "Förväntningarna försämras snabbt"
        why = "Vinstestimaten har sänkts tydligt under den senaste veckan och får ingen discovery-fördel."
    else:
        status = "Ingen verifierad acceleration"
        why = "Borsify ser ännu inte tillräckligt tydlig acceleration i estimat eller revisionsbredd."

    return {
        "Förväntningsacceleration status": status,
        "Förväntningsacceleration kandidat": candidate,
        "Förväntningsacceleration stark": strong,
        "EPS förändring 7d": ch7,
        "EPS förändring 30d": ch30,
        "Revisionsbalans 7d": balance7,
        "Andel revideringar senaste 7d": recent_share,
        "Förväntningsacceleration förklaring": why,
    }


def select_expectation_acceleration_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    """Return deterministic acceleration candidates, with no aggregate score."""
    if df is None or df.empty or quota <= 0 or "Förväntningsacceleration kandidat" not in df.columns:
        return []
    work = df[df["Förväntningsacceleration kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__strong"] = work.get("Förväntningsacceleration stark", False).fillna(False).astype(int)
    work["__7d"] = pd.to_numeric(work.get("EPS förändring 7d"), errors="coerce").fillna(-99)
    work["__bal7"] = pd.to_numeric(work.get("Revisionsbalans 7d"), errors="coerce").fillna(-99)
    work["__fund"] = pd.to_numeric(work.get("Fundamental förändring antal"), errors="coerce").fillna(-1)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    work = work.sort_values(["__strong", "__fund", "__bal7", "__7d", "__ticker"], ascending=[False, False, False, False, True], kind="mergesort")
    return [(idx, "Förväntningsacceleration") for idx in work.head(int(quota)).index]
