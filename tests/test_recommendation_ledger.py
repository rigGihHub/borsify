import json
import numpy as np
import pandas as pd
from recommendation_ledger import (
    stable_record_id, build_recommendation_records, evaluate_record_from_history,
    outcome_summary, calibration_by_gate,
)

def test_stable_id_same_day_same_model_is_idempotent():
    a = stable_record_id("ABC.ST","short","2026-09-01","Balanserad","Sverige","2.35.0")
    b = stable_record_id("abc.st","short","2026-09-01","Balanserad","Sverige","2.35.0")
    assert a == b

def test_records_freeze_all_finalists_not_only_topcase():
    df = pd.DataFrame([
        {"Ticker":"A.ST","Namn":"A","Pris":100,"Short Alpha Score":80,"Short Alpha Gate":"Kortsiktigt toppcase","Short Alpha Confidence":75,"Short Confirmation Count":5},
        {"Ticker":"B.ST","Namn":"B","Pris":90,"Short Alpha Score":60,"Short Alpha Gate":"Bevaka kortsiktigt","Short Alpha Confidence":60,"Short Confirmation Count":2},
    ])
    rows = build_recommendation_records(df,"short","2.35.0","Balanserad","Sverige",pd.Timestamp("2026-09-01T08:00Z"))
    assert len(rows) == 2
    assert rows[1]["gate"] == "Bevaka kortsiktigt"
    assert json.loads(rows[0]["snapshot_json"])["Ticker"] == "A.ST"

def test_future_outcome_uses_trading_session_offset():
    idx = pd.bdate_range("2026-09-01", periods=140)
    close = np.arange(100, 240, dtype=float)
    hist = pd.DataFrame({"Close":close}, index=idx)
    rec = {
        "record_id":"x","symbol":"A.ST","horizon_type":"short",
        "captured_date":"2026-09-01","entry_price":100,
    }
    out = evaluate_record_from_history(rec, hist, as_of=idx[-1])
    one = next(x for x in out if x["horizon"] == "1m")
    assert one["evaluated_date"] == idx[21].date().isoformat()
    assert abs(one["return_pct"] - (121/100 - 1)) < 1e-9

def test_does_not_evaluate_not_yet_due_horizon():
    idx = pd.bdate_range("2026-09-01", periods=30)
    hist = pd.DataFrame({"Close":np.linspace(100,110,30)}, index=idx)
    rec = {"record_id":"x","symbol":"A","horizon_type":"short","captured_date":"2026-09-01","entry_price":100}
    out = evaluate_record_from_history(rec,hist,as_of=idx[-1])
    assert [x["horizon"] for x in out] == ["1m"]

def test_outcome_summary_is_descriptive():
    recs = pd.DataFrame([{"record_id":"a","horizon_type":"short","gate":"Topp","score":80,"confidence":70,"model_version":"2.35"}])
    outs = pd.DataFrame([{"record_id":"a","horizon":"3m","return_pct":.12}])
    s = outcome_summary(recs, outs)
    assert s["evaluated"] == 1
    assert "inte" in s["message"].lower()
    assert s["hit_rate"] == 1

def test_calibration_groups_by_gate():
    recs = pd.DataFrame([
        {"record_id":"a","gate":"Topp","confidence":80,"score":85},
        {"record_id":"b","gate":"Bevaka","confidence":55,"score":60},
    ])
    outs = pd.DataFrame([
        {"record_id":"a","horizon":"3m","return_pct":.20},
        {"record_id":"b","horizon":"3m","return_pct":-.10},
    ])
    c = calibration_by_gate(recs, outs, "3m")
    assert len(c) == 2
    assert c.iloc[0]["Gate"] == "Topp"
