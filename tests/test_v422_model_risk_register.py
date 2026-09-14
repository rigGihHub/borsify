import pandas as pd
from model_risk_register import build_model_risk_register, summarize_model_risks

def test_critical_retire_risk_ranks_first():
    mh={"Model Health signaler":10,"Model Health mogna":8,"Model Health varningar":1,"Model Health retire":2,"Model Health merge":0,"Model Health decision mature":2}
    r=build_model_risk_register(mh,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{})
    assert r.iloc[0]["Severity"]=="CRITICAL"
    assert "Retire/downweight" in r.iloc[0]["Risk"]

def test_low_pit_maturity_is_high_risk():
    mh={"Model Health signaler":12,"Model Health mogna":2,"Model Health varningar":0,"Model Health retire":0,"Model Health merge":0,"Model Health decision mature":0}
    r=build_model_risk_register(mh,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{})
    assert r[r["Risk"]=="Otillräcklig prospektiv PIT-historik"].iloc[0]["Severity"]=="HIGH"

def test_source_failure_is_critical():
    mh={"Model Health signaler":4,"Model Health mogna":4,"Model Health varningar":0,"Model Health retire":0,"Model Health merge":0,"Model Health decision mature":2}
    r=build_model_risk_register(mh,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{"error":1,"circuit":1,"warning":0})
    assert r[r["Risk"].str.contains("datakällfel")].iloc[0]["Severity"]=="CRITICAL"

def test_register_never_auto_changes_model():
    r=build_model_risk_register({},pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),{})
    assert set(r["Auto action"])=={"Ingen"}

def test_summary_prioritises_critical():
    s=summarize_model_risks(pd.DataFrame([{"Severity":"MEDIUM"},{"Severity":"CRITICAL"},{"Severity":"HIGH"}]))
    assert s["critical"]==1 and "Kritiska" in s["status"]

def test_v421_false_positive_regression_is_fixed():
    app=open("app.py",encoding="utf-8").read()
    assert "_mh = assess_model_health(" in app
    assert 'st.markdown("#### Model Health · evidensmognad")' in app
    assert 'st.markdown("#### Model Risk Register")' in app
    assert 'APP_VERSION = "4.35.0"' in app
