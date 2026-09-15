import pandas as pd
from top_pick_explainer import explain_top_pick


def test_explainer_names_real_edges_and_challenger_strengths():
    df=pd.DataFrame([
        {"Ticker":"AAA","Namn":"A","Lång Score":88,"Deal Conviction Score":76,"Deal Conviction oberoende familjer":4,"Affärsläge nivå":3,"Ingångsläge nivå":"yellow","Bolagsbedömning nivå":"green","Case Readiness":80,"Riktkurs potential":.18},
        {"Ticker":"BBB","Namn":"B","Lång Score":84,"Deal Conviction Score":55,"Deal Conviction oberoende familjer":2,"Affärsläge nivå":2,"Ingångsläge nivå":"green","Bolagsbedömning nivå":"green","Case Readiness":75,"Riktkurs potential":.25},
        {"Ticker":"CCC","Namn":"C","Lång Score":82,"Deal Conviction Score":50,"Deal Conviction oberoende familjer":2,"Affärsläge nivå":2,"Ingångsläge nivå":"orange","Bolagsbedömning nivå":"yellow","Case Readiness":70,"Riktkurs potential":.12},
    ])
    r=explain_top_pick(df,"Lång Score","year")
    assert "högre Borsify-score" in r["Varför #1"]
    assert "starkare Deal Conviction" in r["Varför #1"]
    assert "bättre köpläge just nu" in r["Utmanarnas fördelar"]
    assert len(r["Jämförelseunderlag"]) == 3


def test_explainer_does_not_invent_edge_when_equal():
    df=pd.DataFrame([
        {"Ticker":"AAA","Lång Score":80,"Deal Conviction Score":50},
        {"Ticker":"BBB","Lång Score":80,"Deal Conviction Score":50},
    ])
    r=explain_top_pick(df,"Lång Score","year")
    assert "ingen tydlig separat fördel" in r["Varför #1"]


def test_single_candidate_is_handled():
    df=pd.DataFrame([{"Ticker":"AAA","Lång Score":80}])
    r=explain_top_pick(df,"Lång Score","year")
    assert "ensam godkänd kandidat" in r["Varför #1"]


def test_app_wires_top_pick_explainer_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.2"' in app
    assert 'from top_pick_explainer import explain_top_pick' in app
    assert '#### Varför är den här #1?' in app
    assert 'Vad #2–#3 gör bättre' in app
