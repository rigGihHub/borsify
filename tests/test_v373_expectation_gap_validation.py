import json
from pathlib import Path
import pandas as pd

from expectation_gap_validation import eligible_sample, validate_expectation_gap, validation_summary


def rec(i, cohort, version="3.73.0", date="2026-09-10"):
    snap = {
        "Förändringsbekräftelse kandidat": True,
        "Expectation Gap analytiker antal": 8,
        "Expectation Gap kandidat": cohort == "gap",
        "Expectation Gap varning": False,
        "Expectation Gap status": "Förbättring före förväntningarna" if cohort == "gap" else "Positiv förändring – inget tydligt expectation gap",
    }
    return {"record_id": f"r{i}", "symbol": f"S{i}", "model_version": version, "captured_date": date, "snapshot_json": json.dumps(snap)}


def test_older_versions_are_never_backfilled_into_validation():
    recs = pd.DataFrame([rec(1, "gap", version="3.72.0"), rec(2, "control")])
    outs = pd.DataFrame([{"record_id":"r1","horizon":"1m","return_pct":.3},{"record_id":"r2","horizon":"1m","return_pct":.1}])
    x = eligible_sample(recs, outs, "1m")
    assert set(x["record_id"]) == {"r2"}


def test_warning_case_is_not_silently_used_as_control():
    r = rec(1, "control")
    s = json.loads(r["snapshot_json"]); s["Expectation Gap varning"] = True; r["snapshot_json"] = json.dumps(s)
    outs = pd.DataFrame([{"record_id":"r1","horizon":"1m","return_pct":.1}])
    assert eligible_sample(pd.DataFrame([r]), outs, "1m").empty


def test_supported_status_requires_locked_group_sizes_and_gap():
    recs=[]; outs=[]
    for i in range(15):
        recs.append(rec(i,"gap")); outs.append({"record_id":f"r{i}","horizon":"1m","return_pct":.12})
    for i in range(15,30):
        recs.append(rec(i,"control")); outs.append({"record_id":f"r{i}","horizon":"1m","return_pct":.04})
    x=validate_expectation_gap(pd.DataFrame(recs),pd.DataFrame(outs),"1m")
    assert x["Status"] == "Prospektivt stöd"
    assert round(x["Median skillnad"], 2) == .08


def test_summary_never_auto_promotes_model():
    table=pd.DataFrame([{"Status":"Prospektivt stöd","Oberoende case":30}])
    x=validation_summary(table)
    assert x["status"] == "Stöd"
    assert "alpha" in x["text"]


def test_release_ui_and_snapshot_fields_present():
    app=Path("app.py").read_text()
    ledger=Path("recommendation_ledger.py").read_text()
    assert 'APP_VERSION = "3.73.0"' in app
    assert "Expectation Gap · slår hypotesen vanlig positiv förändring?" in app
    assert '"Expectation Gap kandidat"' in ledger
    assert '"Förändringsbekräftelse kandidat"' in ledger
