import pandas as pd
from verified_relationship_engine import add_verified_relationships, select_verified_relationship_candidates
from finalist_selection import select_deep_finalist_pool


def registry(active="true", url="https://example.com/report"):
    return pd.DataFrame([{
        "source_ticker":"SRC.ST","target_ticker":"TGT.ST","relationship_type":"supplier_customer",
        "direction":"positive","evidence_label":"Annual report identifies target relationship",
        "source_url":url,"source_date":"2026-02-01","verified_at":"2026-09-09","active":active,
    }])


def frame(target_fund=2, target_m1=0.02):
    return pd.DataFrame([
        {"Ticker":"SRC.ST","Namn":"Source","INVEST Score":80,"Report Delta kandidat":True,"Report Delta positiva":5,"Report Delta negativa":0,"Ledningssignal kandidat":True,"Ledningssignal varning":False,"Fundamental upptäckt antal":2,"1 mån":0.03},
        {"Ticker":"TGT.ST","Namn":"Target","INVEST Score":60,"Report Delta kandidat":False,"Report Delta positiva":0,"Report Delta negativa":0,"Ledningssignal kandidat":False,"Ledningssignal varning":False,"Fundamental upptäckt antal":target_fund,"1 mån":target_m1},
    ])


def test_explicit_valid_source_can_create_candidate():
    out=add_verified_relationships(frame(), registry())
    tgt=out[out.Ticker=="TGT.ST"].iloc[0]
    assert bool(tgt["Verifierad relation kandidat"])
    assert tgt["Verifierad relation källbolag"] == "Source"
    assert "supplier_customer" in tgt["Verifierad relation typ"]


def test_missing_or_invalid_evidence_never_becomes_verified():
    out=add_verified_relationships(frame(), registry(url="not-a-source"))
    assert not out["Verifierad relation kandidat"].any()


def test_target_needs_own_support_and_no_runup():
    assert not add_verified_relationships(frame(target_fund=0), registry())["Verifierad relation kandidat"].any()
    assert not add_verified_relationships(frame(target_m1=0.20), registry())["Verifierad relation kandidat"].any()


def test_selector_is_deterministic_and_score_free():
    out=add_verified_relationships(frame(), registry())
    picks=select_verified_relationship_candidates(out, quota=1)
    assert picks and out.loc[picks[0][0],"Ticker"] == "TGT.ST"
    assert not any("Score" in c and "Verifierad" in c for c in out.columns)


def test_verified_relationship_has_priority_inside_single_cross_company_slot():
    df=add_verified_relationships(frame(), registry())
    # Add a second incumbent so the verified target must use the shared cross-company slot.
    alt = df.iloc[[0]].copy()
    alt["Ticker"]="ALT.ST"; alt["Namn"]="Alt"; alt["INVEST Score"]=70
    alt["Verifierad relation kandidat"]=False; alt["Verifierad relation stark"]=False
    df=pd.concat([df,alt],ignore_index=True)
    # Add incumbent ranking fields used by finalist selector.
    for c in ["Daytrade Score","Mellan Score","Lång Score","Livstid Score","Kvalitet","REVERSAL Score","Värdering"]:
        df[c]=50
    df["Datatäckning"]=80
    # Preserve the already-computed verified relation but disable unrelated fresh-change selectors.
    df["Report Delta kandidat"]=False
    df["Ledningssignal kandidat"]=False
    pool=select_deep_finalist_pool(df, pool_size=3)
    # The cross-company doorway only starts after the two incumbent INVEST slots.
    assert "verified_relationship" in set(pool["Djupurval Nyckel"])


def test_version_and_ui_wiring():
    app=open("app.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.73.0"' in app
    assert "Verifierade bolagsrelationer – riktig ekonomisk koppling" in app
    assert "Verifierad relation källa" in ledger
