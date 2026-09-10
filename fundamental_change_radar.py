from __future__ import annotations

"""Fundamental Change Radar.

Detects *changes* in broad-scan fundamentals by comparing today's point-in-time
snapshot with the latest previously frozen snapshot for the same symbol. The radar
is intentionally rule based: it creates labels and a discovery doorway, never a new
aggregate score.
"""

import math
from typing import Any

import numpy as np
import pandas as pd


SNAPSHOT_FIELD_MAP: dict[str, str] = {
    "Omsättningstillväxt": "revenue_growth",
    "Vinsttillväxt": "earnings_growth",
    "Vinstmarginal": "profit_margin",
    "ROE": "roe",
    "FCF-yield": "fcf_yield",
    "Forward P/E": "forward_pe",
}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _date(value: Any) -> pd.Timestamp | None:
    try:
        out = pd.to_datetime(value, errors="coerce")
        if pd.isna(out):
            return None
        return pd.Timestamp(out).normalize()
    except Exception:
        return None


def _change_labels(current: pd.Series | dict[str, Any], previous: pd.Series | dict[str, Any]) -> list[str]:
    """Return only material positive changes. Missing evidence never qualifies."""
    rev, prev_rev = _num(current.get("Omsättningstillväxt")), _num(previous.get("revenue_growth"))
    earn, prev_earn = _num(current.get("Vinsttillväxt")), _num(previous.get("earnings_growth"))
    margin, prev_margin = _num(current.get("Vinstmarginal")), _num(previous.get("profit_margin"))
    roe, prev_roe = _num(current.get("ROE")), _num(previous.get("roe"))

    labels: list[str] = []
    if np.isfinite(rev) and np.isfinite(prev_rev):
        if (rev - prev_rev >= .05 and rev >= .05) or (prev_rev < .03 <= rev and rev >= .08):
            labels.append("Försäljning accelererar")
    if np.isfinite(earn) and np.isfinite(prev_earn):
        if (earn - prev_earn >= .10 and earn >= .08) or (prev_earn < .05 <= earn and earn >= .12):
            labels.append("Vinst accelererar")
    if np.isfinite(margin) and np.isfinite(prev_margin):
        if margin - prev_margin >= .02 and margin > 0:
            labels.append("Marginal förbättras")
    if np.isfinite(roe) and np.isfinite(prev_roe):
        if roe - prev_roe >= .03 and roe >= .10:
            labels.append("Kapitalavkastning förbättras")
    return labels


def add_fundamental_change_radar(
    current: pd.DataFrame,
    history: pd.DataFrame | None,
    captured_date: str | None = None,
    max_history_days: int = 180,
) -> pd.DataFrame:
    """Annotate current broad scan with changes vs latest *older* frozen snapshot.

    Same-day observations are excluded so the current run cannot become its own
    reference. Old missing fields remain missing; they are never reconstructed.
    """
    if current is None or current.empty:
        return current.copy() if isinstance(current, pd.DataFrame) else pd.DataFrame()
    out = current.copy()
    out["Fundamental förändring"] = "Ingen jämförbar historik"
    out["Fundamental förändring detalj"] = "—"
    out["Fundamental förändring antal"] = 0
    out["Fundamental jämförelsedatum"] = "—"

    if history is None or history.empty or "symbol" not in history.columns or "captured_date" not in history.columns:
        return out

    today = _date(captured_date) or pd.Timestamp.now().normalize()
    hist = history.copy()
    hist["__date"] = pd.to_datetime(hist["captured_date"], errors="coerce").dt.normalize()
    hist["__symbol"] = hist["symbol"].astype(str).str.upper().str.strip()
    hist = hist[hist["__date"].notna() & (hist["__date"] < today)].copy()
    if max_history_days > 0:
        hist = hist[(today - hist["__date"]).dt.days <= int(max_history_days)]
    if hist.empty:
        return out
    hist = hist.sort_values("__date", ascending=False).drop_duplicates("__symbol", keep="first")
    by_symbol = {str(r["__symbol"]): r for _, r in hist.iterrows()}

    for idx, row in out.iterrows():
        symbol = str(row.get("Ticker") or "").upper().strip()
        prev = by_symbol.get(symbol)
        if prev is None:
            continue
        labels = _change_labels(row, prev)
        if labels:
            # Two changes are a broad change; one still deserves radar visibility but
            # is not automatically a strong recommendation.
            status = "Flera fundamentala förbättringar" if len(labels) >= 2 else "Fundamental förbättring"
            out.at[idx, "Fundamental förändring"] = status
            out.at[idx, "Fundamental förändring detalj"] = "; ".join(labels[:4])
            out.at[idx, "Fundamental förändring antal"] = int(len(labels))
        else:
            out.at[idx, "Fundamental förändring"] = "Ingen tydlig ny förbättring"
            out.at[idx, "Fundamental förändring detalj"] = "Ingen material positiv förändring mot senaste frysta bredscan"
        out.at[idx, "Fundamental jämförelsedatum"] = str(pd.Timestamp(prev["__date"]).date())
    return out


def select_change_radar_candidates(df: pd.DataFrame, quota: int = 4) -> list[tuple[Any, str]]:
    """Reserve discovery doorways for verified fundamental improvement, no score."""
    if df is None or df.empty or quota <= 0 or "Fundamental förändring antal" not in df.columns:
        return []
    work = df.copy()
    work["__count"] = pd.to_numeric(work["Fundamental förändring antal"], errors="coerce").fillna(0)
    work = work[work["__count"] > 0].copy()
    if work.empty:
        return []
    work["__quality"] = pd.to_numeric(work.get("Kvalitet", np.nan), errors="coerce").fillna(-1e9)
    work["__risk"] = pd.to_numeric(work.get("Risk", np.nan), errors="coerce").fillna(-1e9)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    # Improvement grants access, but among multiple radar names prefer broader change,
    # then already-observed quality/risk. Missing evidence cannot be rewarded.
    work = work.sort_values(["__count", "__quality", "__risk", "__ticker"], ascending=[False, False, False, True])
    return [(idx, "Fundamental förändring") for idx in work.head(int(quota)).index]
