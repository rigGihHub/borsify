from __future__ import annotations

"""Consensus Change Engine.

A transparent discovery layer for changes in the *breadth* of analyst opinion.
It deliberately avoids a new aggregate investment score. Missing analyst history
stays missing; current target-price dispersion is descriptive until Borsify has
point-in-time history to compare against.
"""

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "").replace(" ", "")


def _col(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    if frame is None or frame.empty:
        return None
    lookup = {_norm(c): c for c in frame.columns}
    for alias in aliases:
        if _norm(alias) in lookup:
            return lookup[_norm(alias)]
    return None


def _recommendation_rows(frame: pd.DataFrame | None) -> tuple[pd.Series, pd.Series]:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=object), pd.Series(dtype=object)
    work = frame.copy()
    period_col = _col(work, ("period", "Period"))
    periods = work[period_col].astype(str) if period_col else pd.Series(work.index.astype(str), index=work.index)

    def rank_period(text: str) -> int:
        t = str(text).strip().lower()
        mapping = {"0m": 0, "current": 0, "-1m": 1, "1m": 1, "-2m": 2, "2m": 2, "-3m": 3, "3m": 3}
        return mapping.get(t, 99)

    ranked = sorted([(rank_period(p), i) for i, p in periods.items()], key=lambda x: x[0])
    current_idx = ranked[0][1] if ranked and ranked[0][0] < 99 else work.index[0]
    previous_idx = next((i for rank, i in ranked if rank > 0 and rank < 99), None)
    if previous_idx is None and len(work) > 1:
        previous_idx = work.index[1]
    current = work.loc[current_idx]
    previous = work.loc[previous_idx] if previous_idx is not None else pd.Series(dtype=object)
    return current, previous


def _recommendation_state(row: pd.Series) -> dict[str, float]:
    if row is None or row.empty:
        return {"total": np.nan, "bull": np.nan, "bear": np.nan, "net": np.nan}
    lookup = {_norm(c): c for c in row.index}

    def value(*aliases: str) -> float:
        for alias in aliases:
            c = lookup.get(_norm(alias))
            if c is not None:
                x = _num(row.get(c))
                if np.isfinite(x):
                    return max(0.0, x)
        return 0.0

    strong_buy = value("strongBuy", "strong buy")
    buy = value("buy")
    hold = value("hold")
    sell = value("sell")
    strong_sell = value("strongSell", "strong sell")
    total = strong_buy + buy + hold + sell + strong_sell
    if total <= 0:
        return {"total": np.nan, "bull": np.nan, "bear": np.nan, "net": np.nan}
    bull = (strong_buy + buy) / total
    bear = (sell + strong_sell) / total
    return {"total": total, "bull": bull, "bear": bear, "net": bull - bear}


def _recent_actions(frame: pd.DataFrame | None, as_of: str | pd.Timestamp | None, lookback_days: int = 45) -> dict[str, Any]:
    empty = {"up": 0, "down": 0, "init": 0, "firms": 0, "balance": np.nan, "observed": 0}
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return empty
    work = frame.copy()
    date_col = _col(work, ("GradeDate", "date", "Date", "gradedate"))
    if date_col:
        dates = pd.to_datetime(work[date_col], errors="coerce", utc=True)
    else:
        dates = pd.to_datetime(pd.Series(work.index, index=work.index), errors="coerce", utc=True)
    ref = pd.Timestamp(as_of if as_of is not None else datetime.now(timezone.utc))
    if ref.tzinfo is None:
        ref = ref.tz_localize("UTC")
    else:
        ref = ref.tz_convert("UTC")
    age = (ref - dates).dt.total_seconds() / 86400.0
    work = work[(age >= 0) & (age <= lookback_days)].copy()
    if work.empty:
        return empty

    action_col = _col(work, ("Action", "action"))
    firm_col = _col(work, ("Firm", "firm", "Brokerage", "brokerage"))
    actions = work[action_col].astype(str).str.lower().str.strip() if action_col else pd.Series("", index=work.index)

    up_mask = actions.str.contains(r"upgrade|\bup\b|raise", regex=True)
    down_mask = actions.str.contains(r"downgrade|\bdown\b|lower", regex=True)
    init_mask = actions.str.contains(r"init|initiated|coverage", regex=True)
    up = int(up_mask.sum())
    down = int(down_mask.sum())
    init = int(init_mask.sum())
    directional = up + down
    balance = (up - down) / directional if directional else np.nan
    firms = int(work[firm_col].dropna().astype(str).str.strip().replace("", np.nan).dropna().nunique()) if firm_col else 0
    return {"up": up, "down": down, "init": init, "firms": firms, "balance": balance, "observed": int(len(work))}


def _price_targets(targets: dict[str, Any] | pd.Series | None, price: Any = None) -> dict[str, float]:
    if targets is None:
        return {"mean": np.nan, "median": np.nan, "high": np.nan, "low": np.nan, "dispersion": np.nan, "upside": np.nan}
    data = targets.to_dict() if isinstance(targets, pd.Series) else dict(targets) if isinstance(targets, dict) else {}
    norm = {_norm(k): v for k, v in data.items()}

    def get(*aliases: str) -> float:
        for a in aliases:
            if _norm(a) in norm:
                x = _num(norm[_norm(a)])
                if np.isfinite(x):
                    return x
        return np.nan

    mean = get("mean", "meanPrice", "targetMeanPrice", "current")
    median = get("median", "medianPrice", "targetMedianPrice")
    high = get("high", "highPrice", "targetHighPrice")
    low = get("low", "lowPrice", "targetLowPrice")
    dispersion = (high - low) / abs(mean) if np.isfinite(high) and np.isfinite(low) and np.isfinite(mean) and mean != 0 else np.nan
    px = _num(price)
    upside = mean / px - 1.0 if np.isfinite(mean) and np.isfinite(px) and px > 0 else np.nan
    return {"mean": mean, "median": median, "high": high, "low": low, "dispersion": dispersion, "upside": upside}


def build_consensus_change(
    recommendation_summary: pd.DataFrame | None,
    upgrades_downgrades: pd.DataFrame | None,
    analyst_price_targets: dict[str, Any] | pd.Series | None = None,
    scan_row: pd.Series | dict[str, Any] | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Describe whether analyst consensus is broadening or weakening.

    Positive candidates require breadth/change across multiple analysts. A single
    target-price change or recommendation never qualifies. Current target-price
    dispersion is descriptive only; it is not called a *change* until PIT history exists.
    """
    current_row, previous_row = _recommendation_rows(recommendation_summary)
    current = _recommendation_state(current_row)
    previous = _recommendation_state(previous_row)
    delta = current["net"] - previous["net"] if np.isfinite(current["net"]) and np.isfinite(previous["net"]) else np.nan

    actions = _recent_actions(upgrades_downgrades, as_of=as_of, lookback_days=45)
    scan = scan_row if scan_row is not None else {}
    price = scan.get("Pris") if hasattr(scan, "get") else None
    targets = _price_targets(analyst_price_targets, price)

    current_n = current["total"]
    reliable_summary = np.isfinite(current_n) and current_n >= 4
    reliable_actions = actions["firms"] >= 2 and actions["observed"] >= 2
    usable = bool(reliable_summary or reliable_actions)

    breadth_up = bool(np.isfinite(delta) and delta >= 0.08 and reliable_summary)
    breadth_down = bool(np.isfinite(delta) and delta <= -0.08 and reliable_summary)
    upgrades_broad = bool(actions["up"] >= 2 and np.isfinite(actions["balance"]) and actions["balance"] >= 0.50 and actions["firms"] >= 2)
    downgrades_broad = bool(actions["down"] >= 2 and np.isfinite(actions["balance"]) and actions["balance"] <= -0.50 and actions["firms"] >= 2)
    new_coverage = bool(actions["init"] >= 2 and actions["firms"] >= 2)

    negative = bool(breadth_down or downgrades_broad)
    candidate = bool(usable and not negative and (breadth_up or upgrades_broad) and (reliable_summary or reliable_actions))
    strong = bool(candidate and breadth_up and upgrades_broad)

    if not usable:
        status = "För lite verifierbar konsensusdata"
        why = "Borsify saknar tillräckligt bred analytikertäckning eller flera oberoende färska analyshändelser."
    elif strong:
        status = "Konsensus förbättras brett"
        why = "Andelen positiva rekommendationer förbättras samtidigt som flera analytiker nyligen har höjt sin syn."
    elif candidate and breadth_up:
        status = "Rekommendationsbredden förbättras"
        why = "Analytikerkollektivet har blivit tydligt mer positivt jämfört med närmast tillgängliga tidigare konsensusperiod."
    elif candidate and upgrades_broad:
        status = "Flera analytiker höjer"
        why = "Minst två oberoende analyshus har nyligen höjt sin syn och sänkningar dominerar inte."
    elif negative and breadth_down and downgrades_broad:
        status = "Konsensus försämras brett"
        why = "Både rekommendationsbredden och flera färska analyshändelser pekar nedåt."
    elif negative:
        status = "Konsensus försvagas"
        why = "Borsify ser en tydlig negativ förändring i rekommendationsbredd eller flera färska nedgraderingar."
    elif new_coverage:
        status = "Bevakningen breddas"
        why = "Flera analyshus har nyligen initierat bevakning, men det räcker inte i sig för en positiv discovery-fördel."
    else:
        status = "Ingen bred konsensusförändring"
        why = "Det finns inte ännu en tillräckligt bred förändring mellan flera analytiker för att ge discovery-fördel."

    return {
        "Konsensusförändring status": status,
        "Konsensusförändring kandidat": candidate,
        "Konsensusförändring stark": strong,
        "Konsensusförändring varning": negative,
        "Konsensus bullish andel": current["bull"],
        "Konsensus bearish andel": current["bear"],
        "Konsensus net breadth": current["net"],
        "Konsensus breadth förändring": delta,
        "Konsensus analytiker antal": current_n,
        "Konsensus uppgraderingar 45d": actions["up"],
        "Konsensus nedgraderingar 45d": actions["down"],
        "Konsensus initierad bevakning 45d": actions["init"],
        "Konsensus aktiva analyshus 45d": actions["firms"],
        "Konsensus åtgärdsbalans 45d": actions["balance"],
        "Riktkurs medel": targets["mean"],
        "Riktkurs median": targets["median"],
        "Riktkurs hög": targets["high"],
        "Riktkurs låg": targets["low"],
        "Riktkurs dispersion": targets["dispersion"],
        "Riktkurs potential": targets["upside"],
        "Konsensusförändring förklaring": why,
    }


def select_consensus_change_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    """Return deterministic positive consensus-change candidates; never a score."""
    if df is None or df.empty or quota <= 0 or "Konsensusförändring kandidat" not in df.columns:
        return []
    work = df[df["Konsensusförändring kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__strong"] = work.get("Konsensusförändring stark", False).fillna(False).astype(int)
    work["__breadth"] = pd.to_numeric(work.get("Konsensus breadth förändring"), errors="coerce").fillna(-99)
    work["__balance"] = pd.to_numeric(work.get("Konsensus åtgärdsbalans 45d"), errors="coerce").fillna(-99)
    work["__up"] = pd.to_numeric(work.get("Konsensus uppgraderingar 45d"), errors="coerce").fillna(-1)
    work["__firms"] = pd.to_numeric(work.get("Konsensus aktiva analyshus 45d"), errors="coerce").fillna(-1)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    work = work.sort_values(
        ["__strong", "__breadth", "__balance", "__up", "__firms", "__ticker"],
        ascending=[False, False, False, False, False, True],
        kind="mergesort",
    )
    return [(idx, "Konsensusförändring") for idx in work.head(int(quota)).index]
