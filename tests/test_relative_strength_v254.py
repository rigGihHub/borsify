import pandas as pd
from relative_strength import add_relative_strength, relative_strength_label

def make_df():
    return pd.DataFrame([
        {"Ticker":"A.ST","Sektor":"Industri","1 mån":.10,"3 mån":.20},
        {"Ticker":"B.ST","Sektor":"Industri","1 mån":.04,"3 mån":.08},
        {"Ticker":"C.ST","Sektor":"Industri","1 mån":.03,"3 mån":.06},
        {"Ticker":"D.ST","Sektor":"Bank","1 mån":.01,"3 mån":.02},
        {"Ticker":"E.ST","Sektor":"Bank","1 mån":.00,"3 mån":.01},
        {"Ticker":"F.ST","Sektor":"Bank","1 mån":-.01,"3 mån":.00},
    ])

def test_strong_stock_beats_market_and_sector():
    out=add_relative_strength(make_df())
    row=out[out["Ticker"]=="A.ST"].iloc[0]
    assert row["Relativ marknad 3 mån"] > 0
    assert row["Relativ sektor 3 mån"] > 0
    assert row["Relativ styrka"] > 50

def test_sector_strength_detects_stronger_sector():
    out=add_relative_strength(make_df())
    row=out[out["Ticker"]=="A.ST"].iloc[0]
    assert row["Sektorstyrka 3 mån"] > 0

def test_unknown_or_small_sector_is_not_fabricated():
    df=make_df()
    df.loc[len(df)]={"Ticker":"G.ST","Sektor":"Energi","1 mån":.25,"3 mån":.30}
    out=add_relative_strength(df)
    row=out[out["Ticker"]=="G.ST"].iloc[0]
    assert pd.isna(row["Relativ sektor 3 mån"])
    assert "1 aktier i samma sektor" in row["Relativ styrka underlag"]

def test_label_is_plain_swedish():
    assert relative_strength_label({"Relativ styrka":75})=="Starkare än jämförelsen"
    assert relative_strength_label({"Relativ styrka":40})=="Svagare än jämförelsen"
