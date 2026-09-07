from __future__ import annotations

import math
from typing import Any

import pandas as pd

# Trading-session horizons used by the ledger. Calendar spacing is deliberately
# conservative: a repeated signal is not treated as new evidence while the prior
# signal's forward outcome window is still open.
HORIZON_TRADING_DAYS = {"1m": 21, "3m": 63, "6m": 126, "1y": 252, "2y": 504}


def _calendar_days(horizon: str) -> int:
    trading_days = HORIZON_TRADING_DAYS.get(str(horizon))
    if trading_days is None:
        return 0
    return int(math.ceil(trading_days * 365.25 / 252.0))


def independent_case_sample(data: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Prune repeated same-stock observations whose forward windows overlap.

    Keeps the earliest eligible observation for each ticker, then only accepts a new
    observation after the retained observation's evaluation window has ended. This is
    intentionally conservative: row count must not masquerade as independent evidence.

    The function expects `symbol` and `captured_date`. If those fields are unavailable,
    it returns an empty frame rather than silently claiming independence.
    """
    if data is None or data.empty:
        return pd.DataFrame(columns=getattr(data, "columns", None))
    if "symbol" not in data.columns or "captured_date" not in data.columns:
        # Legacy/test datasets may predate these ledger fields. Preserve old analysis
        # rather than deleting it; production ledger rows include both fields.
        return data.copy()
    gap = _calendar_days(horizon)
    if gap <= 0:
        return data.iloc[0:0].copy()

    work = data.copy()
    work["_captured"] = pd.to_datetime(work["captured_date"], errors="coerce", utc=True).dt.tz_convert(None)
    work["_symbol"] = work["symbol"].fillna("").astype(str).str.upper().str.strip()
    work = work[work["_captured"].notna() & work["_symbol"].ne("")].copy()
    if work.empty:
        return work.drop(columns=["_captured", "_symbol"], errors="ignore")

    # Stable ordering makes the audit reproducible even if DB row order changes.
    sort_cols = ["_symbol", "_captured"] + (["record_id"] if "record_id" in work.columns else [])
    work = work.sort_values(sort_cols, kind="stable")
    keep_idx: list[Any] = []
    for _, group in work.groupby("_symbol", sort=False):
        next_allowed = None
        for idx, row in group.iterrows():
            captured = row["_captured"]
            if next_allowed is None or captured > next_allowed:
                keep_idx.append(idx)
                next_allowed = captured + pd.Timedelta(days=gap)
    return work.loc[keep_idx].drop(columns=["_captured", "_symbol"], errors="ignore").copy()


def independence_audit(data: pd.DataFrame, horizon: str) -> dict[str, Any]:
    """Explain how much repeated/overlapping evidence was removed."""
    raw = 0 if data is None else int(len(data))
    independent = independent_case_sample(data, horizon)
    kept = int(len(independent))
    unique_tickers = int(independent["symbol"].astype(str).str.upper().nunique()) if kept and "symbol" in independent else 0
    removed = max(0, raw - kept)
    return {
        "raw_observations": raw,
        "independent_observations": kept,
        "removed_overlaps": removed,
        "unique_tickers": unique_tickers,
        "horizon": str(horizon),
        "text": (
            f"{kept} oberoende case används av {raw} mogna observationer. "
            f"{removed} överlappande upprepningar av samma aktie räknas inte som ny evidens."
        ),
    }
