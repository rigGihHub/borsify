import json
import pandas as pd

from false_negative_analysis import false_negative_analysis, false_negative_summary, frozen_decision
from recommendation_ledger import build_recommendation_records, snapshot_columns


def _rec(record_id, gate, decision=None, horizon_type="long", rank=1, snapshot=None):
    snap = dict(snapshot or {})
    if decision:
        snap["Ledger Decision"] = decision
    return {
        "record_id": record_id,
        "symbol": record_id.upper(),
        "name": record_id.upper(),
        "captured_date": "2026-01-01",
        "horizon_type": horizon_type,
        "rank": rank,
        "gate": gate,
        "model_version": "2.85.0",
        "snapshot_json": json.dumps(snap),
    }


def test_new_ledger_records_freeze_recommended_vs_not_recommended():
    frame = pd.DataFrame([
        {"Ticker":"A.ST","Namn":"A","Pris":100,"Case Gate":"Toppcase","INVEST Score":80},
        {"Ticker":"B.ST","Namn":"B","Pris":90,"Case Gate":"Bevaka","INVEST Score":70},
    ])
    rows = build_recommendation_records(frame, "long", "2.85.0", "Balanserad", "Sverige", pd.Timestamp("2026-09-04T10:00Z"))
    a = json.loads(rows[0]["snapshot_json"])
    b = json.loads(rows[1]["snapshot_json"])
    assert a["Ledger Decision"] == "RECOMMENDED"
    assert b["Ledger Decision"] == "NOT_RECOMMENDED"
    assert b["Ledger Rank"] == 2


def test_false_negative_prefers_relative_outcome_for_complete_cohort():
    recs = pd.DataFrame([
        _rec("a", "Toppcase", "RECOMMENDED"),
        _rec("b", "Bevaka", "NOT_RECOMMENDED", snapshot={"Case Evidence Count":2}),
    ])
    outs = pd.DataFrame([
        {"record_id":"a","horizon":"1y","return_pct":0.20,"excess_return_pct":0.02},
        {"record_id":"b","horizon":"1y","return_pct":0.30,"excess_return_pct":0.14},
    ])
    result = false_negative_analysis(recs, outs, "1y")
    assert list(result["Ticker"]) == ["B"]
    assert result.iloc[0]["Mätning"] == "Mot index"
    assert "oberoende stöd" in result.iloc[0]["Varför den valdes bort"]


def test_false_negative_falls_back_to_raw_for_whole_cohort_not_mixed_metrics():
    recs = pd.DataFrame([
        _rec("a", "Toppcase", "RECOMMENDED"),
        _rec("b", "Bevaka", "NOT_RECOMMENDED"),
    ])
    outs = pd.DataFrame([
        {"record_id":"a","horizon":"1y","return_pct":0.05,"excess_return_pct":None},
        {"record_id":"b","horizon":"1y","return_pct":0.18,"excess_return_pct":0.20},
    ])
    result = false_negative_analysis(recs, outs, "1y")
    assert len(result) == 1
    assert result.iloc[0]["Mätning"] == "Rå kursutveckling"
    assert abs(result.iloc[0]["Utfall"] - 0.18) < 1e-12


def test_old_records_use_frozen_gate_fallback_not_live_data():
    row = _rec("x", "Bevaka", decision=None)
    assert frozen_decision(row) == "NOT_RECOMMENDED"
    row2 = _rec("y", "Starkt kortsiktigt case", decision=None, horizon_type="short")
    assert frozen_decision(row2) == "RECOMMENDED"


def test_summary_is_descriptive_and_does_not_recommend_reweighting():
    recs = pd.DataFrame([_rec(f"r{i}", "Bevaka", "NOT_RECOMMENDED") for i in range(10)])
    outs = pd.DataFrame([
        {"record_id":f"r{i}","horizon":"1y","return_pct":0.20 if i < 2 else 0.02}
        for i in range(10)
    ])
    summary = false_negative_summary(recs, outs, "1y")
    assert summary["evaluated_rejected"] == 10
    assert summary["misses"] == 2
    assert "vikt" in summary["text"].lower()


def test_new_snapshots_keep_rejection_evidence_for_future_miss_analysis():
    long_cols = snapshot_columns("long")
    short_cols = snapshot_columns("short")
    assert "Case Vetoes" in long_cols
    assert "Fundamental Data stopp" in long_cols
    assert "Short Vetoes" in short_cols
