import pandas as pd
from search_filters import apply_country_price_filters

def sample():
    return pd.DataFrame([
        {"Ticker":"A.ST","Land":"Sverige","Pris SEK":95.0},
        {"Ticker":"B","Land":"USA","Pris SEK":250.0},
        {"Ticker":"C.DE","Land":"Tyskland","Pris SEK":410.0},
        {"Ticker":"D.CO","Land":"Danmark","Pris SEK":150.0},
    ])

def test_country_filter_keeps_only_selected_countries():
    out=apply_country_price_filters(sample(),countries=["Sverige","Danmark"])
    assert set(out["Ticker"])=={"A.ST","D.CO"}

def test_empty_country_selection_returns_no_results():
    out=apply_country_price_filters(sample(),countries=[])
    assert out.empty

def test_price_range_uses_sek_column():
    out=apply_country_price_filters(sample(),countries=["Sverige","USA","Tyskland","Danmark"],min_price_sek=100,max_price_sek=300)
    assert set(out["Ticker"])=={"B","D.CO"}

def test_zero_bounds_mean_no_price_boundary():
    out=apply_country_price_filters(sample(),countries=["Sverige","USA","Tyskland","Danmark"],min_price_sek=0,max_price_sek=0)
    assert len(out)==4

def test_missing_price_is_excluded_when_price_filter_is_active():
    df=sample()
    df.loc[len(df)]={"Ticker":"E","Land":"USA","Pris SEK":None}
    out=apply_country_price_filters(df,countries=["USA"],min_price_sek=1,max_price_sek=0)
    assert out["Ticker"].tolist()==["B"]
