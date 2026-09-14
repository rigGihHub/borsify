from data_failure_transparency import assess_failure_transparency

def test_deep_fetch_error_is_not_silently_neutral():
    r=assess_failure_transparency({"Data Trust status":"GOTT UNDERLAG","Deep fetch error":"timeout"})
    assert "BLOCKERAD" in r["Data Failure status"]
    assert "timeout" in r["Data Failure blockerare"]
    assert "KPI-inflection" in r["Data Failure försvagat"]

def test_missing_sector_kpis_are_explicitly_weakened():
    r=assess_failure_transparency({"Data Trust status":"GOTT UNDERLAG","KPI-specifika saknas":"NRR/churn; ARR"})
    assert "NRR/churn" in r["Data Failure försvagat"]
    assert "FÖRSVAGAD" in r["Data Failure status"]

def test_good_data_does_not_invent_warning():
    r=assess_failure_transparency({"Data Trust status":"GOTT UNDERLAG","Rapportdatum":"2026-09-01",
        "KPI-specifika observerade":"orderingång","Fundamental hämtad":"2026-09-13"})
    assert r["Data Failure status"]=="🟢 DATAUNDERLAG OK"
    assert r["Data Failure penalty"]==0

def test_app_wires_transparency_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.36.0"' in app
    assert "Data Trust & Failure Transparency" in app
    assert "assess_failure_transparency" in app
