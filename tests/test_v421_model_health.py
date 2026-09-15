import pandas as pd
from model_health import assess_model_health

def test_empty_model_is_immature_not_healthy():
    r=assess_model_health(pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame())
    assert r["Model Health Score"]<40
    assert r["Model Health nivå"]==1

def test_mature_positive_model_scores_high():
    evidence=pd.DataFrame([{"Signal":f"S{i}","Status":"Lovande · kräver fortsatt prospektiv validering"} for i in range(10)])
    gov=pd.DataFrame([{"Signal":"S1","Action":"PROMOTE CANDIDATE"}])
    dq=pd.DataFrame([
        {"Status":"Moget nog för jämförelse"},{"Status":"Moget nog för jämförelse"}
    ])
    r=assess_model_health(evidence,gov,pd.DataFrame(),dq)
    assert r["Model Health Score"]>=80
    assert r["Model Health nivå"]==4

def test_negative_and_redundant_signals_reduce_health():
    evidence=pd.DataFrame([
        {"Signal":"A","Status":"Varningssignal · underpresterar kontroll"},
        {"Signal":"B","Status":"Varningssignal · underpresterar kontroll"},
        {"Signal":"C","Status":"Ingen tydlig edge"},
        {"Signal":"D","Status":"Bygger facit"},
    ])
    gov=pd.DataFrame([
        {"Signal":"A","Action":"RETIRE/DOWNWEIGHT CANDIDATE"},
        {"Signal":"B","Action":"MERGE REVIEW"},
    ])
    red=pd.DataFrame([{"Signal A":"B","Signal B":"C","Korrelation":.9}])
    r=assess_model_health(evidence,gov,red,pd.DataFrame())
    assert r["Model Health Score"]<60
    assert "redundans" in r["Model Health risker"]

def test_model_health_is_advisory_only():
    src=open("model_health.py",encoding="utf-8").read()
    assert "ändrar aldrig produktionen automatiskt" in src

def test_app_exposes_model_health():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.2"' in app
    assert "#### Model Health" in app
    assert "assess_model_health" in app
