import pandas as pd

from sector_readthrough_engine import add_sector_readthrough, select_sector_readthrough_candidates


def _frame():
    return pd.DataFrame([
        {"Ticker":"SRC.ST","Namn":"Source","Sektor":"Industrials","Bransch":"Machinery","Report Delta kandidat":True,"Report Delta positiva":5,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":1,"1 mån":0.08},
        {"Ticker":"PEER.ST","Namn":"Peer","Sektor":"Industrials","Bransch":"Machinery","Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"Fundamentala upptäcktslinser":"Lönsam tillväxt","1 mån":0.01},
        {"Ticker":"OTHER.ST","Namn":"Other","Sektor":"Technology","Bransch":"Software","Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.00},
    ])


def test_same_sector_peer_with_own_fundamental_support_can_be_candidate():
    out = add_sector_readthrough(_frame())
    peer = out[out.Ticker == "PEER.ST"].iloc[0]
    assert bool(peer["Sektorläsning kandidat"]) is True
    assert peer["Sektorläsning nivå"] == "samma bransch"
    assert "Source" in peer["Sektorläsning källbolag"]
    assert "inte bevis" in peer["Sektorläsning förklaring"]


def test_no_own_fundamental_support_means_no_candidate():
    df = _frame(); df.loc[df.Ticker == "PEER.ST", "Fundamental upptäckt antal"] = 0
    peer = add_sector_readthrough(df).query('Ticker == "PEER.ST"').iloc[0]
    assert bool(peer["Sektorläsning kandidat"]) is False
    assert "saknar eget fundamentalt stöd" in peer["Sektorläsning status"]


def test_own_negative_evidence_overrides_sector_signal():
    df = _frame(); df.loc[df.Ticker == "PEER.ST", "Ledningssignal varning"] = True
    peer = add_sector_readthrough(df).query('Ticker == "PEER.ST"').iloc[0]
    assert bool(peer["Sektorläsning kandidat"]) is False
    assert "motbevis" in peer["Sektorläsning status"]


def test_already_run_peer_does_not_get_discovery_doorway():
    df = _frame(); df.loc[df.Ticker == "PEER.ST", "1 mån"] = 0.13
    peer = add_sector_readthrough(df).query('Ticker == "PEER.ST"').iloc[0]
    assert bool(peer["Sektorläsning kandidat"]) is False
    assert "redan rört" in peer["Sektorläsning status"]


def test_selector_prefers_stronger_independent_readthrough():
    df = pd.DataFrame({
        "Ticker":["A","B"], "Sektorläsning kandidat":[True,True], "Sektorläsning stark":[False,True],
        "Sektorläsning källor antal":[1,2], "Fundamental upptäckt antal":[2,1], "1 mån":[0.0,0.05],
    }, index=[10,20])
    assert select_sector_readthrough_candidates(df, quota=1) == [(20, "Sektorläsning")]


def test_v358_wiring_and_no_new_score():
    app = open("app.py", encoding="utf-8").read()
    finalist = open("finalist_selection.py", encoding="utf-8").read()
    ledger = open("recommendation_ledger.py", encoding="utf-8").read()
    module = open("sector_readthrough_engine.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'add_sector_readthrough(discovery_pool)' in app
    assert 'bq_sector_readthrough_radar' in app
    assert 'reason_keys[idx] = "sector_readthrough"' in finalist
    assert '"Sektorläsning status"' in ledger
    assert "Sektorläsning Score" not in module
