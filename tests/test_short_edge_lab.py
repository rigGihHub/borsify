import numpy as np
import pandas as pd
from short_edge_lab import (
    build_point_in_time_short_signals, add_forward_returns, evaluate_thresholds,
    walk_forward_threshold_test, component_bucket_analysis, summarize_edge,
)

def make_prices(n=900, drift=0.0007, seed=1):
    rng = np.random.default_rng(seed)
    rets = drift + rng.normal(0, 0.012, n)
    close = 100 * np.exp(np.cumsum(rets))
    vol = rng.integers(100_000, 250_000, n)
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame({"Close": close, "Volume": vol}, index=idx)

def test_no_forward_data_inside_signal_builder():
    sig = build_point_in_time_short_signals(make_prices())
    assert "ShortProxy" in sig
    assert not any(c.startswith("Fwd_") for c in sig.columns)

def test_forward_returns_added_separately():
    sig = add_forward_returns(build_point_in_time_short_signals(make_prices()))
    assert {"Fwd_1m","Fwd_3m","Fwd_6m"} <= set(sig.columns)
    assert sig["Fwd_6m"].tail(126).isna().all()

def test_falling_knife_is_capped():
    px = make_prices()
    px.loc[px.index[-80]:, "Close"] = np.linspace(px["Close"].iloc[-81], px["Close"].iloc[-81]*0.45, 80)
    sig = build_point_in_time_short_signals(px)
    veto = sig[sig["FallingKnifeVeto"]]
    assert len(veto) > 0
    assert veto["ShortProxy"].max() <= 54

def test_threshold_eval_has_forward_horizons():
    sig = add_forward_returns(build_point_in_time_short_signals(make_prices()))
    ev = evaluate_thresholds(sig, [55,65])
    assert set(ev["Horizon"]).issubset({"1m","3m","6m"})
    assert "HitRate" in ev

def test_walk_forward_train_precedes_test():
    sig = add_forward_returns(build_point_in_time_short_signals(make_prices(1200)))
    wf = walk_forward_threshold_test(sig, min_train_days=504, test_days=126)
    if not wf.empty:
        assert (pd.to_datetime(wf["TrainEnd"]) < pd.to_datetime(wf["TestStart"])).all()

def test_component_quartiles():
    sig = add_forward_returns(build_point_in_time_short_signals(make_prices()))
    q = component_bucket_analysis(sig, "Relative", "3m")
    if not q.empty:
        assert q["Signals"].sum() > 0

def test_summary_is_cautious():
    sig = add_forward_returns(build_point_in_time_short_signals(make_prices()))
    s = summarize_edge(evaluate_thresholds(sig), walk_forward_threshold_test(sig))
    assert "point-in-time" in s["message"]
    assert s["status"] in {
        "Historiskt lovande – ej bevisad alpha",
        "In-sample lovande – kräver bättre OOS-stöd",
        "Ingen tydlig historisk edge",
        "Otillräcklig data",
    }
