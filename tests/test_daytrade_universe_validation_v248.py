import numpy as np
import pandas as pd

from daytrade_universe_validation import (
    split_downloaded_histories, validate_universe, universe_validation_label,
)

def make_prices(n=900, seed=1):
    rng=np.random.default_rng(seed)
    idx=pd.bdate_range("2022-01-03",periods=n)
    ret=.0004+.005*np.sin(np.arange(n)/15)+rng.normal(0,.009,n)
    close=100*np.cumprod(1+ret)
    open_=np.r_[close[0],close[:-1]*(1+rng.normal(0,.002,n-1))]
    vol=np.maximum(10000,1_000_000*(1+.4*np.sin(np.arange(n)/10))+rng.normal(0,100000,n))
    return pd.DataFrame({"Open":open_,"High":np.maximum(open_,close)*1.01,
                         "Low":np.minimum(open_,close)*.99,"Close":close,"Volume":vol},index=idx)

def test_validate_universe_aggregates_multiple_symbols():
    histories={f"S{i}":make_prices(seed=i) for i in range(1,7)}
    per_symbol,by_country,summary=validate_universe(
        histories,horizon_days=2,roundtrip_cost_bps=20,
        country_fn=lambda s: "Sverige" if s in {"S1","S2","S3"} else "USA",
    )
    assert summary["symbols_tested"]==6
    assert "Median efter kostnader" in per_symbol.columns
    assert set(by_country["Land"]).issubset({"Sverige","USA"})

def test_label_is_plain_swedish_and_cautious():
    label,message=universe_validation_label({
        "signals":100,"symbols_with_signals":10,"median_net":.01,"positive_symbols_share":.7
    })
    assert "Lovande" in label
    assert ("framtid" in message) or ("framöver" in message)

def test_split_multiindex_download():
    idx=pd.bdate_range("2025-01-01",periods=5)
    cols=pd.MultiIndex.from_product([["AAA","BBB"],["Open","Close","Volume"]])
    df=pd.DataFrame(np.ones((5,len(cols))),index=idx,columns=cols)
    out=split_downloaded_histories(df,["AAA","BBB"])
    assert set(out)=={"AAA","BBB"}
    assert "Close" in out["AAA"].columns
