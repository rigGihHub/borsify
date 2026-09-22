import pandas as pd
from false_start_confirmation import classify_early_signals, summarize_false_starts, calibration_by_outcome

def events(rows):
    return pd.DataFrame(rows,columns=["symbol","signal_type","source_date"])

def test_unmatured_signal_is_pending_not_false_start():
    d=events([["AAA","business_kpi","2026-08-01"]])
    r=classify_early_signals(d,"2026-09-09",120)
    assert r.iloc[0].status=="pending"

def test_mature_signal_without_later_step_is_false_start():
    d=events([["AAA","business_kpi","2026-01-01"]])
    r=classify_early_signals(d,"2026-09-09",120)
    assert r.iloc[0].status=="false_start"

def test_later_estimate_confirms_business_signal():
    d=events([["AAA","business_kpi","2026-01-01"],["AAA","estimate_revision","2026-02-01"]])
    r=classify_early_signals(d,"2026-09-09",120)
    b=r[r.early_type=="business_kpi"].iloc[0]
    assert b.status=="confirmed" and b.days_to_confirmation==31

def test_summary_does_not_claim_causality():
    d=events([["AAA","business_kpi","2026-01-01"],["AAA","estimate_revision","2026-02-01"]])
    s=summarize_false_starts(classify_early_signals(d,"2026-09-09"))
    assert "inte bevis på kausalitet" in s["False Start förklaring"]

def test_outcome_calibration_uses_only_frozen_state():
    rec=pd.DataFrame([{"record_id":"1","False Start frozen state":"confirmed"},{"record_id":"2","False Start frozen state":"false_start"}])
    out=pd.DataFrame([{"record_id":"1","horizon":"3m","return_pct":.2},{"record_id":"2","horizon":"3m","return_pct":-.1}])
    c=calibration_by_outcome(rec,out,"3m")
    assert set(c.State)=={"confirmed","false_start"}

def test_app_wires_engine_without_deal_conviction_weight():
    app=open("app.py",encoding="utf-8").read(); deal=open("deal_conviction.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "classify_early_signals" in app
    assert "False Start frozen state" not in deal
