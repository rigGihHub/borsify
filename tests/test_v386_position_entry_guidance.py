import pandas as pd
from position_entry_guidance import assess_position_entry, add_position_entry_guidance

def test_full_position_requires_green_company_and_green_entry():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"green"})
    assert r["Positionsråd"] == "🟢 Köp hela positionen nu"

def test_orange_entry_never_gets_full_position():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"orange","Bättre ingång":"90–95"})
    assert r["Positionsråd"] == "🟡 Börja köpa försiktigt"
    assert "90–95" in r["Positionsråd skäl"]

def test_red_entry_means_wait_even_for_good_company():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"red"})
    assert r["Positionsråd"] == "🔴 Vänta helt"

def test_weak_company_cannot_be_rescued_by_good_price():
    r=assess_position_entry({"Bolagsbedömning nivå":"red","Ingångsläge nivå":"green"})
    assert r["Positionsråd"] == "🔴 Vänta helt"

def test_dataframe_adds_guidance_columns():
    df=pd.DataFrame([{"Bolagsbedömning nivå":"green","Ingångsläge nivå":"green"}])
    out=add_position_entry_guidance(df)
    assert "Positionsråd" in out.columns
    assert "Positionsråd skäl" in out.columns

def test_app_wires_position_guidance_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "add_position_entry_guidance(ranked)" in app
    assert '"Positionsråd"' in app
    assert "**Position:**" in app
