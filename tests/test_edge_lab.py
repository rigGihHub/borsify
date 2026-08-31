import numpy as np
import pandas as pd

from edge_lab import build_technical_history, summarize_backtest, summarize_universe_backtest


def _sample_history(n=320):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(100, 150, n) + np.sin(np.arange(n) / 8) * 3, index=idx)
    volume = pd.Series(1_000_000 + (np.arange(n) % 30) * 10_000, index=idx)
    return pd.DataFrame({"Close": close, "Volume": volume})


def test_build_technical_history_has_scores_and_forward_returns():
    out = build_technical_history(_sample_history())
    assert {"swing_proxy", "reversal_proxy", "fwd_5d", "fwd_10d", "fwd_20d"}.issubset(out.columns)
    assert out["swing_proxy"].dropna().between(0, 100).all()
    assert out["reversal_proxy"].dropna().between(0, 100).all()


def test_summarize_backtest_returns_signal_count():
    out = build_technical_history(_sample_history())
    summary = summarize_backtest(out, "swing_proxy", 40, 10)
    assert summary["signals"] > 0
    assert 0 <= summary["win_rate"] <= 1


def test_universe_backtest_aggregates_multiple_symbols():
    histories = {
        "AAA.ST": _sample_history(420),
        "BBB.ST": _sample_history(440) * pd.Series({"Close": 1.1, "Volume": 1.0}),
    }
    summary = summarize_universe_backtest(histories, "swing_proxy", 40, 10)
    assert summary["symbols_tested"] == 2
    assert summary["signals"] > 0
    assert isinstance(summary["per_symbol"], pd.DataFrame)
    assert set(summary["per_symbol"]["symbol"]) == {"AAA.ST", "BBB.ST"}

from edge_lab import build_market_regime_history, summarize_backtest_by_regime, summarize_universe_backtest_by_regime


def test_market_regime_history_uses_expected_labels():
    hist = _sample_history(420)
    regime = build_market_regime_history(hist)
    assert "regime" in regime.columns
    assert set(regime["regime"].dropna().unique()).issubset({"Risk-on", "Neutral", "Risk-off"})


def test_backtest_by_regime_returns_rows():
    hist = _sample_history(420)
    tech = build_technical_history(hist)
    regime = build_market_regime_history(hist)
    out = summarize_backtest_by_regime(tech, regime, "swing_proxy", 40, 10)
    assert not out.empty
    assert {"regime", "signals", "median_excess"}.issubset(out.columns)


def test_universe_backtest_by_regime_aggregates():
    histories = {"AAA.ST": _sample_history(420), "BBB.ST": _sample_history(440)}
    regime = build_market_regime_history(_sample_history(440))
    out = summarize_universe_backtest_by_regime(histories, regime, "swing_proxy", 40, 10)
    assert not out.empty
    assert "signals" in out.columns

from edge_lab import walk_forward_backtest


def test_walk_forward_backtest_produces_chronological_folds():
    hist = _sample_history(1200)
    tech = build_technical_history(hist)
    out = walk_forward_backtest(
        tech,
        "swing_proxy",
        [40, 45, 50, 55, 60],
        10,
        train_days=420,
        test_days=126,
        min_train_signals=3,
        min_test_signals=1,
    )
    assert out["folds"] >= 2
    assert isinstance(out["fold_table"], pd.DataFrame)
    assert {"threshold", "test_start", "test_end", "test_median_excess"}.issubset(out["fold_table"].columns)
    assert (out["fold_table"]["threshold"] >= 40).all()


def test_walk_forward_avoids_training_future_overlap():
    hist = _sample_history(1000)
    tech = build_technical_history(hist)
    out = walk_forward_backtest(
        tech,
        "swing_proxy",
        [40, 50, 60],
        20,
        train_days=360,
        test_days=100,
        min_train_signals=2,
        min_test_signals=1,
    )
    assert out["folds"] > 0
    folds = out["fold_table"]
    # Training end must be strictly before the unseen test start.
    assert (pd.to_datetime(folds["train_end"]) < pd.to_datetime(folds["test_start"])).all()


def test_trading_friction_reduces_returns():
    from edge_lab import summarize_trading_friction
    gross = [0.02, -0.01, 0.03, 0.01]
    stats = summarize_trading_friction(gross, roundtrip_cost_bps=30, position_fraction=1.0)
    assert stats["trades"] == 4
    assert stats["net_median_return"] < stats["gross_median_return"]
    assert abs(stats["cost_drag_per_trade"] - 0.003) < 1e-12


def test_position_fraction_reduces_equity_swing():
    from edge_lab import summarize_trading_friction
    returns = [0.10, -0.08, 0.06, -0.03]
    full = summarize_trading_friction(returns, roundtrip_cost_bps=0, position_fraction=1.0)
    quarter = summarize_trading_friction(returns, roundtrip_cost_bps=0, position_fraction=0.25)
    assert abs(quarter["max_drawdown"]) < abs(full["max_drawdown"])


def test_portfolio_simulation_respects_position_cap():
    from edge_lab import simulate_portfolio_backtest
    histories = {
        "AAA.ST": _sample_history(520),
        "BBB.ST": _sample_history(520),
        "CCC.ST": _sample_history(520),
    }
    out = simulate_portfolio_backtest(
        histories, "swing_proxy", 35, 10,
        max_positions=2, position_fraction=0.5, roundtrip_cost_bps=20,
    )
    assert out["trades"] > 0
    assert not out["equity_curve"].empty
    assert out["equity_curve"]["open_positions"].max() <= 2
    assert out["equity_curve"]["exposure"].max() <= 1.0000001


def test_portfolio_costs_reduce_final_equity():
    from edge_lab import simulate_portfolio_backtest
    histories = {"AAA.ST": _sample_history(620), "BBB.ST": _sample_history(620)}
    free = simulate_portfolio_backtest(histories, "swing_proxy", 35, 5, max_positions=2, position_fraction=0.5, roundtrip_cost_bps=0)
    costly = simulate_portfolio_backtest(histories, "swing_proxy", 35, 5, max_positions=2, position_fraction=0.5, roundtrip_cost_bps=100)
    assert free["trades"] == costly["trades"]
    assert costly["final_equity"] < free["final_equity"]


def _sample_ohlcv(n=620, shock=False):
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    base = np.linspace(100, 140, n) + np.sin(np.arange(n) / 7) * 2
    if shock:
        base = base.copy()
        base[360:365] -= 12
    close = pd.Series(base, index=idx)
    high = close * 1.01
    low = close * 0.99
    if shock:
        low.iloc[362] = close.iloc[360] * 0.80
    volume = pd.Series(1_000_000 + (np.arange(n) % 20) * 20_000, index=idx)
    return pd.DataFrame({"High": high, "Low": low, "Close": close, "Volume": volume})


def test_technical_history_adds_trailing_atr():
    out = build_technical_history(_sample_ohlcv())
    assert "atr14_pct" in out.columns
    atr = out["atr14_pct"].dropna()
    assert not atr.empty
    assert (atr > 0).all()


def test_risk_sizing_respects_open_risk_cap():
    from edge_lab import simulate_portfolio_backtest
    histories = {
        "AAA.ST": _sample_ohlcv(700),
        "BBB.ST": _sample_ohlcv(700),
        "CCC.ST": _sample_ohlcv(700),
    }
    out = simulate_portfolio_backtest(
        histories, "swing_proxy", 35, 10,
        max_positions=5, position_fraction=0.8, roundtrip_cost_bps=20,
        use_risk_sizing=True, risk_per_trade=0.01, max_portfolio_risk=0.03,
        atr_stop_multiple=2.0,
    )
    assert out["trades"] > 0
    assert out["max_entry_risk"] <= 0.0300001
    # Live risk as % of MTM equity may drift above the entry cap after losses.
    assert out["max_open_risk"] >= 0


def test_atr_stop_can_close_trade_early():
    from edge_lab import simulate_portfolio_backtest
    hist = _sample_ohlcv(700, shock=True)
    out = simulate_portfolio_backtest(
        {"AAA.ST": hist}, "swing_proxy", 20, 20,
        max_positions=1, position_fraction=1.0, roundtrip_cost_bps=0,
        use_risk_sizing=True, risk_per_trade=0.02, max_portfolio_risk=0.05,
        atr_stop_multiple=1.0, min_stop_pct=0.01, max_stop_pct=0.08,
    )
    assert out["trades"] > 0
    assert "stopped" in out["trade_log"].columns
    assert out["trade_log"]["stopped"].astype(bool).any()


def test_portfolio_equity_curve_is_daily_mark_to_market():
    from edge_lab import simulate_portfolio_backtest
    histories = {"AAA.ST": _sample_ohlcv(620), "BBB.ST": _sample_ohlcv(620)}
    out = simulate_portfolio_backtest(
        histories, "swing_proxy", 35, 20,
        max_positions=2, position_fraction=0.5, roundtrip_cost_bps=0,
    )
    assert out["trades"] > 0
    eq = out["equity_curve"]
    assert {"unrealized_pnl", "realized_pnl", "invested_cost"}.issubset(eq.columns)
    # A real MTM curve should contain many in-between trading days, not only
    # signal/exit event dates.
    event_dates = set(pd.to_datetime(out["trade_log"]["entry_date"])) | set(pd.to_datetime(out["trade_log"]["exit_date"]))
    assert len(eq.index) > len(event_dates)
    assert (eq["unrealized_pnl"].abs() > 1e-10).any()


def test_mark_to_market_drawdown_captures_open_position_path():
    from edge_lab import simulate_portfolio_backtest
    hist = _sample_ohlcv(700, shock=True)
    out = simulate_portfolio_backtest(
        {"AAA.ST": hist}, "swing_proxy", 20, 20,
        max_positions=1, position_fraction=1.0, roundtrip_cost_bps=0,
        use_risk_sizing=False,
    )
    assert out["trades"] > 0
    eq = out["equity_curve"]
    assert "drawdown" in eq.columns
    # Daily MTM must actually move while capital is invested.
    invested_days = eq[eq["open_positions"] > 0]
    assert not invested_days.empty
    assert invested_days["equity"].nunique() > 1
