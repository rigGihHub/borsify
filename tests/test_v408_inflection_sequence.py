import sqlite3, pandas as pd
from inflection_sequence import event, save_events, history, summarize_sequence, events_from_snapshot

def test_event_requires_real_source_date():
    assert event("AAA","business_kpi","","2026-01-01",2,"","") is None

def test_repeated_scan_does_not_invent_history():
    c=sqlite3.connect(":memory:")
    e=event("AAA","business_kpi","2026-01-01","2026-01-02",2,"x","x")
    save_events(c,[e]); save_events(c,[e])
    assert len(history(c,"AAA"))==1

def test_sequence_measures_lead_time_without_claiming_causality():
    c=sqlite3.connect(":memory:")
    save_events(c,[
        event("AAA","business_kpi","2026-01-01","2026-01-02",2,"",""),
        event("AAA","estimate_revision","2026-01-15","2026-01-15",.03,"",""),
        event("AAA","market_reaction","2026-02-01","2026-02-01",.05,"",""),
    ])
    r=summarize_sequence(history(c,"AAA"))
    assert r["Inflection Sequence lead days"]==31
    assert "inte kausalitet" in r["Inflection Sequence förklaring"]

def test_estimate_date_is_capture_date_not_fake_historical_timestamp():
    es=events_from_snapshot("AAA",{"EPS-estimat förändring":.04},"2026-03-10")
    e=[x for x in es if x["signal_type"]=="estimate_revision"][0]
    assert e["source_date"]=="2026-03-10"

def test_app_wires_tracker_but_not_deal_conviction():
    app=open("app.py",encoding="utf-8").read(); deal=open("deal_conviction.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert "save_events(" in app
    assert "Inflection Sequence lead days" not in deal
