import numpy as np
import pandas as pd

from daytrade_validation import (
    build_point_in_time_daytrade,
    evaluate_daytrade,
    walk_forward_fixed_gate,
    validation_grade,
    compare_horizons,
)


def synthetic_prices(n=900, seed=7):
    rng=np.random.default_rng(seed)
    idx=pd.bdate_range("2022-01-03", periods=n)
    # Slow positive drift with cyclical bursts; enough structure to exercise the engine.
    ret=0.00035 + 0.006*np.sin(np.arange(n)/18.0) + rng.normal(0,0.009,n)
    close=100*np.cumprod(1+ret)
    overnight=rng.normal(0,0.002,n)
    open_=np.r_[close[0], close[:-1]*(1+overnight[1:])]
    volume=1_000_000*(1+0.35*np.sin(np.arange(n)/11.0))+rng.normal(0,120_000,n)
    volume=np.maximum(volume,50_000)
    return pd.DataFrame({"Open":open_,"High":np.maximum(open_,close)*1.01,
                         "Low":np.minimum(open_,close)*.99,"Close":close,
                         "Volume":volume},index=idx)


def test_point_in_time_daytrade_has_next_open_returns():
    pit=build_point_in_time_daytrade(synthetic_prices())
    assert not pit.empty
    assert {"DaytradeProxy","BuyGateProxy","EntryNextOpen","Gross1d","Gross2d"} <= set(pit.columns)
    # Entry after signal day: at row t it must equal next row's open.
    assert np.isclose(pit["EntryNextOpen"].iloc[300], pit["Open"].iloc[301])


def test_forward_return_does_not_use_same_close_as_entry():
    pit=build_point_in_time_daytrade(synthetic_prices())
    i=350
    expected=pit["Close"].iloc[i+1]/pit["Open"].iloc[i+1]-1
    assert np.isclose(pit["Gross1d"].iloc[i], expected)


def test_costs_reduce_net_median():
    pit=build_point_in_time_daytrade(synthetic_prices())
    zero=evaluate_daytrade(pit,1,0)
    costly=evaluate_daytrade(pit,1,50)
    if zero.get("signals",0):
        assert costly["net_median"] <= zero["net_median"]


def test_walk_forward_uses_fixed_gate_and_returns_sequential_windows():
    pit=build_point_in_time_daytrade(synthetic_prices())
    wf=walk_forward_fixed_gate(pit,1,20,min_train_days=300,test_days=100)
    assert not wf.empty
    assert {"TestStart","TestEnd","Signals","NetMedian","HitRate","MedianExcess"} <= set(wf.columns)
    assert all(pd.to_datetime(wf["TestStart"]).diff().dropna().dt.days > 0)


def test_grade_never_calls_result_proven_alpha():
    pit=build_point_in_time_daytrade(synthetic_prices())
    stats=evaluate_daytrade(pit,1,20)
    wf=walk_forward_fixed_gate(pit,1,20,min_train_days=300,test_days=100)
    grade=validation_grade(stats,wf)
    assert "bevisad alpha" not in grade["status"].lower()
    assert grade["status"] in {
        "Ej validerad",
        "Historiskt lovande – ej bevisad edge",
        "Svagt/blandat historiskt stöd",
        "Ingen tydlig historisk edge",
    }


def test_compare_horizons_returns_one_and_two_days():
    pit=build_point_in_time_daytrade(synthetic_prices())
    out=compare_horizons(pit,20,min_train_days=300,test_days=100)
    assert len(out)==2
    assert set(out["Horisont"])=={"1 handelsdag","2 handelsdagar"}
