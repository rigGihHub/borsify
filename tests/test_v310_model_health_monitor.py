import json
import pandas as pd

from model_health_monitor import (
    data_health, model_health_summary, model_health_table,
    performance_drift, signal_distribution_drift,
)

FIELDS = {
    "Short Relative Strength": 60,
    "Short Trend": 60,
    "Short Momentum": 60,
    "Short Participation": 60,
    "Short Revisions": 60,
    "Short Catalyst": 60,
}


def _recs(n=60, shifted=False):
    rows=[]
    base=pd.Timestamp("2024-01-01")
    for i in range(n):
        snap={"PIT Complete": True, "Marknadsläge": "Normal", **FIELDS}
        if shifted and i >= n//2:
            snap["Short Momentum"] = 85
            snap["Short Trend"] = 85
        rows.append({
            "record_id": f"r{i}", "symbol": f"S{i}", "captured_date": (base+pd.Timedelta(days=i*8)).date().isoformat(),
            "horizon_type": "short", "score": 50+i%40, "snapshot_json": json.dumps(snap), "market": "Sverige", "model_version":"3.10.0",
        })
    return pd.DataFrame(rows)


def _outs(n=60, bad_recent=False):
    rows=[]
    for i in range(n):
        ret = (i % 10) / 100
        if bad_recent and i >= n-12:
            ret = -0.12
        rows.append({"record_id":f"r{i}", "symbol":f"S{i}", "horizon":"1m", "return_pct":ret})
    return pd.DataFrame(rows)


def test_data_health_requires_high_pit_and_signal_completeness():
    result=data_health(_recs(30))
    assert result["Status"] == "OK"
    assert result["pit_rate"] == 1.0


def test_signal_distribution_drift_detects_multiple_large_median_shifts():
    result=signal_distribution_drift(_recs(50, shifted=True))
    assert result["Status"] == "Bevaka"
    assert result["shift_count"] >= 2


def test_performance_drift_warns_when_recent_outcomes_collapse():
    result=performance_drift(_recs(40), _outs(40, bad_recent=True), "1m")
    assert result["Status"] == "Varning"


def test_summary_never_automatically_rolls_back():
    table=pd.DataFrame([
        {"Kontroll":"Utfall 1m","Status":"Varning","N":30,"Detalj":"x"},
        {"Kontroll":"Point-in-time-data","Status":"Varning","N":30,"Detalj":"x"},
    ])
    result=model_health_summary(table)
    assert result["status"] == "Granska rollback"
    assert result["automatic_rollback"] is False


def test_model_health_table_has_expected_controls():
    table=model_health_table(_recs(60), _outs(60))
    names=set(table["Kontroll"])
    assert "Point-in-time-data" in names
    assert "Signalbeteende" in names
    assert "Utfall 1m" in names
    assert "Rangordning 1m" in names
    assert "Marknadslägen" in names


def test_v310_ui_and_version():
    app=open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Model Health Monitor · mår champion fortfarande bra?" in app
    assert "Ingen rollback sker automatiskt" in app
