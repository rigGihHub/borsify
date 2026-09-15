import json
import pandas as pd
from decision_quality_calibration import calibration_table, compare_strong_idea_groups

def rec(i,q):
    return {"record_id":str(i),"snapshot_json":json.dumps({"Decision Support quadrant":q})}

def test_old_rows_without_frozen_decision_support_are_excluded():
    recs=pd.DataFrame([
        {"record_id":"0","snapshot_json":"{}"},
        rec(1,"STARK IDÉ / STARK DATA"),
    ])
    outs=pd.DataFrame([
        {"record_id":"0","horizon":"3m","return_pct":.9},
        {"record_id":"1","horizon":"3m","return_pct":.1},
    ])
    t=calibration_table(recs,outs,"3m",1)
    assert int(t["Antal"].sum())==1

def test_table_uses_worst_observed_return_without_calling_it_drawdown():
    recs=pd.DataFrame([rec(1,"STARK IDÉ / STARK DATA")])
    outs=pd.DataFrame([{"record_id":"1","horizon":"3m","return_pct":.2,"worst_return_pct":-.08}])
    t=calibration_table(recs,outs,"3m",1)
    assert abs(t.iloc[0]["Sämsta observerade median"]+.08)<1e-9

def test_strong_data_beating_weak_data_can_be_lovande():
    recs=[]; outs=[]
    for i in range(8):
        recs.append(rec(f"a{i}","STARK IDÉ / STARK DATA"))
        outs.append({"record_id":f"a{i}","horizon":"1y","return_pct":.20,"worst_return_pct":-.08})
        recs.append(rec(f"b{i}","STARK IDÉ / SVAG DATA"))
        outs.append({"record_id":f"b{i}","horizon":"1y","return_pct":.05,"worst_return_pct":-.15})
    t=calibration_table(pd.DataFrame(recs),pd.DataFrame(outs),"1y",8)
    c=compare_strong_idea_groups(t,8)
    assert c["enough"] is True
    assert c["status"]=="Confidence-lagret ser lovande ut"
    assert c["return_edge"]>.10

def test_small_samples_do_not_claim_edge():
    recs=pd.DataFrame([rec(1,"STARK IDÉ / STARK DATA"),rec(2,"STARK IDÉ / SVAG DATA")])
    outs=pd.DataFrame([
        {"record_id":"1","horizon":"1m","return_pct":.5},
        {"record_id":"2","horizon":"1m","return_pct":-.5},
    ])
    t=calibration_table(recs,outs,"1m")
    c=compare_strong_idea_groups(t)
    assert c["enough"] is False
    assert c["status"]=="Bygger facit"

def test_app_exposes_decision_quality_calibration():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.0"' in app
    assert "Decision Quality Calibration" in app
    assert "decision_quality_table" in app
