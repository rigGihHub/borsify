import pandas as pd
from recommendation_ledger import calibration_by_deal_conviction

def test_legacy_rows_without_frozen_conviction_are_excluded():
    rec=pd.DataFrame([
        {"record_id":"old","Deal Conviction Score":None},
        {"record_id":"new","Deal Conviction Score":80},
    ])
    out=pd.DataFrame([
        {"record_id":"old","horizon":"3m","return_pct":.50},
        {"record_id":"new","horizon":"3m","return_pct":.10},
    ])
    r=calibration_by_deal_conviction(rec,out,"3m")
    assert r["eligible"]==1
    assert r["excluded_legacy"]==1
    assert int(r["table"]["Antal"].sum())==1

def test_conviction_buckets_are_point_in_time_values():
    rec=pd.DataFrame([
        {"record_id":"a","Deal Conviction Score":20},
        {"record_id":"b","Deal Conviction Score":40},
        {"record_id":"c","Deal Conviction Score":60},
        {"record_id":"d","Deal Conviction Score":80},
    ])
    out=pd.DataFrame([{"record_id":x,"horizon":"1m","return_pct":r} for x,r in zip("abcd",[-.1,0,.1,.2])])
    r=calibration_by_deal_conviction(rec,out,"1m")
    assert list(r["table"]["Conviction"])==["0–24","25–49","50–74","75–100"]

def test_app_exposes_calibration_without_claiming_proof():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert "Kalibrering av Deal Conviction" in app
    assert "ännu inte ett bevis" in app
