import pandas as pd
from risk_to_roadmap import build_risk_roadmap, roadmap_focus

def test_critical_risk_becomes_first_roadmap_item():
    r=pd.DataFrame([
      {"Prioritet":1,"Severity":"CRITICAL","Risk":"Retire/downweight-kandidater finns","Recommended action":"x"},
      {"Prioritet":2,"Severity":"HIGH","Risk":"Otillräcklig prospektiv PIT-historik","Recommended action":"y"}])
    road=build_risk_roadmap(r)
    assert road.iloc[0]["Utvecklingsspår"]=="Granska och isolera skadliga signaler"
    assert road.iloc[0]["Kategori"]=="MODEL_VALIDATION"

def test_source_failure_maps_to_reliability():
    r=pd.DataFrame([{"Prioritet":1,"Severity":"CRITICAL","Risk":"Aktiva datakällfel påverkar analyskedjan"}])
    road=build_risk_roadmap(r)
    assert road.iloc[0]["Kategori"]=="DATA_RELIABILITY"

def test_no_risk_does_not_invent_work():
    r=pd.DataFrame([{"Prioritet":1,"Severity":"LOW","Risk":"Inga stora modellrisker identifierade av nuvarande register"}])
    assert build_risk_roadmap(r).empty

def test_manual_gate_is_mandatory():
    r=pd.DataFrame([{"Prioritet":1,"Severity":"HIGH","Risk":"Signaler med negativ observerad edge"}])
    road=build_risk_roadmap(r)
    assert "Manuell" in road.iloc[0]["Gate"]

def test_focus_uses_first_prioritised_item():
    r=pd.DataFrame([{"Prioritet":1,"Severity":"MEDIUM","Risk":"Signalredundans / möjlig dubbelräkning"}])
    f=roadmap_focus(build_risk_roadmap(r))
    assert f["next"]=="Minska signalredundans"

def test_app_exposes_risk_to_roadmap():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert 'st.markdown("#### Risk-to-Roadmap")' in app
    assert "build_risk_roadmap(_risk_register)" in app
