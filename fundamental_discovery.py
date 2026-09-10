from __future__ import annotations

"""Fundamental Discovery 2.0.

Rule-based discovery lenses that broaden the doorway into deep analysis using only
fundamental information already available in the broad scan. They deliberately do
not create another aggregate score: a company either satisfies an auditable rule or
it does not. Deep analysis remains responsible for confirming the case.
"""

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


FUNDAMENTAL_LENSES: tuple[str, ...] = (
    "Lönsam tillväxt",
    "Vinst växer snabbare än försäljning",
    "Kassaflöde + kvalitet",
    "Tillväxt till rimligt pris",
)


def fundamental_discovery_labels(row: pd.Series | dict[str, Any]) -> list[str]:
    """Return transparent qualifying lenses. Missing data never qualifies."""
    rev = _num(row.get("Omsättningstillväxt"))
    earn = _num(row.get("Vinsttillväxt"))
    margin = _num(row.get("Vinstmarginal"))
    roe = _num(row.get("ROE"))
    fcfy = _num(row.get("FCF-yield"))
    debt = _num(row.get("Skuld/eget kapital"))
    fpe = _num(row.get("Forward P/E"))

    labels: list[str] = []

    # Growth that is already profitable and earns a reasonable return on equity.
    if all(np.isfinite(x) for x in [rev, earn, margin, roe]) and rev >= .08 and earn >= .10 and margin >= .08 and roe >= .12:
        labels.append("Lönsam tillväxt")

    # A simple operating-leverage clue: profits are growing materially faster than sales,
    # but only when sales and profitability are already positive.
    if all(np.isfinite(x) for x in [rev, earn, margin]) and rev >= .03 and earn >= .12 and earn - rev >= .07 and margin > 0:
        labels.append("Vinst växer snabbare än försäljning")

    # Cash generation plus quality; debt is a veto only when actually observed as high.
    debt_ok = (not np.isfinite(debt)) or debt <= 150
    if all(np.isfinite(x) for x in [fcfy, margin, roe]) and fcfy >= .04 and margin >= .08 and roe >= .12 and debt_ok:
        labels.append("Kassaflöde + kvalitet")

    # Growth at a non-extreme forward valuation. This is a discovery doorway, not a buy rule.
    if all(np.isfinite(x) for x in [rev, earn, fpe]) and rev >= .10 and earn >= .10 and 0 < fpe <= 30:
        labels.append("Tillväxt till rimligt pris")

    return labels


def add_fundamental_discovery(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    labels = [fundamental_discovery_labels(row) for _, row in out.iterrows()]
    out["Fundamentala upptäcktslinser"] = [", ".join(x) for x in labels]
    out["Fundamental upptäckt antal"] = [len(x) for x in labels]
    return out


def select_fundamental_candidates(df: pd.DataFrame, quota_per_lens: int = 2, max_candidates: int = 6) -> list[tuple[Any, str]]:
    """Reserve a few deep-analysis doorways per fundamental rule, without a score."""
    if df is None or df.empty or quota_per_lens <= 0 or max_candidates <= 0:
        return []
    work = add_fundamental_discovery(df)
    chosen: list[tuple[Any, str]] = []
    seen: set[Any] = set()

    # Within a rule, use existing Borsify Score only as deterministic ordering. The
    # rule itself is what grants access; no new fundamental mega-score is computed.
    for label in FUNDAMENTAL_LENSES:
        mask = work["Fundamentala upptäcktslinser"].astype(str).str.contains(label, regex=False)
        subset = work.loc[mask].copy()
        if subset.empty:
            continue
        subset["__score"] = pd.to_numeric(subset.get("Borsify Score", np.nan), errors="coerce").fillna(-1e9)
        subset["__ticker"] = subset.get("Ticker", pd.Series("", index=subset.index)).astype(str)
        subset = subset.sort_values(["__score", "__ticker"], ascending=[False, True])
        taken = 0
        for idx in subset.index:
            if idx in seen:
                continue
            seen.add(idx)
            chosen.append((idx, label))
            taken += 1
            if taken >= quota_per_lens or len(chosen) >= max_candidates:
                break
        if len(chosen) >= max_candidates:
            break
    return chosen
