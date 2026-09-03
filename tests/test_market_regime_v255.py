import pandas as pd

from market_regime import (
    add_market_regime,
    classify_market,
    required_score_adjustment,
)

def market_df(m1, m3, suffix=".ST"):
    rows=[]
    for i,(a,b) in enumerate(zip(m1,m3)):
        rows.append({
            "Ticker":f"X{i}{suffix}",
            "1 mån":a,
            "3 mån":b,
            "Daytrade Score":75,
            "Mellan Score":75,
            "Lång Score":75,
            "Livstid Score":75,
        })
    return pd.DataFrame(rows)

def test_strong_market_never_lowers_buy_threshold():
    df=market_df([.05,.04,.03,.02,.06,.01],[.10,.08,.07,.06,.12,.09])
    result=classify_market(df)
    assert result["Marknadsläge"]=="STARK"
    for horizon in ("day","medium","long","lifetime"):
        assert required_score_adjustment("STARK",horizon)==0

def test_weak_market_raises_requirements():
    df=market_df([-.08,-.06,-.04,-.02,-.07,.01],[-.15,-.12,-.10,-.09,-.11,.01])
    result=classify_market(df)
    assert result["Marknadsläge"] in {"SVAG","MYCKET SVAG"}
    assert required_score_adjustment(result["Marknadsläge"],"medium") > 0

def test_very_weak_market_is_most_conservative():
    assert required_score_adjustment("MYCKET SVAG","day") > required_score_adjustment("SVAG","day")
    assert required_score_adjustment("MYCKET SVAG","medium") > required_score_adjustment("SVAG","medium")

def test_too_little_market_data_does_not_change_thresholds():
    df=market_df([-.10,-.10,-.10],[-.20,-.20,-.20])
    result=classify_market(df)
    assert result["Marknadsläge"]=="FÖR LITE UNDERLAG"
    assert required_score_adjustment(result["Marknadsläge"],"day")==0

def test_added_regime_can_block_score_that_passes_normal_threshold():
    df=market_df([-.08,-.06,-.04,-.02,-.07,.01],[-.15,-.12,-.10,-.09,-.11,.01])
    df["Daytrade Score"]=69.0
    out=add_market_regime(df,"day")
    assert (out["Marknadsläge"].isin(["SVAG","MYCKET SVAG"])).all()
    assert (~out["Marknadskrav godkänd"]).all()

def test_markets_are_evaluated_separately():
    sw=market_df([-.08,-.06,-.04,-.02,-.07,.01],[-.15,-.12,-.10,-.09,-.11,.01],".ST")
    us=market_df([.05,.04,.03,.02,.06,.01],[.10,.08,.07,.06,.12,.09],"")
    out=add_market_regime(pd.concat([sw,us],ignore_index=True),"day")
    sw_status=set(out[out["Ticker"].str.endswith(".ST")]["Marknadsläge"])
    us_status=set(out[~out["Ticker"].str.endswith(".ST")]["Marknadsläge"])
    assert sw_status != us_status
