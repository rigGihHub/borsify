from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def build_technical_history(history: pd.DataFrame) -> pd.DataFrame:
    """Build trailing-only technical features suitable for historical testing.

    The function intentionally uses no current fundamental data, because applying
    today's fundamentals to old dates would create look-ahead bias.
    """
    if history is None or history.empty:
        return pd.DataFrame()

    df = history.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    required = {"Close", "Volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    close = pd.to_numeric(df["Close"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    df["ret_1d"] = close.pct_change()
    df["ret_20d"] = close.pct_change(20)
    df["ret_60d"] = close.pct_change(60)
    df["sma20"] = close.rolling(20, min_periods=20).mean()
    df["sma50"] = close.rolling(50, min_periods=50).mean()
    df["sma200"] = close.rolling(200, min_periods=200).mean()
    df["dist_sma20"] = close / df["sma20"] - 1
    df["dist_sma50"] = close / df["sma50"] - 1
    df["dist_sma200"] = close / df["sma200"] - 1
    df["rsi14"] = _rsi(close, 14)
    df["volume_ratio"] = volume / volume.rolling(20, min_periods=20).mean()
    rolling_high = close.rolling(252, min_periods=60).max()
    df["drawdown_52w"] = close / rolling_high - 1

    # ATR is trailing-only and is used by the optional risk-sizing backtest.
    if {"High", "Low"}.issubset(df.columns):
        high = pd.to_numeric(df["High"], errors="coerce")
        low = pd.to_numeric(df["Low"], errors="coerce")
        prev_close = close.shift(1)
        true_range = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
    else:
        # Fallback when a data source only provides Close/Volume. It is less
        # precise than true range, but remains causal and avoids silently
        # disabling risk sizing for otherwise usable histories.
        true_range = close.diff().abs()
    df["atr14"] = true_range.rolling(14, min_periods=14).mean()
    df["atr14_pct"] = (df["atr14"] / close).replace([np.inf, -np.inf], np.nan)

    # SWING proxy: trend + controlled pullback + momentum + participation.
    trend = np.select(
        [df["dist_sma200"].between(0, .20), df["dist_sma200"].between(-.05, 0, inclusive="left"), df["dist_sma200"] > .20, df["dist_sma200"] < -.10],
        [85, 65, 65, 20],
        default=45,
    )
    rsi_setup = (100 * np.exp(-((df["rsi14"] - 50) / 17) ** 2)).clip(0, 100)
    pullback = (100 * np.exp(-((df["dist_sma20"] + .01) / .055) ** 2)).clip(0, 100)
    momentum = ((df["ret_60d"] + .10) / .35 * 100).clip(0, 100).fillna(45)
    volume_score = ((df["volume_ratio"] - .7) / 1.1 * 100).clip(0, 100).fillna(45)
    df["swing_proxy"] = (.30 * trend + .25 * rsi_setup + .20 * pullback + .15 * momentum + .10 * volume_score).clip(0, 100)

    # REVERSAL proxy: sharp selloff + meaningful drawdown + oversold condition.
    selloff = ((-df["ret_1d"] - .015) / .10 * 100).clip(0, 100).fillna(0)
    draw_score = ((-df["drawdown_52w"] - .08) / .32 * 100).clip(0, 100).fillna(20)
    oversold = ((48 - df["rsi14"]) / 23 * 100).clip(0, 100).fillna(20)
    reclaim = ((df["dist_sma20"] + .10) / .12 * 100).clip(0, 100).fillna(30)
    df["reversal_proxy"] = (.38 * selloff + .27 * draw_score + .25 * oversold + .10 * reclaim).clip(0, 100)

    for days in (5, 10, 20):
        df[f"fwd_{days}d"] = close.shift(-days) / close - 1
    return df


def summarize_backtest(df: pd.DataFrame, score_col: str, threshold: float, horizon_days: int) -> dict[str, float | int]:
    if df.empty or score_col not in df.columns:
        return {"signals": 0}
    fwd_col = f"fwd_{horizon_days}d"
    valid = df[[score_col, fwd_col]].dropna()
    if valid.empty:
        return {"signals": 0}
    hits = valid[valid[score_col] >= threshold]
    baseline = valid[fwd_col]
    if hits.empty:
        return {"signals": 0, "baseline_observations": int(len(valid))}
    returns = hits[fwd_col]
    losses = returns[returns < 0]
    wins = returns[returns > 0]
    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.nan
    return {
        "signals": int(len(hits)),
        "win_rate": float((returns > 0).mean()),
        "median_return": float(returns.median()),
        "mean_return": float(returns.mean()),
        "baseline_win_rate": float((baseline > 0).mean()),
        "baseline_median_return": float(baseline.median()),
        "profit_factor": float(profit_factor) if np.isfinite(profit_factor) else np.nan,
    }


def summarize_universe_backtest(
    histories: dict[str, pd.DataFrame],
    score_col: str,
    threshold: float,
    horizon_days: int,
) -> dict:
    """Aggregate the same trailing-only signal across many symbols.

    Baselines are calculated per symbol before pooling so a chronically strong
    stock cannot make a weak signal look good merely because that stock rose
    over the whole sample.
    """
    rows = []
    pooled_signal_returns: list[float] = []
    pooled_baseline_returns: list[float] = []
    symbols_tested = 0
    symbols_with_signals = 0

    for symbol, history in histories.items():
        tech = build_technical_history(history)
        if tech.empty or score_col not in tech.columns:
            continue
        fwd_col = f"fwd_{horizon_days}d"
        valid = tech[[score_col, fwd_col]].dropna()
        if len(valid) < 60:
            continue
        symbols_tested += 1
        hits = valid[valid[score_col] >= threshold]
        baseline = valid[fwd_col]
        pooled_baseline_returns.extend(baseline.astype(float).tolist())
        if hits.empty:
            continue
        symbols_with_signals += 1
        returns = hits[fwd_col].astype(float)
        pooled_signal_returns.extend(returns.tolist())
        median_ret = float(returns.median())
        baseline_median = float(baseline.median())
        rows.append({
            "symbol": symbol,
            "signals": int(len(returns)),
            "win_rate": float((returns > 0).mean()),
            "baseline_win_rate": float((baseline > 0).mean()),
            "median_return": median_ret,
            "baseline_median_return": baseline_median,
            "median_excess": median_ret - baseline_median,
        })

    if not pooled_signal_returns:
        return {
            "symbols_tested": symbols_tested,
            "symbols_with_signals": symbols_with_signals,
            "signals": 0,
            "per_symbol": pd.DataFrame(rows),
        }

    signal = pd.Series(pooled_signal_returns, dtype=float)
    baseline = pd.Series(pooled_baseline_returns, dtype=float)
    wins = signal[signal > 0]
    losses = signal[signal < 0]
    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.nan
    per_symbol = pd.DataFrame(rows)
    positive_edge_share = float((per_symbol["median_excess"] > 0).mean()) if not per_symbol.empty else 0.0
    return {
        "symbols_tested": symbols_tested,
        "symbols_with_signals": symbols_with_signals,
        "signals": int(len(signal)),
        "win_rate": float((signal > 0).mean()),
        "baseline_win_rate": float((baseline > 0).mean()) if not baseline.empty else np.nan,
        "median_return": float(signal.median()),
        "mean_return": float(signal.mean()),
        "baseline_median_return": float(baseline.median()) if not baseline.empty else np.nan,
        "median_excess": float(signal.median() - baseline.median()) if not baseline.empty else np.nan,
        "profit_factor": float(profit_factor) if np.isfinite(profit_factor) else np.nan,
        "positive_edge_share": positive_edge_share,
        "per_symbol": per_symbol,
    }


def build_market_regime_history(index_history: pd.DataFrame) -> pd.DataFrame:
    """Classify each historical date into Risk-on, Neutral or Risk-off.

    Uses only trailing index data. No future information is used.
    """
    if index_history is None or index_history.empty:
        return pd.DataFrame()
    df = index_history.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    if "Close" not in df.columns:
        return pd.DataFrame()
    close = pd.to_numeric(df["Close"], errors="coerce")
    out = pd.DataFrame(index=df.index)
    out["index_close"] = close
    out["index_sma50"] = close.rolling(50, min_periods=50).mean()
    out["index_sma200"] = close.rolling(200, min_periods=200).mean()
    out["index_ret_60d"] = close.pct_change(60)
    out["index_dist_sma200"] = close / out["index_sma200"] - 1

    risk_on = (
        (close > out["index_sma200"])
        & (out["index_sma50"] > out["index_sma200"])
        & (out["index_ret_60d"] > 0)
    )
    risk_off = (
        (close < out["index_sma200"])
        & (out["index_sma50"] < out["index_sma200"])
        & (out["index_ret_60d"] < 0)
    )
    out["regime"] = np.select([risk_on, risk_off], ["Risk-on", "Risk-off"], default="Neutral")
    return out


def summarize_backtest_by_regime(
    technical_history: pd.DataFrame,
    regime_history: pd.DataFrame,
    score_col: str,
    threshold: float,
    horizon_days: int,
) -> pd.DataFrame:
    """Summarize a signal separately inside each market regime."""
    if technical_history is None or technical_history.empty or regime_history is None or regime_history.empty:
        return pd.DataFrame()
    fwd_col = f"fwd_{horizon_days}d"
    if score_col not in technical_history.columns or fwd_col not in technical_history.columns or "regime" not in regime_history.columns:
        return pd.DataFrame()
    joined = technical_history[[score_col, fwd_col]].join(regime_history[["regime"]], how="left").dropna()
    rows = []
    for regime in ("Risk-on", "Neutral", "Risk-off"):
        valid = joined[joined["regime"] == regime]
        if valid.empty:
            continue
        hits = valid[valid[score_col] >= threshold]
        if hits.empty:
            rows.append({
                "regime": regime, "signals": 0, "win_rate": np.nan,
                "baseline_win_rate": float((valid[fwd_col] > 0).mean()),
                "median_return": np.nan, "baseline_median_return": float(valid[fwd_col].median()),
                "median_excess": np.nan, "profit_factor": np.nan,
            })
            continue
        returns = hits[fwd_col].astype(float)
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        gross_profit = float(wins.sum()) if not wins.empty else 0.0
        gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
        pf = gross_profit / gross_loss if gross_loss > 0 else np.nan
        baseline = valid[fwd_col].astype(float)
        median_return = float(returns.median())
        baseline_median = float(baseline.median())
        rows.append({
            "regime": regime,
            "signals": int(len(returns)),
            "win_rate": float((returns > 0).mean()),
            "baseline_win_rate": float((baseline > 0).mean()),
            "median_return": median_return,
            "baseline_median_return": baseline_median,
            "median_excess": median_return - baseline_median,
            "profit_factor": float(pf) if np.isfinite(pf) else np.nan,
        })
    return pd.DataFrame(rows)


def summarize_universe_backtest_by_regime(
    histories: dict[str, pd.DataFrame],
    regime_history: pd.DataFrame,
    score_col: str,
    threshold: float,
    horizon_days: int,
) -> pd.DataFrame:
    """Pool universe signal outcomes by a shared market-regime series."""
    pooled: dict[str, list[float]] = {"Risk-on": [], "Neutral": [], "Risk-off": []}
    baseline_pooled: dict[str, list[float]] = {"Risk-on": [], "Neutral": [], "Risk-off": []}
    symbols: dict[str, set[str]] = {"Risk-on": set(), "Neutral": set(), "Risk-off": set()}
    fwd_col = f"fwd_{horizon_days}d"
    if regime_history is None or regime_history.empty or "regime" not in regime_history.columns:
        return pd.DataFrame()

    for symbol, history in histories.items():
        tech = build_technical_history(history)
        if tech.empty or score_col not in tech.columns:
            continue
        joined = tech[[score_col, fwd_col]].join(regime_history[["regime"]], how="left").dropna()
        if len(joined) < 60:
            continue
        for regime in pooled:
            valid = joined[joined["regime"] == regime]
            if valid.empty:
                continue
            baseline_pooled[regime].extend(valid[fwd_col].astype(float).tolist())
            hits = valid[valid[score_col] >= threshold]
            if not hits.empty:
                pooled[regime].extend(hits[fwd_col].astype(float).tolist())
                symbols[regime].add(symbol)

    rows = []
    for regime in ("Risk-on", "Neutral", "Risk-off"):
        signal = pd.Series(pooled[regime], dtype=float)
        baseline = pd.Series(baseline_pooled[regime], dtype=float)
        if signal.empty:
            continue
        wins = signal[signal > 0]
        losses = signal[signal < 0]
        gp = float(wins.sum()) if not wins.empty else 0.0
        gl = abs(float(losses.sum())) if not losses.empty else 0.0
        pf = gp / gl if gl > 0 else np.nan
        rows.append({
            "regime": regime,
            "symbols_with_signals": len(symbols[regime]),
            "signals": int(len(signal)),
            "win_rate": float((signal > 0).mean()),
            "baseline_win_rate": float((baseline > 0).mean()) if not baseline.empty else np.nan,
            "median_return": float(signal.median()),
            "baseline_median_return": float(baseline.median()) if not baseline.empty else np.nan,
            "median_excess": float(signal.median() - baseline.median()) if not baseline.empty else np.nan,
            "profit_factor": float(pf) if np.isfinite(pf) else np.nan,
        })
    return pd.DataFrame(rows)


def _non_overlapping_hits(valid: pd.DataFrame, score_col: str, threshold: float, horizon_days: int) -> pd.DataFrame:
    """Return threshold hits while avoiding clusters of overlapping forward windows.

    A daily screener can emit the same setup several days in a row. Counting every
    day as an independent trade overstates sample size. Walk-forward evaluation
    therefore keeps the first eligible signal and skips the next `horizon_days`
    rows before accepting another signal.
    """
    if valid is None or valid.empty or score_col not in valid.columns:
        return pd.DataFrame(columns=getattr(valid, "columns", []))
    mask = pd.to_numeric(valid[score_col], errors="coerce") >= float(threshold)
    candidate_positions = np.flatnonzero(mask.to_numpy())
    if len(candidate_positions) == 0:
        return valid.iloc[0:0].copy()
    keep: list[int] = []
    next_allowed = 0
    cooldown = max(int(horizon_days), 1)
    for pos in candidate_positions:
        if int(pos) < next_allowed:
            continue
        keep.append(int(pos))
        next_allowed = int(pos) + cooldown
    return valid.iloc[keep].copy()


def _window_stats(valid: pd.DataFrame, score_col: str, threshold: float, horizon_days: int) -> dict[str, float | int]:
    """Evaluate one threshold inside a pre-sliced chronological window."""
    if valid is None or valid.empty:
        return {"signals": 0}
    fwd_col = f"fwd_{horizon_days}d"
    if score_col not in valid.columns or fwd_col not in valid.columns:
        return {"signals": 0}
    clean = valid[[score_col, fwd_col]].dropna().copy()
    if clean.empty:
        return {"signals": 0}
    hits = _non_overlapping_hits(clean, score_col, threshold, horizon_days)
    baseline = clean[fwd_col].astype(float)
    if hits.empty:
        return {
            "signals": 0,
            "baseline_win_rate": float((baseline > 0).mean()),
            "baseline_median_return": float(baseline.median()),
        }
    returns = hits[fwd_col].astype(float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.nan
    win_rate = float((returns > 0).mean())
    baseline_win_rate = float((baseline > 0).mean())
    median_return = float(returns.median())
    baseline_median = float(baseline.median())
    return {
        "signals": int(len(returns)),
        "win_rate": win_rate,
        "baseline_win_rate": baseline_win_rate,
        "win_rate_excess": win_rate - baseline_win_rate,
        "median_return": median_return,
        "baseline_median_return": baseline_median,
        "median_excess": median_return - baseline_median,
        "mean_return": float(returns.mean()),
        "profit_factor": float(profit_factor) if np.isfinite(profit_factor) else np.nan,
    }


def walk_forward_backtest(
    technical_history: pd.DataFrame,
    score_col: str,
    thresholds: list[float] | tuple[float, ...],
    horizon_days: int,
    train_days: int = 504,
    test_days: int = 126,
    min_train_signals: int = 12,
    min_test_signals: int = 2,
) -> dict:
    """Tune a score threshold on past data and evaluate it only on unseen data.

    Each fold uses a rolling training window, selects the threshold with the best
    conservative training objective, then freezes that threshold for the next
    test window. Training rows whose forward return crosses into the test window
    are excluded. Repeated daily setup hits are de-clustered so overlapping
    forward windows are not counted as independent trades.
    """
    if technical_history is None or technical_history.empty:
        return {"folds": 0, "signals": 0, "fold_table": pd.DataFrame()}
    fwd_col = f"fwd_{horizon_days}d"
    if score_col not in technical_history.columns or fwd_col not in technical_history.columns:
        return {"folds": 0, "signals": 0, "fold_table": pd.DataFrame()}

    cols = [score_col, fwd_col]
    data = technical_history[cols].copy()
    data[score_col] = pd.to_numeric(data[score_col], errors="coerce")
    data[fwd_col] = pd.to_numeric(data[fwd_col], errors="coerce")
    data = data.dropna().sort_index()
    train_days = max(int(train_days), 120)
    test_days = max(int(test_days), 20)
    horizon_days = max(int(horizon_days), 1)
    candidates = sorted({float(x) for x in thresholds})
    if not candidates or len(data) < train_days + test_days:
        return {"folds": 0, "signals": 0, "fold_table": pd.DataFrame()}

    fold_rows: list[dict] = []
    pooled_returns: list[float] = []
    pooled_baselines: list[float] = []
    start_test = train_days
    fold_no = 0

    while start_test + test_days <= len(data):
        fold_no += 1
        train_start = max(0, start_test - train_days)
        # Prevent a training observation's future return from using test prices.
        train_end_exclusive = max(train_start, start_test - horizon_days)
        train = data.iloc[train_start:train_end_exclusive].copy()
        test = data.iloc[start_test:start_test + test_days].copy()
        if train.empty or test.empty:
            start_test += test_days
            continue

        scored_candidates: list[tuple[float, float, dict]] = []
        for threshold in candidates:
            stats = _window_stats(train, score_col, threshold, horizon_days)
            if int(stats.get("signals", 0)) < int(min_train_signals):
                continue
            med_edge = float(stats.get("median_excess", np.nan))
            win_edge = float(stats.get("win_rate_excess", np.nan))
            if not np.isfinite(med_edge) or not np.isfinite(win_edge):
                continue
            # Median edge dominates. Win-rate edge is a secondary robustness term.
            objective = med_edge + 0.35 * win_edge
            scored_candidates.append((objective, threshold, stats))

        if not scored_candidates:
            start_test += test_days
            continue
        scored_candidates.sort(key=lambda x: (x[0], x[2].get("signals", 0)), reverse=True)
        _, chosen_threshold, train_stats = scored_candidates[0]
        test_stats = _window_stats(test, score_col, chosen_threshold, horizon_days)
        test_signals = int(test_stats.get("signals", 0))

        if test_signals > 0:
            hits = _non_overlapping_hits(test[[score_col, fwd_col]].dropna(), score_col, chosen_threshold, horizon_days)
            pooled_returns.extend(hits[fwd_col].astype(float).tolist())
        pooled_baselines.extend(test[fwd_col].astype(float).dropna().tolist())

        test_median_edge = float(test_stats.get("median_excess", np.nan))
        test_win_edge = float(test_stats.get("win_rate_excess", np.nan))
        fold_rows.append({
            "fold": fold_no,
            "train_start": str(train.index.min())[:10],
            "train_end": str(train.index.max())[:10],
            "test_start": str(test.index.min())[:10],
            "test_end": str(test.index.max())[:10],
            "threshold": chosen_threshold,
            "train_signals": int(train_stats.get("signals", 0)),
            "train_median_excess": float(train_stats.get("median_excess", np.nan)),
            "test_signals": test_signals,
            "test_win_rate": float(test_stats.get("win_rate", np.nan)),
            "test_baseline_win_rate": float(test_stats.get("baseline_win_rate", np.nan)),
            "test_win_rate_excess": test_win_edge,
            "test_median_return": float(test_stats.get("median_return", np.nan)),
            "test_baseline_median_return": float(test_stats.get("baseline_median_return", np.nan)),
            "test_median_excess": test_median_edge,
            "test_profit_factor": float(test_stats.get("profit_factor", np.nan)),
            "eligible": test_signals >= int(min_test_signals),
        })
        start_test += test_days

    fold_table = pd.DataFrame(fold_rows)
    if fold_table.empty:
        return {"folds": 0, "signals": 0, "fold_table": fold_table}

    signal = pd.Series(pooled_returns, dtype=float)
    baseline = pd.Series(pooled_baselines, dtype=float)
    eligible_folds = fold_table[fold_table["eligible"]].copy()
    if signal.empty:
        return {
            "folds": int(len(fold_table)),
            "eligible_folds": int(len(eligible_folds)),
            "signals": 0,
            "fold_table": fold_table,
        }

    wins = signal[signal > 0]
    losses = signal[signal < 0]
    gp = float(wins.sum()) if not wins.empty else 0.0
    gl = abs(float(losses.sum())) if not losses.empty else 0.0
    pf = gp / gl if gl > 0 else np.nan
    positive_fold_share = float((eligible_folds["test_median_excess"] > 0).mean()) if not eligible_folds.empty else np.nan
    threshold_std = float(fold_table["threshold"].std(ddof=0)) if len(fold_table) > 1 else 0.0
    return {
        "folds": int(len(fold_table)),
        "eligible_folds": int(len(eligible_folds)),
        "signals": int(len(signal)),
        "win_rate": float((signal > 0).mean()),
        "baseline_win_rate": float((baseline > 0).mean()) if not baseline.empty else np.nan,
        "median_return": float(signal.median()),
        "baseline_median_return": float(baseline.median()) if not baseline.empty else np.nan,
        "median_excess": float(signal.median() - baseline.median()) if not baseline.empty else np.nan,
        "mean_return": float(signal.mean()),
        "profit_factor": float(pf) if np.isfinite(pf) else np.nan,
        "positive_fold_share": positive_fold_share,
        "median_threshold": float(fold_table["threshold"].median()),
        "threshold_std": threshold_std,
        "fold_table": fold_table,
        "trade_returns": signal.astype(float).tolist(),
    }


def summarize_trading_friction(
    returns: list[float] | pd.Series | np.ndarray,
    roundtrip_cost_bps: float = 20.0,
    position_fraction: float = 1.0,
) -> dict[str, float | int]:
    """Translate gross signal returns into a simple after-cost equity simulation.

    `roundtrip_cost_bps` represents the total economic drag for entry + exit
    (commission + spread + slippage). `position_fraction` is the fraction of
    current equity allocated to each sequential trade. This is intentionally a
    simple diagnostic: it does not model concurrent positions, taxes, liquidity
    limits or partial fills.
    """
    series = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if series.empty:
        return {"trades": 0}
    cost = max(float(roundtrip_cost_bps), 0.0) / 10000.0
    fraction = float(np.clip(position_fraction, 0.0, 1.0))
    net = series - cost
    equity_multipliers = 1.0 + fraction * net
    # A return below -100% is not economically meaningful in this long-only proxy.
    equity_multipliers = equity_multipliers.clip(lower=0.0)
    equity = equity_multipliers.cumprod()
    running_peak = equity.cummax()
    drawdown = equity / running_peak.replace(0, np.nan) - 1.0
    wins = net[net > 0]
    losses = net[net < 0]
    gp = float(wins.sum()) if not wins.empty else 0.0
    gl = abs(float(losses.sum())) if not losses.empty else 0.0
    pf = gp / gl if gl > 0 else np.nan
    compounded = float(equity.iloc[-1] - 1.0)
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0
    return {
        "trades": int(len(net)),
        "roundtrip_cost_bps": float(roundtrip_cost_bps),
        "position_fraction": fraction,
        "net_win_rate": float((net > 0).mean()),
        "net_median_return": float(net.median()),
        "net_mean_return": float(net.mean()),
        "net_profit_factor": float(pf) if np.isfinite(pf) else np.nan,
        "compounded_return": compounded,
        "max_drawdown": max_dd,
        "gross_median_return": float(series.median()),
        "cost_drag_per_trade": cost,
    }


def simulate_portfolio_backtest(
    histories: dict[str, pd.DataFrame],
    score_col: str,
    threshold: float,
    horizon_days: int,
    max_positions: int = 5,
    position_fraction: float = 0.20,
    roundtrip_cost_bps: float = 30.0,
    use_risk_sizing: bool = False,
    risk_per_trade: float = 0.01,
    max_portfolio_risk: float = 0.05,
    atr_stop_multiple: float = 2.0,
    min_stop_pct: float = 0.02,
    max_stop_pct: float = 0.15,
) -> dict:
    """Event-driven multi-symbol portfolio simulation with daily mark-to-market.

    Technical signals and optional ATR risk sizing use only information available
    on the entry date. Open positions are revalued on every available trading day
    using that symbol's historical closing price. This makes the equity curve,
    exposure and drawdown substantially more realistic than a booked-capital
    curve that stays flat between entry and exit.

    Stops are checked against subsequent daily lows until the normal horizon
    exit. A breached stop is still modeled as filled at the stop level; overnight
    gap-through, taxes, order-book depth and real fill uncertainty are not
    simulated. Round-trip friction is charged when a trade closes. Therefore the
    live mark-to-market curve does not pre-accrue future exit costs, while final
    trade P/L does include the full configured round-trip friction.
    """
    empty = {"trades": 0, "equity_curve": pd.DataFrame(), "trade_log": pd.DataFrame()}
    if not histories:
        return empty

    horizon_days = max(int(horizon_days), 1)
    max_positions = max(int(max_positions), 1)
    position_fraction = float(np.clip(position_fraction, 0.01, 1.0))
    cost = max(float(roundtrip_cost_bps), 0.0) / 10000.0
    risk_per_trade = float(np.clip(risk_per_trade, 0.0001, 1.0))
    max_portfolio_risk = float(np.clip(max_portfolio_risk, 0.0001, 1.0))
    atr_stop_multiple = max(float(atr_stop_multiple), 0.1)
    min_stop_pct = float(np.clip(min_stop_pct, 0.001, 0.99))
    max_stop_pct = float(np.clip(max_stop_pct, min_stop_pct, 0.99))

    candidates: list[dict] = []
    trading_dates: set[pd.Timestamp] = set()

    for symbol, history in histories.items():
        tech = build_technical_history(history)
        fwd_col = f"fwd_{horizon_days}d"
        if tech.empty or score_col not in tech.columns or fwd_col not in tech.columns:
            continue

        cols = [score_col, fwd_col]
        if "atr14_pct" in tech.columns:
            cols.append("atr14_pct")
        clean = tech[cols].dropna(subset=[score_col, fwd_col]).copy().sort_index()
        if clean.empty:
            continue

        raw = history.copy().sort_index()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
        if "Close" not in raw.columns:
            continue
        raw_close = pd.to_numeric(raw["Close"], errors="coerce").dropna()
        raw_low = pd.to_numeric(raw.get("Low"), errors="coerce") if "Low" in raw.columns else raw_close
        if raw_close.empty:
            continue

        for date, row in clean.iterrows():
            score = float(row[score_col])
            if not np.isfinite(score) or score < float(threshold):
                continue
            source_pos = tech.index.get_indexer([date])[0]
            exit_pos = source_pos + horizon_days
            if source_pos < 0 or exit_pos >= len(tech.index):
                continue

            entry_date = pd.Timestamp(date)
            normal_exit_date = pd.Timestamp(tech.index[exit_pos])
            if entry_date not in raw_close.index:
                continue
            entry_price = float(raw_close.loc[entry_date])
            if not np.isfinite(entry_price) or entry_price <= 0:
                continue

            gross_ret = float(row[fwd_col])
            if not np.isfinite(gross_ret):
                continue

            atr_pct = float(row.get("atr14_pct", np.nan))
            stop_pct = float(np.clip(atr_pct * atr_stop_multiple, min_stop_pct, max_stop_pct)) if np.isfinite(atr_pct) else min_stop_pct
            actual_exit_date = normal_exit_date
            stopped = False
            exit_price = entry_price * (1.0 + gross_ret)

            if use_risk_sizing:
                stop_price = entry_price * (1.0 - stop_pct)
                # Check only bars after the signal/entry close.
                path_dates = pd.DatetimeIndex(tech.index[source_pos + 1:exit_pos + 1])
                lows = raw_low.reindex(path_dates)
                breached = lows[lows <= stop_price].dropna()
                if not breached.empty:
                    actual_exit_date = pd.Timestamp(breached.index[0])
                    gross_ret = -stop_pct
                    exit_price = stop_price
                    stopped = True

            # Mark-to-market path uses only prices available from entry through
            # the modeled exit. Reindex later with forward-fill across exchange
            # holidays that differ between symbols.
            mark_prices = raw_close.loc[(raw_close.index >= entry_date) & (raw_close.index <= actual_exit_date)].copy()
            if mark_prices.empty:
                continue
            mark_prices.loc[entry_date] = entry_price
            if actual_exit_date not in mark_prices.index and not stopped:
                # The technical horizon should normally provide a closing price,
                # but keep the simulated exit value explicit if a source has a
                # sparse calendar.
                mark_prices.loc[actual_exit_date] = exit_price
            mark_prices = mark_prices.sort_index()

            candidates.append({
                "symbol": str(symbol),
                "entry_date": entry_date,
                "exit_date": actual_exit_date,
                "scheduled_exit_date": normal_exit_date,
                "score": score,
                "gross_return": gross_ret,
                "entry_price": entry_price,
                "exit_price": float(exit_price),
                "mark_prices": mark_prices,
                "stop_pct": stop_pct,
                "stopped": stopped,
            })
            trading_dates.update(pd.Timestamp(d) for d in mark_prices.index)
            trading_dates.add(entry_date)
            trading_dates.add(actual_exit_date)

    if not candidates:
        return empty

    by_date: dict[pd.Timestamp, list[dict]] = {}
    for row in candidates:
        by_date.setdefault(row["entry_date"], []).append(row)
    for rows in by_date.values():
        rows.sort(key=lambda x: (x["score"], x["symbol"]), reverse=True)

    dates = sorted(trading_dates)
    cash = 1.0
    open_positions: list[dict] = []
    trade_log: list[dict] = []
    curve: list[dict] = []
    rejected_capacity = 0
    rejected_risk = 0
    cumulative_realized_pnl = 0.0
    max_entry_risk_ratio = 0.0

    def _mark_price(pos: dict, date: pd.Timestamp) -> float:
        prices = pos.get("mark_prices")
        if not isinstance(prices, pd.Series) or prices.empty:
            return float(pos["entry_price"])
        eligible = prices.loc[prices.index <= date]
        if eligible.empty:
            return float(pos["entry_price"])
        price = float(eligible.iloc[-1])
        return price if np.isfinite(price) and price > 0 else float(pos["entry_price"])

    def _market_value(pos: dict, date: pd.Timestamp) -> float:
        entry = max(float(pos["entry_price"]), 1e-12)
        return max(float(pos["capital"]) * (_mark_price(pos, date) / entry), 0.0)

    for date in dates:
        # Close positions first. Stops use their modeled stop fill; scheduled
        # exits use the forward close return. Full configured round-trip friction
        # is charged here so final P/L remains conservative and explicit.
        still_open: list[dict] = []
        for pos in open_positions:
            if pos["exit_date"] <= date:
                gross_ret = float(pos["gross_return"])
                net_ret = max(gross_ret - cost, -1.0)
                proceeds = float(pos["capital"]) * (1.0 + net_ret)
                pnl = proceeds - float(pos["capital"])
                cash += proceeds
                cumulative_realized_pnl += pnl
                trade_log.append({
                    **{k: v for k, v in pos.items() if k != "mark_prices"},
                    "net_return": net_ret,
                    "pnl": pnl,
                    "risk_amount": float(pos.get("risk_amount", 0.0)),
                })
            else:
                still_open.append(pos)
        open_positions = still_open

        active_symbols = {p["symbol"] for p in open_positions}
        slots = max_positions - len(open_positions)
        for cand in by_date.get(date, []):
            if slots <= 0:
                rejected_capacity += 1
                continue
            if cand["symbol"] in active_symbols:
                continue

            invested_mtm = float(sum(_market_value(p, date) for p in open_positions))
            book_equity = cash + invested_mtm
            desired = position_fraction * book_equity

            if use_risk_sizing:
                stop_pct = max(float(cand["stop_pct"]), 1e-6)
                risk_sized_capital = (risk_per_trade * book_equity) / stop_pct
                desired = min(desired, risk_sized_capital)
                open_risk = float(sum(float(p.get("risk_amount", 0.0)) for p in open_positions))
                remaining_risk = max(max_portfolio_risk * book_equity - open_risk, 0.0)
                risk_capital_limit = remaining_risk / stop_pct
                desired = min(desired, risk_capital_limit)
                if desired <= 1e-12:
                    rejected_risk += 1
                    continue

            allocation = min(desired, cash)
            if allocation <= 1e-12:
                rejected_capacity += 1
                continue
            cash -= allocation
            risk_amount = allocation * float(cand["stop_pct"]) if use_risk_sizing else 0.0
            opened = {**cand, "capital": float(allocation), "risk_amount": float(risk_amount)}
            open_positions.append(opened)
            active_symbols.add(cand["symbol"])
            slots -= 1
            if use_risk_sizing:
                post_open_mtm = float(sum(_market_value(p, date) for p in open_positions))
                post_open_equity = cash + post_open_mtm
                post_open_risk = float(sum(float(p.get("risk_amount", 0.0)) for p in open_positions))
                if post_open_equity > 0:
                    max_entry_risk_ratio = max(max_entry_risk_ratio, post_open_risk / post_open_equity)

        invested_mtm = float(sum(_market_value(p, date) for p in open_positions))
        invested_cost = float(sum(float(p["capital"]) for p in open_positions))
        equity = cash + invested_mtm
        open_risk = float(sum(float(p.get("risk_amount", 0.0)) for p in open_positions))
        unrealized_pnl = invested_mtm - invested_cost
        curve.append({
            "date": date,
            "equity": equity,
            "cash": cash,
            "invested": invested_mtm,
            "invested_cost": invested_cost,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": cumulative_realized_pnl,
            "open_positions": len(open_positions),
            "exposure": invested_mtm / equity if equity > 0 else 0.0,
            "open_risk": open_risk / equity if equity > 0 else 0.0,
        })

    # Normally all positions have exited because every candidate contributes its
    # exit date to the calendar. Keep this defensive flush for sparse/bad input.
    for pos in list(open_positions):
        gross_ret = float(pos["gross_return"])
        net_ret = max(gross_ret - cost, -1.0)
        proceeds = float(pos["capital"]) * (1.0 + net_ret)
        pnl = proceeds - float(pos["capital"])
        cash += proceeds
        cumulative_realized_pnl += pnl
        trade_log.append({
            **{k: v for k, v in pos.items() if k != "mark_prices"},
            "net_return": net_ret,
            "pnl": pnl,
            "risk_amount": float(pos.get("risk_amount", 0.0)),
        })
    open_positions.clear()

    trades = pd.DataFrame(trade_log)
    eq = pd.DataFrame(curve)
    if not eq.empty:
        eq = eq.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        final_date = pd.Timestamp(max(t["exit_date"] for t in trade_log)) if trade_log else eq.index.max()
        eq.loc[final_date, [
            "equity", "cash", "invested", "invested_cost", "unrealized_pnl",
            "realized_pnl", "open_positions", "exposure", "open_risk"
        ]] = [cash, cash, 0.0, 0.0, 0.0, cumulative_realized_pnl, 0, 0.0, 0.0]
        eq = eq.sort_index()
        peak = eq["equity"].cummax()
        eq["drawdown"] = eq["equity"] / peak.replace(0, np.nan) - 1.0

    if trades.empty:
        return {
            "trades": 0,
            "rejected_capacity": int(rejected_capacity),
            "rejected_risk": int(rejected_risk),
            "equity_curve": eq,
            "trade_log": trades,
        }

    net = pd.to_numeric(trades["net_return"], errors="coerce").dropna()
    wins = net[net > 0]
    losses = net[net < 0]
    gp = float(wins.sum()) if not wins.empty else 0.0
    gl = abs(float(losses.sum())) if not losses.empty else 0.0
    pf = gp / gl if gl > 0 else np.nan
    final_equity = float(cash)
    max_dd = float(eq["drawdown"].min()) if not eq.empty and "drawdown" in eq else 0.0
    avg_exposure = float(eq["exposure"].mean()) if not eq.empty else 0.0
    max_exposure = float(eq["exposure"].max()) if not eq.empty else 0.0
    max_open_risk = float(eq["open_risk"].max()) if not eq.empty and "open_risk" in eq else 0.0
    stop_rate = float(trades["stopped"].astype(bool).mean()) if "stopped" in trades.columns else 0.0
    return {
        "trades": int(len(trades)),
        "symbols_traded": int(trades["symbol"].nunique()),
        "win_rate": float((net > 0).mean()),
        "median_return": float(net.median()),
        "mean_return": float(net.mean()),
        "profit_factor": float(pf) if np.isfinite(pf) else np.nan,
        "total_return": final_equity - 1.0,
        "final_equity": final_equity,
        "max_drawdown": max_dd,
        "avg_exposure": avg_exposure,
        "max_exposure": max_exposure,
        "max_open_risk": max_open_risk,
        "max_entry_risk": float(max_entry_risk_ratio),
        "stop_rate": stop_rate,
        "rejected_capacity": int(rejected_capacity),
        "rejected_risk": int(rejected_risk),
        "equity_curve": eq,
        "trade_log": trades.sort_values(["entry_date", "score"], ascending=[True, False]).reset_index(drop=True),
    }
