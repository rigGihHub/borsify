from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import pandas as pd

HORIZONS = {"1w": 5, "1m": 21, "3m": 63, "12m": 252}

@dataclass(frozen=True)
class FrozenPick:
    ticker: str
    captured_at: str
    price: float
    final_score: float
    horizon: str
    reason: str
    risk: str
    benchmark: str

def freeze_pick(row: Any, horizon: str, benchmark: str, captured_at: str) -> dict[str, Any]:
    """Freeze only information available when Borsify made the suggestion."""
    def num(v):
        try:
            x=float(v); return x if math.isfinite(x) else float("nan")
        except Exception: return float("nan")
    return {
        "Ticker": str(row.get("Ticker") or ""),
        "Captured at": captured_at,
        "Entry price": num(row.get("Pris")),
        "Final score": num(row.get("Borsify slutbetyg", row.get("Borsify Score"))),
        "Horizon": horizon,
        "Reason": str(row.get("Varför köpa") or row.get("Horisontförklaring") or ""),
        "Risk": str(row.get("Största risk") or row.get("Riskflaggor") or ""),
        "Benchmark": benchmark,
        "Model version": str(row.get("Model version") or ""),
    }

def forward_return(prices: pd.Series, entry_pos: int, days: int) -> float:
    s=pd.to_numeric(prices, errors="coerce").dropna()
    if entry_pos < 0 or entry_pos >= len(s) or entry_pos + days >= len(s):
        return float("nan")
    a=float(s.iloc[entry_pos]); b=float(s.iloc[entry_pos+days])
    return b/a-1 if a > 0 else float("nan")

def evaluate_pick(entry_return: float, benchmark_return: float) -> dict[str, Any]:
    if not math.isfinite(entry_return):
        return {"Return": float("nan"), "Benchmark return": benchmark_return, "Beat benchmark": None, "Excess return": float("nan")}
    excess=entry_return-benchmark_return if math.isfinite(benchmark_return) else float("nan")
    return {
        "Return": entry_return,
        "Benchmark return": benchmark_return,
        "Beat benchmark": bool(excess > 0) if math.isfinite(excess) else None,
        "Excess return": excess,
    }

def validation_summary(results: pd.DataFrame) -> dict[str, Any]:
    if results is None or results.empty:
        return {"count":0, "hit_rate":float("nan"), "avg_excess":float("nan")}
    excess=pd.to_numeric(results.get("Excess return"), errors="coerce").dropna()
    return {
        "count": int(len(excess)),
        "hit_rate": float((excess > 0).mean()) if len(excess) else float("nan"),
        "avg_excess": float(excess.mean()) if len(excess) else float("nan"),
        "median_excess": float(excess.median()) if len(excess) else float("nan"),
    }
