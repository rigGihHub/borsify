import pandas as pd
from mispriced_acceleration import assess_mispriced_acceleration, add_mispriced_acceleration

def test_strong_unpriced_acceleration_candidate():
    row={
        "Omsättning acceleration":.08,
        "Marginal YoY förändring":.04,
        "Marginal YoY föregående kvartal":.01,
        "Vinst YoY senaste kvartal":.35,
        "Vinst YoY föregående kvartal":.10,
        "EPS-estimat förändring":.04,
        "1 mån":.06,
        "3 mån":.10,
        "Avstånd SMA200":.08,
        "Värdering":72,
        "Riktkurs potential":.22,
        "Ingångsläge nivå":"green",
    }
    r=assess_mispriced_acceleration(row)
    assert r["Mispriced acceleration nivå"] == 3
    assert "Mispriced acceleration" in r["Mispriced acceleration"]

def test_acceleration_but_price_already_ran():
    row={
        "Omsättning acceleration":.08,
        "Vinst YoY senaste kvartal":.35,
        "Vinst YoY föregående kvartal":.10,
        "EPS-estimat förändring":.04,
        "1 mån":.30,
        "3 mån":.48,
        "Avstånd SMA200":.24,
        "Värdering":70,
        "Riktkurs potential":.20,
        "Ingångsläge nivå":"red",
    }
    r=assess_mispriced_acceleration(row)
    assert r["Mispriced acceleration nivå"] == 1
    assert "kursen har hunnit före" in r["Mispriced acceleration"]

def test_high_growth_without_acceleration_is_not_enough():
    row={
        "Omsättning acceleration":.00,
        "Vinst YoY senaste kvartal":.30,
        "Vinst YoY föregående kvartal":.28,
        "Marginal YoY förändring":.02,
        "Marginal YoY föregående kvartal":.02,
    }
    r=assess_mispriced_acceleration(row)
    assert r["Mispriced acceleration nivå"] == 0

def test_deterioration_blocks_signal():
    row={
        "Omsättning acceleration":-.08,
        "Vinst YoY senaste kvartal":-.25,
        "Vinst YoY föregående kvartal":.10,
        "FCF YoY senaste kvartal":-.35,
        "FCF YoY föregående kvartal":.05,
    }
    r=assess_mispriced_acceleration(row)
    assert r["Mispriced acceleration nivå"] == -1

def test_dataframe_adds_fields():
    out=add_mispriced_acceleration(pd.DataFrame([{"Omsättning acceleration":.04,"EPS-estimat förändring":.03}]))
    assert "Mispriced acceleration" in out.columns
    assert "Mispriced acceleration rangvärde" in out.columns

def test_app_and_ranking_wire_release():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.1"' in app
    assert "Mispriced acceleration" in app
    assert "add_mispriced_acceleration(ranked)" in app
    assert "add_mispriced_acceleration(out)" in rank
    assert '"Deal Conviction Score"' in rank
    assert '"Mispriced acceleration förklaring"' in ledger
