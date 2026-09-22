import pandas as pd
from source_health_dashboard import build_source_health_rows, summarize_source_health

def test_empty_dashboard_is_neutral():
    rows=build_source_health_rows({})
    s=summarize_source_health(rows)
    assert s["error"]==0
    assert "Ingen källstatus" in s["status"]

def test_bulk_error_marks_red_and_explains_impact():
    state={"bq_source_health_bulk_prices":{"status":"ERROR","error":"TimeoutError","attempts":2,"circuit_open":False,"requested":10,"returned":0}}
    rows=build_source_health_rows(state)
    s=summarize_source_health(rows)
    assert s["error"]==1
    assert "ranking" in rows.iloc[0]["impact"]

def test_open_circuit_is_counted_even_if_status_unknown():
    state={"bq_source_health_fx":{"status":"CIRCUIT_OPEN","error":"Timeout","circuit_open":True}}
    rows=build_source_health_rows(state)
    s=summarize_source_health(rows)
    assert s["circuit"]==1
    assert "Källproblem" in s["status"]

def test_per_symbol_fundamentals_collapses_to_worst_state():
    state={"bq_source_health_fundamentals":{
        "AAA":{"status":"OK","attempts":1},
        "BBB":{"status":"PARTIAL","attempts":2,"errors":["get_info:Timeout"]},
    }}
    rows=build_source_health_rows(state)
    r=rows.iloc[0]
    assert r["endpoint"]=="fundamentals"
    assert r["status"]=="PARTIAL"
    assert r["scope"]=="2 aktier"

def test_deep_health_from_session_is_shown():
    state={"bq_source_health_deep":{"status":"DEGRADED","error":"quarterly_income:Timeout","circuit_open":False}}
    rows=build_source_health_rows(state)
    assert "deep" in set(rows.endpoint)

def test_app_exposes_source_health_dashboard():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "Datakällornas status" in app
    assert "build_source_health_rows" in app
