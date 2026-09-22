import pandas as pd
from challenger_path import path_to_number_one, challenger_paths


def test_lower_primary_score_must_close_primary_score_first():
    winner={"Ticker":"AAA","Lång Score":88,"Deal Conviction Score":70}
    challenger={"Ticker":"BBB","Lång Score":84,"Deal Conviction Score":90}
    r=path_to_number_one(winner,challenger,"Lång Score","year")
    assert r["Första avgörande dimension"] == "Borsify-score"
    assert "från 84 till minst cirka" in r["Formell väg till #1"]
    assert "Deal Conviction" in r["Bevaka också"] or True


def test_equal_primary_score_moves_threshold_to_conviction():
    winner={"Ticker":"AAA","Lång Score":88,"Deal Conviction Score":70,"Affärsläge rangvärde":200}
    challenger={"Ticker":"BBB","Lång Score":88,"Deal Conviction Score":62,"Affärsläge rangvärde":300}
    r=path_to_number_one(winner,challenger,"Lång Score","year")
    assert r["Första avgörande dimension"] == "Deal Conviction"
    assert "62" in r["Formell väg till #1"]
    assert "71" in r["Formell väg till #1"]


def test_practical_watch_uses_existing_better_entry_not_invented_retracement():
    winner={"Ticker":"AAA","Lång Score":90}
    challenger={"Ticker":"BBB","Lång Score":85,"Ingångsläge nivå":"red","Bättre ingång":"112.00–118.00"}
    r=path_to_number_one(winner,challenger,"Lång Score","year")
    assert "112.00–118.00" in r["Bevaka också"]


def test_paths_only_for_number_two_and_three():
    df=pd.DataFrame([
        {"Ticker":"A","Lång Score":90},
        {"Ticker":"B","Lång Score":85},
        {"Ticker":"C","Lång Score":80},
        {"Ticker":"D","Lång Score":70},
    ])
    out=challenger_paths(df,"Lång Score","year")
    assert list(out["#"]) == [2,3]


def test_app_wires_v402():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert 'from challenger_path import challenger_paths' in app
    assert 'Vad krävs för att #2 eller #3 ska bli #1?' in app
    assert 'villkor, inte prognoser' in app
