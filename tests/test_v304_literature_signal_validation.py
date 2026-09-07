import json
import pandas as pd

from literature_signal_validation import (
    SIGNALS,
    literature_signal_summary,
    prepare_signal_sample,
    validate_literature_signals,
)


def _frames(signal_field, good, bad, model="long", n=12):
    recs=[]; outs=[]
    for i in range(n*2):
        state = good if i < n else bad
        snap = dict(signal_field)
        snap.update(state)
        rid=f"r{i}"
        recs.append({
            "record_id":rid,"symbol":f"S{i}","captured_date":f"2025-01-{(i%28)+1:02d}",
            "horizon_type":model,"snapshot_json":json.dumps(snap),"model_version":"3.x",
        })
        outs.append({"record_id":rid,"horizon":"6m","return_pct":0.20 if i < n else -0.05})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_signal_catalog_contains_six_literature_signals():
    assert len(SIGNALS) == 6
    assert {s.name for s in SIGNALS} >= {"Post-Report Drift", "12–1 Momentum", "Bolagsspecifik volatilitet"}


def test_post_report_validation_can_be_lovande():
    recs, outs = _frames({}, {"Post-report status":"Positiv rapportdrift"}, {"Post-report status":"Negativ rapportdrift"})
    table = validate_literature_signals(recs, outs, "6m")
    row = table[table["Signal"].eq("Post-Report Drift")].iloc[0]
    assert row["Status"] == "Lovande"
    assert row["Skillnad"] > 0.20


def test_reverse_outcome_marks_signal_ifragasatt():
    recs, outs = _frames({}, {"Kapitaldisciplin status":"EFFEKTIV KAPITALANVÄNDNING"}, {"Kapitaldisciplin status":"KAPITALBINDNING ÖKAR"})
    outs["return_pct"] = [-0.10]*12 + [0.15]*12
    table = validate_literature_signals(recs, outs, "6m")
    row = table[table["Signal"].eq("Investment Discipline")].iloc[0]
    assert row["Status"] == "Ifrågasatt"


def test_missing_and_neutral_history_is_not_backfilled():
    spec = next(s for s in SIGNALS if s.name == "Earnings Quality 2.0")
    recs = pd.DataFrame([{"record_id":"a","symbol":"A","captured_date":"2025-01-01","horizon_type":"long","snapshot_json":"{}"}])
    outs = pd.DataFrame([{"record_id":"a","horizon":"6m","return_pct":0.5}])
    sample = prepare_signal_sample(recs, outs, "6m", spec)
    assert sample.empty


def test_benchmark_basis_requires_complete_relative_outcomes():
    recs, outs = _frames({}, {"Evidence Family Support Count":4,"Evidence Family Warning Count":0}, {"Evidence Family Support Count":1,"Evidence Family Warning Count":2})
    outs["excess_return_pct"] = outs["return_pct"]
    outs.loc[0,"excess_return_pct"] = None
    table = validate_literature_signals(recs, outs, "6m")
    row = table[table["Signal"].eq("Evidence Families")].iloc[0]
    assert row["Mätning"] == "Rå kursutveckling"


def test_summary_refuses_conclusion_when_history_is_too_small():
    recs, outs = _frames({}, {"Post-report status":"Positiv rapportdrift"}, {"Post-report status":"Negativ rapportdrift"}, n=3)
    table = validate_literature_signals(recs, outs, "6m")
    summary = literature_signal_summary(table)
    assert summary["status"] == "För lite historik"
    assert "dagens data" in summary["text"]


def test_app_version_and_ui_hook_updated():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Fungerar de nya litteratursignalerna i Borsify?" in app
    assert "validate_literature_signals" in app
