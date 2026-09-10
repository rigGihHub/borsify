import pandas as pd
from value_chain_readthrough_engine import add_value_chain_readthrough, select_value_chain_candidates


def _frame():
    return pd.DataFrame([
        {"Ticker":"CHIP.ST","Namn":"ChipCo","Sektor":"Technology","Bransch":"Semiconductors","Report Delta kandidat":True,"Report Delta positiva":5,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":1,"1 mån":0.04},
        {"Ticker":"AUTO.ST","Namn":"AutoCo","Sektor":"Consumer Cyclical","Bransch":"Auto Manufacturers","Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.01},
        {"Ticker":"BANK.ST","Namn":"BankCo","Sektor":"Financial Services","Bransch":"Banks - Regional","Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.01},
    ])


def test_directional_value_chain_can_surface_supported_target():
    out=add_value_chain_readthrough(_frame()); row=out.query('Ticker=="AUTO.ST"').iloc[0]
    assert bool(row["Värdekedja kandidat"]) is True
    assert "fordonselektronik" in row["Värdekedja relation"]
    assert "bevisar inte" in row["Värdekedja förklaring"]


def test_unrelated_industry_does_not_inherit_signal():
    row=add_value_chain_readthrough(_frame()).query('Ticker=="BANK.ST"').iloc[0]
    assert bool(row["Värdekedja kandidat"]) is False


def test_target_needs_own_fundamental_support_and_negative_overrides():
    df=_frame(); df.loc[df.Ticker=="AUTO.ST","Fundamental upptäckt antal"]=0
    assert not bool(add_value_chain_readthrough(df).query('Ticker=="AUTO.ST"').iloc[0]["Värdekedja kandidat"])
    df=_frame(); df.loc[df.Ticker=="AUTO.ST","Ledningssignal varning"]=True
    row=add_value_chain_readthrough(df).query('Ticker=="AUTO.ST"').iloc[0]
    assert not bool(row["Värdekedja kandidat"]); assert "motbevis" in row["Värdekedja status"]


def test_runup_blocks_candidate():
    df=_frame(); df.loc[df.Ticker=="AUTO.ST","1 mån"]=0.15
    row=add_value_chain_readthrough(df).query('Ticker=="AUTO.ST"').iloc[0]
    assert not bool(row["Värdekedja kandidat"]); assert "redan rört" in row["Värdekedja status"]


def test_selector_and_wiring_no_new_score():
    out=add_value_chain_readthrough(_frame())
    assert select_value_chain_candidates(out,1)[0][0]==1
    app=open('app.py',encoding='utf-8').read(); fin=open('finalist_selection.py',encoding='utf-8').read(); led=open('recommendation_ledger.py',encoding='utf-8').read(); mod=open('value_chain_readthrough_engine.py',encoding='utf-8').read()
    assert 'APP_VERSION = "3.73.0"' in app
    assert 'add_value_chain_readthrough(discovery_pool)' in app
    assert 'bq_value_chain_radar' in app
    assert 'reason_keys[idx] = "value_chain_readthrough"' in fin
    assert '"Värdekedja status"' in led
    assert 'Värdekedja Score' not in mod
