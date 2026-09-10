from __future__ import annotations

"""Underfollowed Discovery.

A narrow discovery doorway for Nordic companies with *observed low analyst coverage*
and verified point-in-time fundamental improvement. Low coverage is never treated as
a positive signal by itself and missing analyst coverage never qualifies.
"""

import math
from typing import Any

import numpy as np
import pandas as pd


NORDIC_COUNTRIES = frozenset({"Sverige", "Norge", "Danmark", "Finland"})
MAX_ANALYSTS = 3


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def underfollowed_assessment(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    country = str(row.get("Land") or "").strip()
    analysts = _num(row.get("Analytiker antal", row.get("Antal analytiker")))
    improvements = _num(row.get("Fundamental förändring antal"))
    detail = str(row.get("Fundamental förändring detalj") or "").strip()

    observed_coverage = np.isfinite(analysts)
    nordic = country in NORDIC_COUNTRIES
    low_coverage = observed_coverage and 0 <= analysts <= MAX_ANALYSTS
    improving = np.isfinite(improvements) and improvements >= 1
    candidate = bool(nordic and low_coverage and improving)

    if not nordic:
        status = "Utanför Norden"
        why = "Underfollowed Discovery är avgränsad till nordiska bolag."
    elif not observed_coverage:
        status = "Analytikertäckning saknas"
        why = "Saknad analystäckning får inte tolkas som låg bevakning."
    elif analysts > MAX_ANALYSTS:
        status = "Tillräckligt bevakad"
        why = f"{int(analysts)} analytiker följer bolaget; låg bevakning ger därför ingen särskild discovery-väg."
    elif analysts < 0:
        status = "Analytikertäckning saknas"
        why = "Ogiltig analystäckning får inte ge discovery-fördel."
    elif not improving:
        status = "Låg bevakning utan verifierad förbättring"
        why = "Få analytiker räcker inte. Borsify kräver en verifierad fundamental förbättring mot en äldre fryst bredscan."
    else:
        status = "Underfollowed fundamental förbättring"
        bits = detail if detail and detail != "—" else f"{int(improvements)} verifierad fundamental förbättring"
        why = f"Endast {int(analysts)} analytiker följer bolaget samtidigt som Borsify ser: {bits}. Låg bevakning är kontext, inte en köpsignal."

    return {
        "Underfollowed status": status,
        "Underfollowed kandidat": candidate,
        "Underfollowed analytiker": analysts,
        "Underfollowed förbättringar": improvements if np.isfinite(improvements) else np.nan,
        "Underfollowed förklaring": why,
    }


def add_underfollowed_discovery(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    rows = [underfollowed_assessment(row) for _, row in out.iterrows()]
    for key in rows[0]:
        out[key] = [r[key] for r in rows]
    return out


def select_underfollowed_candidates(df: pd.DataFrame, quota: int = 3) -> list[tuple[Any, str]]:
    """Reserve a few deep-analysis slots; low analyst count itself never ranks names."""
    if df is None or df.empty or quota <= 0:
        return []
    work = add_underfollowed_discovery(df)
    work = work[work["Underfollowed kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__change"] = pd.to_numeric(work.get("Fundamental förändring antal"), errors="coerce").fillna(-1)
    work["__quality"] = pd.to_numeric(work.get("Kvalitet"), errors="coerce").fillna(-1e9)
    work["__risk"] = pd.to_numeric(work.get("Risk"), errors="coerce").fillna(-1e9)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    # Do not sort by analyst count: having fewer analysts must not itself be rewarded.
    work = work.sort_values(["__change", "__quality", "__risk", "__ticker"], ascending=[False, False, False, True])
    return [(idx, "Underfollowed förbättring") for idx in work.head(int(quota)).index]
