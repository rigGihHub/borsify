import pandas as pd
from verified_relationship_engine import add_verified_relationships, load_verified_relationships, select_verified_relationship_candidates
from relationship_data_builder import relationship_registry_health


def _frame():
    return pd.DataFrame([
        {"Ticker":"TELIA.ST","Namn":"Telia","Report Delta kandidat":True,"Report Delta positiva":4,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":1,"1 mån":0.02},
        {"Ticker":"ERIC-B.ST","Namn":"Ericsson","Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.01},
        {"Ticker":"INVE-B.ST","Namn":"Investor","Report Delta kandidat":True,"Report Delta positiva":4,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":1,"1 mån":0.01},
        {"Ticker":"ABB.ST","Namn":"ABB","Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.01},
    ])


def test_seed_has_named_customer_supplier_relationships_from_primary_sources():
    reg = load_verified_relationships()
    cs = reg[reg["relationship_type"].eq("customer_supplier")]
    pairs = set(zip(cs["source_ticker"], cs["target_ticker"]))
    assert {("TELIA.ST","ERIC-B.ST"),("ELISA.HE","NOKIA.HE"),("BOL.ST","EPI-A.ST"),("VOLV-B.ST","SSAB-A.ST")}.issubset(pairs)
    assert cs["source_url"].str.startswith("https://").all()


def test_operating_customer_supplier_can_create_directional_candidate():
    out = add_verified_relationships(_frame())
    eric = out[out["Ticker"].eq("ERIC-B.ST")].iloc[0]
    assert bool(eric["Verifierad relation kandidat"])
    assert bool(eric["Verifierad relation operativ"])
    assert "customer_supplier" in eric["Verifierad relation typ"]


def test_ownership_is_context_only_not_operating_readthrough():
    out = add_verified_relationships(_frame())
    abb = out[out["Ticker"].eq("ABB.ST")].iloc[0]
    assert not bool(abb["Verifierad relation kandidat"])
    assert not bool(abb["Verifierad relation operativ"])
    assert "kontext" in abb["Verifierad relation status"].casefold()


def test_customer_supplier_priority_wins_single_verified_slot():
    out = add_verified_relationships(_frame())
    picks = select_verified_relationship_candidates(out, quota=1)
    assert picks and out.loc[picks[0][0], "Ticker"] == "ERIC-B.ST"


def test_registry_health_separates_operating_coverage():
    h = relationship_registry_health(load_verified_relationships(), as_of="2026-09-09")
    assert h["customer_supplier_relations"] >= 4
    assert h["operating_relations"] >= 4
    assert h["relations"] >= 24


def test_v362_version_and_ui_wiring():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.73.0"' in app
    assert "kund→leverantör" in app
    assert "Verifierad relation operativ" in app
    engine = open("verified_relationship_engine.py", encoding="utf-8").read()
    assert "OPERATING_READTHROUGH_TYPES" in engine
    assert "Relationship Score" not in engine
