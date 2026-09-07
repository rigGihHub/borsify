import pandas as pd

from independent_case_validation import independent_case_sample, independence_audit
from false_negative_analysis import false_negative_summary


def _rows():
    return pd.DataFrame([
        {"record_id":"a1","symbol":"AAA","captured_date":"2026-01-01","horizon_type":"long","gate":"Bevaka","snapshot_json":"{}"},
        {"record_id":"a2","symbol":"AAA","captured_date":"2026-02-01","horizon_type":"long","gate":"Bevaka","snapshot_json":"{}"},
        {"record_id":"b1","symbol":"BBB","captured_date":"2026-01-10","horizon_type":"long","gate":"Bevaka","snapshot_json":"{}"},
        {"record_id":"a3","symbol":"AAA","captured_date":"2027-02-01","horizon_type":"long","gate":"Bevaka","snapshot_json":"{}"},
    ])


def test_prunes_overlapping_same_ticker_but_allows_new_episode_after_horizon():
    out=independent_case_sample(_rows(), "1y")
    assert list(out["record_id"]) == ["a1", "a3", "b1"]


def test_audit_reports_effective_sample():
    audit=independence_audit(_rows(), "1y")
    assert audit["raw_observations"] == 4
    assert audit["independent_observations"] == 3
    assert audit["removed_overlaps"] == 1
    assert audit["unique_tickers"] == 2


def test_false_negative_denominator_does_not_count_overlap_twice():
    recs=_rows().iloc[:3].copy()
    recs["name"]=["A","A","B"]
    recs["rank"]=[1,2,1]
    recs["model_version"]="2.87.0"
    outs=pd.DataFrame([
        {"record_id":"a1","horizon":"1y","return_pct":0.20},
        {"record_id":"a2","horizon":"1y","return_pct":0.25},
        {"record_id":"b1","horizon":"1y","return_pct":0.01},
    ])
    summary=false_negative_summary(recs,outs,"1y")
    assert summary["evaluated_rejected"] == 2
    assert summary["misses"] == 1
