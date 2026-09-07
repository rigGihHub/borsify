import pandas as pd
from relative_strength import add_relative_strength


def _df():
    return pd.DataFrame([
        {"Ticker":"A.ST","Sektor":"Industri","Bransch":"Maskiner","1 mån":.10,"3 mån":.20},
        {"Ticker":"B.ST","Sektor":"Industri","Bransch":"Maskiner","1 mån":.04,"3 mån":.08},
        {"Ticker":"C.ST","Sektor":"Industri","Bransch":"Maskiner","1 mån":.03,"3 mån":.06},
        {"Ticker":"D.ST","Sektor":"Industri","Bransch":"Maskiner","1 mån":.02,"3 mån":.04},
        {"Ticker":"E.ST","Sektor":"Industri","Bransch":"Bygg","1 mån":.01,"3 mån":.02},
        {"Ticker":"F.ST","Sektor":"Bank","Bransch":"Banker","1 mån":.00,"3 mån":.01},
        {"Ticker":"G.ST","Sektor":"Bank","Bransch":"Banker","1 mån":-.01,"3 mån":.00},
        {"Ticker":"H.ST","Sektor":"Bank","Bransch":"Banker","1 mån":.01,"3 mån":.02},
    ])


def test_peer_comparison_excludes_stock_itself_and_uses_same_industry():
    out=add_relative_strength(_df())
    row=out.loc[out["Ticker"].eq("A.ST")].iloc[0]
    assert row["Peer 3 mån"] == .06
    assert row["Relativ peer 3 mån"] > 0
    assert "3 jämförbara bolag i Maskiner" in row["Relativ styrka underlag"]


def test_peer_falls_back_to_same_sector_when_industry_too_small():
    out=add_relative_strength(_df())
    row=out.loc[out["Ticker"].eq("E.ST")].iloc[0]
    assert pd.notna(row["Peer 3 mån"])
    assert "peers:" in row["Relativ styrka underlag"]


def test_peer_is_missing_when_fewer_than_three_other_comparables():
    df=pd.DataFrame([
        {"Ticker":"A.ST","Sektor":"Energi","Bransch":"Olja","1 mån":.1,"3 mån":.2},
        {"Ticker":"B.ST","Sektor":"Energi","Bransch":"Olja","1 mån":.0,"3 mån":.1},
        {"Ticker":"C.ST","Sektor":"Energi","Bransch":"Olja","1 mån":.0,"3 mån":.0},
    ])
    out=add_relative_strength(df)
    row=out.iloc[0]
    assert pd.isna(row["Peer 3 mån"])
    assert "peers: för lite underlag" in row["Relativ styrka underlag"]


def test_benchmark_keeps_market_sector_and_peer_layers_separate():
    out=add_relative_strength(_df())
    row=out.loc[out["Ticker"].eq("A.ST")].iloc[0]
    for col in ["Relativ marknad 3 mån","Relativ sektor 3 mån","Relativ peer 3 mån"]:
        assert pd.notna(row[col])
