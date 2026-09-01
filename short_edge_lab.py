from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _pct(series: pd.Series, periods: int) -> pd.Series:
    return series.pct_change(periods=periods, fill_method=None)


def _score_linear(s: pd.Series, lo: float, hi: float) -> pd.Series:
    return ((s - lo) / (hi - lo) * 100).clip(0, 100)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_up = up.rolling(window, min_periods=window).mean()
    avg_down = down.rolling(window, min_periods=window).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def build_point_in_time_short_signals(
    prices: pd.DataFrame,
    benchmark: pd.Series | None = None,
    volume: pd.Series | None = None,
) -> pd.DataFrame:
    """Causal technical Short Alpha proxy using only information known at each date.

    Historical revisions/catalysts are deliberately excluded because Borsify does not
    yet store point-in-time histories for them. This prevents look-ahead contamination.
    """
    if prices is None or prices.empty:
        return pd.DataFrame()

    close = prices["Close"].astype(float).copy()
    vol = volume.astype(float) if volume is not None else (
        prices["Volume"].astype(float) if "Volume" in prices.columns
        else pd.Series(index=close.index, dtype=float)
    )

    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    dist200 = close / sma200 - 1
    m1, m3, m6 = _pct(close, 21), _pct(close, 63), _pct(close, 126)

    trend = pd.Series(45.0, index=close.index)
    above50 = close >= sma50
    trend[(dist200 >= 0) & (dist200 <= 0.18) & above50] = 88
    trend[(dist200 >= 0) & (dist200 <= 0.18) & ~above50] = 72
    trend[(dist200 > 0.18) & above50] = 72
    trend[(dist200 > 0.18) & ~above50] = 58
    trend[(dist200 >= -0.05) & (dist200 < 0) & above50] = 55
    trend[(dist200 >= -0.05) & (dist200 < 0) & ~above50] = 42
    trend[(dist200 >= -0.10) & (dist200 < -0.05)] = 30
    trend[dist200 < -0.10] = 10

    momentum = pd.concat([
        _score_linear(m1, -0.10, 0.14),
        _score_linear(m3, -0.15, 0.30),
        _score_linear(m6, -0.20, 0.50),
    ], axis=1).mean(axis=1)

    if benchmark is not None and not benchmark.empty:
        b = benchmark.reindex(close.index).ffill()
        relative = pd.concat([
            _score_linear(m1 - _pct(b, 21), -0.15, 0.15),
            _score_linear(m3 - _pct(b, 63), -0.15, 0.15),
            _score_linear(m6 - _pct(b, 126), -0.15, 0.15),
        ], axis=1).mean(axis=1)
    else:
        relative = pd.Series(50.0, index=close.index)

    if not vol.empty:
        vol_avg = vol.rolling(20, min_periods=20).mean()
        vol_ratio = vol / vol_avg.replace(0, np.nan)
        participation = _score_linear(vol_ratio, 0.65, 1.65)
    else:
        vol_ratio = pd.Series(np.nan, index=close.index)
        participation = pd.Series(45.0, index=close.index)

    # Only reconstructable dimensions; live revisions/catalysts are not backfilled.
    proxy = (
        0.35 * relative
        + 0.30 * trend
        + 0.22 * momentum
        + 0.13 * participation.fillna(45)
    )

    falling_knife = (
        ((dist200 < -0.10) & (m3 < -0.08))
        | (m1 <= -0.20)
        | ((relative < 25) & (dist200 < 0))
    )
    proxy = proxy.where(~falling_knife, np.minimum(proxy, 54.0))

    return pd.DataFrame({
        "Close": close,
        "SMA50": sma50,
        "SMA200": sma200,
        "Dist200": dist200,
        "M1": m1,
        "M3": m3,
        "M6": m6,
        "RSI": _rsi(close),
        "VolumeRatio": vol_ratio,
        "Trend": trend,
        "Relative": relative,
        "Momentum": momentum,
        "Participation": participation,
        "ShortProxy": proxy,
        "FallingKnifeVeto": falling_knife.astype(bool),
    })


def add_forward_returns(signals: pd.DataFrame, horizons: dict[str, int] | None = None) -> pd.DataFrame:
    if signals is None or signals.empty:
        return pd.DataFrame()
    horizons = horizons or {"1m": 21, "3m": 63, "6m": 126}
    out = signals.copy()
    for label, days in horizons.items():
        out[f"Fwd_{label}"] = out["Close"].shift(-days) / out["Close"] - 1
    return out


def evaluate_thresholds(
    signals: pd.DataFrame,
    thresholds: list[float] | None = None,
    spacing_days: int = 21,
) -> pd.DataFrame:
    """Threshold diagnostic with spaced entries; not a trading simulator."""
    if signals is None or signals.empty:
        return pd.DataFrame()
    thresholds = thresholds or [55, 60, 65, 70, 75, 80]
    rows = []
    pos = {idx: i for i, idx in enumerate(signals.index)}

    for threshold in thresholds:
        cand = signals[(signals["ShortProxy"] >= threshold) & (~signals["FallingKnifeVeto"])]
        chosen, last_i = [], -100000
        for idx in cand.index:
            i = pos[idx]
            if i - last_i >= spacing_days:
                chosen.append(idx)
                last_i = i
        sample = cand.loc[chosen] if chosen else cand.iloc[0:0]

        for horizon in ("1m", "3m", "6m"):
            col = f"Fwd_{horizon}"
            vals = sample[col].dropna() if col in sample else pd.Series(dtype=float)
            if vals.empty:
                continue
            rows.append({
                "Threshold": threshold,
                "Horizon": horizon,
                "Signals": int(len(vals)),
                "MedianReturn": float(vals.median()),
                "MeanReturn": float(vals.mean()),
                "HitRate": float((vals > 0).mean()),
                "LossRate10": float((vals <= -0.10).mean()),
                "GainRate10": float((vals >= 0.10).mean()),
            })
    return pd.DataFrame(rows)


def walk_forward_threshold_test(
    signals: pd.DataFrame,
    min_train_days: int = 504,
    test_days: int = 126,
    thresholds: list[float] | None = None,
) -> pd.DataFrame:
    """Choose a threshold on prior data and evaluate it only on the later window."""
    if signals is None or signals.empty:
        return pd.DataFrame()
    thresholds = thresholds or [55, 60, 65, 70, 75, 80]
    rows, n, start = [], len(signals), min_train_days

    while start < n - 63:
        train = signals.iloc[max(0, start - min_train_days):start]
        test = signals.iloc[start:min(n, start + test_days)]
        train_eval = evaluate_thresholds(train, thresholds, spacing_days=21)
        train_3m = (
            train_eval[(train_eval["Horizon"] == "3m") & (train_eval["Signals"] >= 3)]
            if not train_eval.empty else pd.DataFrame()
        )
        if not train_3m.empty:
            best = train_3m.sort_values(
                ["MedianReturn", "HitRate", "Threshold"], ascending=False
            ).iloc[0]
            threshold = float(best["Threshold"])
            selected = test[
                (test["ShortProxy"] >= threshold) & (~test["FallingKnifeVeto"])
            ]
            vals = selected.get("Fwd_3m", pd.Series(dtype=float)).dropna()
            if len(vals):
                rows.append({
                    "TrainEnd": train.index[-1],
                    "TestStart": test.index[0],
                    "TestEnd": test.index[-1],
                    "ChosenThreshold": threshold,
                    "TrainMedian3m": float(best["MedianReturn"]),
                    "TestSignals": int(len(vals)),
                    "TestMedian3m": float(vals.median()),
                    "TestMean3m": float(vals.mean()),
                    "TestHitRate3m": float((vals > 0).mean()),
                })
        start += test_days
    return pd.DataFrame(rows)


def component_bucket_analysis(signals: pd.DataFrame, component: str, horizon: str = "3m") -> pd.DataFrame:
    if signals is None or signals.empty or component not in signals:
        return pd.DataFrame()
    col = f"Fwd_{horizon}"
    if col not in signals:
        return pd.DataFrame()
    work = signals[[component, col]].dropna().copy()
    if len(work) < 20:
        return pd.DataFrame()
    try:
        work["Bucket"] = pd.qcut(
            work[component],
            q=4,
            labels=["Q1 svagast", "Q2", "Q3", "Q4 starkast"],
            duplicates="drop",
        )
    except Exception:
        return pd.DataFrame()
    grouped = work.groupby("Bucket", observed=True)[col].agg(["count", "median", "mean"])
    grouped["HitRate"] = work.groupby("Bucket", observed=True)[col].apply(
        lambda s: float((s > 0).mean())
    )
    return grouped.reset_index().rename(
        columns={"count": "Signals", "median": "MedianReturn", "mean": "MeanReturn"}
    )


def summarize_edge(thresholds: pd.DataFrame, walk_forward: pd.DataFrame) -> dict[str, Any]:
    if thresholds is None or thresholds.empty:
        return {
            "status": "Otillräcklig data",
            "message": "För få historiska observationer för att bedöma Short Alpha-proxyn.",
        }
    three = thresholds[
        (thresholds["Horizon"] == "3m") & (thresholds["Signals"] >= 5)
    ].copy()
    if three.empty:
        return {
            "status": "Otillräcklig data",
            "message": "För få 3-månadersobservationer för stabilare slutsats.",
        }

    best = three.sort_values(["MedianReturn", "HitRate"], ascending=False).iloc[0]
    wf_median = np.nan
    wf_positive = False
    if walk_forward is not None and not walk_forward.empty:
        wf_median = float(walk_forward["TestMedian3m"].median())
        wf_positive = wf_median > 0

    if best["MedianReturn"] > 0 and best["HitRate"] >= 0.5 and wf_positive:
        status = "Historiskt lovande – ej bevisad alpha"
    elif best["MedianReturn"] > 0 and best["HitRate"] >= 0.5:
        status = "In-sample lovande – kräver bättre OOS-stöd"
    else:
        status = "Ingen tydlig historisk edge"

    return {
        "status": status,
        "best_threshold": float(best["Threshold"]),
        "median_3m": float(best["MedianReturn"]),
        "hit_rate_3m": float(best["HitRate"]),
        "signals_3m": int(best["Signals"]),
        "walk_forward_median_3m": wf_median,
        "message": "Teknisk point-in-time-proxy. Historiska revisions- och katalysatordata ingår inte.",
    }
