import json
import pandas as pd
from news_underreaction_validation import eligible_sample, validate_news_underreaction, REGISTERED_VERSION


def rec(i, cohort=True, date="2026-09-09", version="3.39.0", symbol=None):
    snap = {
        "News Surprise Primary Direction":"positive",
        "News Surprise Strength":3,
        "News Surprise Source Quality":"Stark källa",
        "News Surprise Underreaction":cohort,
        "News Surprise Adverse Reaction":False,
        "News Surprise Directional Immediate":0.01 if cohort else 0.04,
    }
    return {"record_id":f"r{i}","symbol":symbol or f"S{i}","captured_date":date,"model_version":version,"snapshot_json":json.dumps(snap)}


def out(i, value, horizon="1m"):
    return {"record_id":f"r{i}","horizon":horizon,"return_pct":value}


def test_pre_registration_rows_are_excluded():
    recs=pd.DataFrame([rec(1, date="2026-09-07", version="3.38.0"), rec(2)])
    outs=pd.DataFrame([out(1,.2),out(2,.1)])
    sample=eligible_sample(recs,outs,"1m")
    assert list(sample["record_id"]) == ["r2"]


def test_small_sample_never_claims_support():
    recs=pd.DataFrame([rec(1,True),rec(2,False)])
    outs=pd.DataFrame([out(1,.2),out(2,0)])
    result=validate_news_underreaction(recs,outs,"1m")
    assert result["Status"] == "För lite prospektiv historik"
    assert result["Median skillnad"] == .2


def test_enough_cases_can_show_support_without_changing_model():
    recs=[]; outs=[]
    for i in range(1,16):
        recs.append(rec(i,True)); outs.append(out(i,.08))
    for i in range(16,31):
        recs.append(rec(i,False)); outs.append(out(i,.01))
    result=validate_news_underreaction(pd.DataFrame(recs),pd.DataFrame(outs),"1m")
    assert result["Status"] == "Prospektivt stöd"
    assert result["Underreaktion case"] == 15
    assert result["Kontroll case"] == 15
    assert result["Registrerad version"] == REGISTERED_VERSION


def test_weak_source_and_ambiguous_surprise_are_not_controls():
    r=rec(1,False); s=json.loads(r["snapshot_json"]); s["News Surprise Source Quality"]="Okänd källkvalitet"; r["snapshot_json"]=json.dumps(s)
    sample=eligible_sample(pd.DataFrame([r]),pd.DataFrame([out(1,.1)]),"1m")
    assert sample.empty
