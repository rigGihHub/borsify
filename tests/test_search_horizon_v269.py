import pandas as pd
from search_horizon import apply_search_horizon

def score_builder(df):
    out=df.copy()
    out["Daytrade Score"]=[90,40]
    out["Mellan Score"]=[80,60]
    out["Lång Score"]=[45,95]
    out["Livstid Score"]=[40,98]
    return out

def sample():
    return pd.DataFrame([
        {"Ticker":"FAST","Match Score":50,"Datatäckning":.9},
        {"Ticker":"LONG","Match Score":50,"Datatäckning":.9},
    ])

def test_short_horizon_prioritizes_short_term_strength():
    out=apply_search_horizon(sample(),"1–2 dagar",score_builder)
    assert out.iloc[0]["Ticker"]=="FAST"
    assert "Sökpoäng" in out.columns

def test_long_horizon_prioritizes_long_term_quality():
    out=apply_search_horizon(sample(),"1–5 år",score_builder)
    assert out.iloc[0]["Ticker"]=="LONG"

def test_all_horizons_preserve_current_order_without_new_score():
    df=sample()
    out=apply_search_horizon(df,"Alla tidshorisonter",score_builder)
    assert out["Ticker"].tolist()==df["Ticker"].tolist()
    assert "Sökpoäng" not in out.columns
