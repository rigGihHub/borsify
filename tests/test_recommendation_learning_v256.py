import json
import pandas as pd

from recommendation_learning import (
    MIN_COHORT,
    prepare_learning_data,
    learning_summary,
    learning_tables,
    score_band_monotonicity,
)

def make_data(n=20):
    recs=[]
    outs=[]
    for i in range(n):
        high=i >= n//2
        rid=f"r{i}"
        snap={
            "Sektor":"Industri" if high else "Bank",
            "Short Trend":80 if high else 40,
        }
        recs.append({
            "record_id":rid,
            "symbol":f"X{i}",
            "name":f"X{i}",
            "horizon_type":"short",
            "gate":"Starkt kortsiktigt case" if high else "Bevaka kortsiktigt",
            "score":82 if high else 64,
            "confidence":80 if high else 60,
            "model_version":"2.55.0",
            "profile":"Balanserad",
            "market":"Sverige",
            "rank":1,
            "captured_date":"2026-01-01",
            "snapshot_json":json.dumps(snap),
        })
        outs.append({
            "record_id":rid,
            "symbol":f"X{i}",
            "horizon":"1m",
            "return_pct":.08 if high else -.03,
        })
    return pd.DataFrame(recs),pd.DataFrame(outs)

def test_learning_uses_frozen_snapshot_sector():
    recs,outs=make_data()
    data=prepare_learning_data(recs,outs)
    assert set(data["Sektor"])=={"Industri","Bank"}

def test_missing_historical_snapshot_field_stays_missing():
    recs,outs=make_data()
    recs.loc[0,"snapshot_json"]="{}"
    data=prepare_learning_data(recs,outs)
    row=data[data["record_id"]=="r0"].iloc[0]
    assert row["Sektor"]=="Okänd"
    assert pd.isna(row["Short Trend"])

def test_learning_requires_minimum_sample_per_group():
    recs,outs=make_data(10)
    tables=learning_tables(recs,outs,"1m")
    assert not tables["Score"]["Tillräckligt underlag"].any()

def test_learning_can_surface_descriptive_pattern_with_enough_samples():
    recs,outs=make_data(20)
    summary=learning_summary(recs,outs,"1m")
    assert summary["status"]=="Möjligt historiskt mönster"
    assert "inte ett bevis" in summary["text"]

def test_higher_score_diagnostic_can_detect_order():
    recs,outs=make_data(20)
    result=score_band_monotonicity(recs,outs,"1m")
    assert "Högre score" in result["status"]

def test_no_automatic_model_change_is_encoded_in_learning_output():
    recs,outs=make_data(20)
    summary=learning_summary(recs,outs,"1m")
    assert "new_weight" not in summary
    assert "new_threshold" not in summary
