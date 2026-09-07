from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ValuationProfile:
    name: str
    weights: Mapping[str, float]
    note: str = ""


DEFAULT_PROFILE = ValuationProfile(
    "Balanserad",
    {"P/E": 0.22, "Forward P/E": 0.24, "P/B": 0.12, "EV/EBITDA": 0.20, "FCF-yield": 0.22},
)

PROFILES: dict[str, ValuationProfile] = {
    "financials": ValuationProfile(
        "Bank/finans",
        {"P/E": 0.22, "Forward P/E": 0.28, "P/B": 0.50},
        "EV/EBITDA och FCF-yield används inte som huvudmått för bank/finans.",
    ),
    "real_estate": ValuationProfile(
        "Fastigheter",
        {"Forward P/E": 0.20, "P/B": 0.55, "FCF-yield": 0.25},
        "P/FFO och substansvärde saknas i grunddatan, så fastighetsvärderingen är begränsad.",
    ),
    "growth": ValuationProfile(
        "Tillväxt/tillgångslätt",
        {"P/E": 0.12, "Forward P/E": 0.30, "EV/EBITDA": 0.20, "FCF-yield": 0.38},
        "P/B får låg eller ingen vikt eftersom bokfört kapital ofta säger mindre i tillgångslätta bolag.",
    ),
    "cyclical": ValuationProfile(
        "Cyklisk",
        {"P/E": 0.15, "Forward P/E": 0.15, "P/B": 0.10, "EV/EBITDA": 0.30, "FCF-yield": 0.30},
        "Cykliska vinster kan ligga nära topp eller botten; kontrollera normaliserad vinst före köp.",
    ),
    "utilities": ValuationProfile(
        "Kapitalintensiv/stabil",
        {"P/E": 0.18, "Forward P/E": 0.22, "P/B": 0.10, "EV/EBITDA": 0.28, "FCF-yield": 0.22},
    ),
}


def _sector_key(value: object) -> str:
    sector = str(value or "").strip().lower()
    if any(token in sector for token in ("financial", "bank", "insurance", "finans")):
        return "financials"
    if any(token in sector for token in ("real estate", "reit", "fastighet")):
        return "real_estate"
    if any(token in sector for token in ("technology", "communication", "software", "internet", "teknik")):
        return "growth"
    if any(token in sector for token in ("energy", "basic materials", "materials", "mining", "oil", "gas", "råvar")):
        return "cyclical"
    if any(token in sector for token in ("utilities", "utility", "kraft", "elnät")):
        return "utilities"
    return "default"


def profile_for_sector(value: object) -> ValuationProfile:
    return PROFILES.get(_sector_key(value), DEFAULT_PROFILE)


def _percentile_score(series: pd.Series, higher_is_better: bool) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=s.index, dtype=float)
    valid = s.notna()
    if valid.sum() >= 2:
        pct = s[valid].rank(pct=True, method="average") * 100
        if not higher_is_better:
            pct = 100 - pct + (100 / valid.sum())
        out.loc[valid] = pct.clip(0, 100)
    elif valid.sum() == 1:
        out.loc[valid] = 50.0
    return out


def _peer_score(df: pd.DataFrame, column: str, higher_is_better: bool) -> pd.Series:
    """Use same-sector peers when >=3 valid observations, otherwise whole universe."""
    global_score = _percentile_score(df[column], higher_is_better)
    result = global_score.copy()
    sectors = df.get("Sektor", pd.Series("Okänd", index=df.index)).fillna("Okänd").astype(str)
    for sector, idx in sectors.groupby(sectors).groups.items():
        valid_local = pd.to_numeric(df.loc[idx, column], errors="coerce").notna().sum()
        if sector.lower() == "okänd" or valid_local < 3:
            continue
        result.loc[idx] = _percentile_score(df.loc[idx, column], higher_is_better)
    return result


def sector_aware_valuation(df: pd.DataFrame) -> pd.DataFrame:
    """Return sector-aware valuation score and transparent metadata.

    Only metrics that actually exist for a row contribute to its score. This avoids
    treating missing valuation fields as neutral 50s and then presenting a false sense
    of precision. Scores remain relative screening measures, not intrinsic values.
    """
    if df.empty:
        return pd.DataFrame(index=df.index)

    directions = {
        "P/E": False,
        "Forward P/E": False,
        "P/B": False,
        "EV/EBITDA": False,
        "FCF-yield": True,
    }
    metric_scores = {name: _peer_score(df, name, direction) for name, direction in directions.items()}

    scores: list[float] = []
    profiles: list[str] = []
    coverage: list[float] = []
    metric_counts: list[int] = []
    statuses: list[str] = []
    notes: list[str] = []

    for idx, row in df.iterrows():
        profile = profile_for_sector(row.get("Sektor"))
        numerator = 0.0
        denominator = 0.0
        present_weight = 0.0
        count = 0
        for metric, weight in profile.weights.items():
            raw = pd.to_numeric(pd.Series([row.get(metric)]), errors="coerce").iloc[0]
            score = metric_scores[metric].loc[idx]
            if pd.notna(raw) and pd.notna(score):
                numerator += float(score) * float(weight)
                denominator += float(weight)
                present_weight += float(weight)
                count += 1
        value = numerator / denominator if denominator > 0 else 50.0
        cov = present_weight / sum(profile.weights.values()) if profile.weights else 0.0

        if count >= 3 and cov >= 0.70:
            status = "Bra underlag"
        elif count >= 2 and cov >= 0.45:
            status = "Användbart underlag"
        else:
            status = "Begränsat underlag"
        if _sector_key(row.get("Sektor")) == "real_estate":
            status = "Begränsat underlag" if status == "Bra underlag" else status

        scores.append(round(float(np.clip(value, 0, 100)), 1))
        profiles.append(profile.name)
        coverage.append(round(float(cov), 3))
        metric_counts.append(count)
        statuses.append(status)
        notes.append(profile.note)

    return pd.DataFrame({
        "Värdering": scores,
        "Värderingsprofil": profiles,
        "Värderingsunderlag": statuses,
        "Värderingsmått antal": metric_counts,
        "Värdering täckning": coverage,
        "Värderingsnotis": notes,
    }, index=df.index)
