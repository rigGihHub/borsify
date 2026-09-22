import json, pandas as pd
from signal_evidence_lab import build_signal_evidence, redundancy_matrix, redundancy_pairs, lab_summary

def rec(i, **fields):
    return {"record_id":str(i),"snapshot_json":json.dumps(fields)}

def test_missing_old_signal_is_excluded_not_reconstructed():
    recs=pd.DataFrame([rec(1),rec(2,**{"KPI Inflection nivå":2}),rec(3,**{"KPI Inflection nivå":0})])
    outs=pd.DataFrame([{"record_id":str(i),"horizon":"3m","return_pct":r} for i,r in [(1,.9),(2,.2),(3,-.1)]])
    t=build_signal_evidence(recs,outs,"3m",1)
    row=t[t.Signal=="KPI Inflection"].iloc[0]
    assert row["Signal N"]==1 and row["Control N"]==1
    assert abs(row["Median edge"]-.3)<1e-9

def test_small_samples_are_not_called_validated():
    recs=pd.DataFrame([rec(1,**{"Margin recovery nivå":2}),rec(2,**{"Margin recovery nivå":0})])
    outs=pd.DataFrame([{"record_id":"1","horizon":"1y","return_pct":.5},{"record_id":"2","horizon":"1y","return_pct":-.5}])
    t=build_signal_evidence(recs,outs,"1y")
    assert t.iloc[0].Status=="Bygger facit"

def test_redundancy_flags_highly_overlapping_frozen_signals():
    recs=[]
    for i in range(10):
        x=2 if i<5 else 0
        recs.append(rec(i,**{"Margin recovery nivå":x,"Operating leverage nivå":x}))
    pairs=redundancy_pairs(redundancy_matrix(pd.DataFrame(recs),min_overlap=8),.7)
    assert len(pairs)==1
    assert "redundans" in pairs.iloc[0].Status

def test_lab_never_claims_automatic_reweighting():
    s=lab_summary(pd.DataFrame([{"Status":"Lovande · kräver fortsatt prospektiv validering"}]))
    assert "inte automatiskt ändra" in s["message"]

def test_app_wires_lab_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "Signal Evidence Lab" in app
    assert "build_signal_evidence" in app
