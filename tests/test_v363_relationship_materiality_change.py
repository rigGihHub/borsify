import pandas as pd
from relationship_change_radar import add_relationship_change_radar, select_relationship_change_candidates
from verified_relationship_engine import load_verified_relationships
from finalist_selection import select_deep_finalist_pool


def _frame():
    return pd.DataFrame([
        {"Ticker":"TELIA.ST","Namn":"Telia","INVEST Score":90,"Report Delta kandidat":True,"Report Delta positiva":4,"Report Delta negativa":0,"Report Delta evidens":4,"Report Delta underreaktion":False,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":1,"1 mån":0.02,"Datatäckning":80},
        {"Ticker":"ERIC-B.ST","Namn":"Ericsson","INVEST Score":40,"Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Report Delta evidens":0,"Report Delta underreaktion":False,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.01,"Datatäckning":80},
        {"Ticker":"OTHER.ST","Namn":"Other","INVEST Score":80,"Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Report Delta evidens":0,"Report Delta underreaktion":False,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":1,"1 mån":0.01,"Datatäckning":80},
    ])


def _rel(change_type="contract_extension", materiality="multiyear", evidence="Four-year agreement", change_date="2026-08-01"):
    return pd.DataFrame([{
        "source_ticker":"TELIA.ST","target_ticker":"ERIC-B.ST","relationship_type":"customer_supplier","direction":"positive",
        "evidence_label":"Named customer supplier agreement","source_url":"https://example.com/source","source_date":"2026-08-01","verified_at":"2026-09-09","active":"true",
        "change_type":change_type,"change_date":change_date,"materiality_level":materiality,"materiality_evidence":evidence,
    }])


def test_static_relation_without_explicit_change_metadata_is_not_change_signal():
    rel=_rel(); rel["change_type"]=""; rel["change_date"]=""; rel["materiality_evidence"]=""
    out=add_relationship_change_radar(_frame(), rel)
    row=out[out.Ticker.eq("ERIC-B.ST")].iloc[0]
    assert not bool(row["Relationsförändring kandidat"])


def test_multiyear_explicit_change_can_create_candidate_but_does_not_invent_financial_materiality():
    out=add_relationship_change_radar(_frame(), _rel(materiality="multiyear"), as_of="2026-09-09")
    row=out[out.Ticker.eq("ERIC-B.ST")].iloc[0]
    assert bool(row["Relationsförändring kandidat"])
    assert not bool(row["Relationsförändring stark"])
    assert row["Relationsförändring materialitet"] == "multiyear"
    assert "antar inte" in row["Relationsförändring förklaring"]


def test_fresh_quantified_scope_with_strong_source_is_strong():
    f=_frame(); f.loc[f.Ticker.eq("TELIA.ST"),"Ledningssignal kandidat"]=True
    out=add_relationship_change_radar(f, _rel(materiality="quantified_scope", evidence="12,000 units explicitly disclosed"), as_of="2026-09-09")
    row=out[out.Ticker.eq("ERIC-B.ST")].iloc[0]
    assert bool(row["Relationsförändring stark"])


def test_low_materiality_or_old_change_is_not_promoted():
    out=add_relationship_change_radar(_frame(), _rel(materiality="qualitative"), as_of="2026-09-09")
    assert not bool(out[out.Ticker.eq("ERIC-B.ST")].iloc[0]["Relationsförändring kandidat"])
    old=add_relationship_change_radar(_frame(), _rel(change_date="2024-01-01"), as_of="2026-09-09")
    assert not bool(old[old.Ticker.eq("ERIC-B.ST")].iloc[0]["Relationsförändring kandidat"])


def test_own_negative_or_large_runup_vetoes_change_candidate():
    f=_frame(); f.loc[f.Ticker.eq("ERIC-B.ST"),"Ledningssignal varning"]=True
    out=add_relationship_change_radar(f,_rel(),as_of="2026-09-09")
    assert not bool(out[out.Ticker.eq("ERIC-B.ST")].iloc[0]["Relationsförändring kandidat"])
    f=_frame(); f.loc[f.Ticker.eq("ERIC-B.ST"),"1 mån"]=0.20
    out=add_relationship_change_radar(f,_rel(),as_of="2026-09-09")
    assert not bool(out[out.Ticker.eq("ERIC-B.ST")].iloc[0]["Relationsförändring kandidat"])


def test_selector_and_finalist_use_same_single_cross_company_slot_with_change_priority():
    out=add_relationship_change_radar(_frame(), _rel(), as_of="2026-09-09")
    out["Verifierad relation kandidat"]=[False,True,False]
    out["Verifierad relation stark"]=[False,True,False]
    out["Verifierad relation prioritet"]=[0,4,0]
    out["Verifierad relation källor antal"]=[0,1,0]
    picks=select_relationship_change_candidates(out,quota=1)
    assert picks and out.loc[picks[0][0],"Ticker"]=="ERIC-B.ST"
    selected=select_deep_finalist_pool(out,pool_size=3)
    eric=selected[selected.Ticker.eq("ERIC-B.ST")]
    assert not eric.empty
    assert eric.iloc[0]["Djupurval Nyckel"] == "relationship_change"


def test_seed_change_metadata_and_v363_ui_wiring():
    reg=load_verified_relationships()
    telia=reg[(reg.source_ticker.eq("TELIA.ST")) & (reg.target_ticker.eq("ERIC-B.ST"))].iloc[0]
    assert telia["change_type"] == "contract_extension"
    assert telia["materiality_level"] == "multiyear"
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Relationen förändras – har kopplingen blivit viktigare?" in app
    engine=open("relationship_change_radar.py",encoding="utf-8").read()
    assert "Relationship Score" not in engine
