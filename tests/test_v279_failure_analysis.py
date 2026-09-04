import json
import pandas as pd

from recommendation_failure_analysis import failed_recommendation_analysis, failure_pattern_summary
from recommendation_ledger import snapshot_columns


def _recs(snapshot, horizon_type="long"):
    return pd.DataFrame([{
        "record_id":"r1", "symbol":"ABC.ST", "name":"ABC", "captured_date":"2026-01-01",
        "horizon_type":horizon_type, "model_version":"2.79.0", "snapshot_json":json.dumps(snapshot),
    }])


def test_relative_failure_is_preferred_and_frozen_warning_is_explained():
    recs=_recs({"Value Trap Risk":65, "Case Evidence Count":3, "Catalyst Signal":"Ingen tydlig katalysator verifierad"})
    outs=pd.DataFrame([{"record_id":"r1","horizon":"1y","return_pct":0.02,"excess_return_pct":-0.08}])
    result=failed_recommendation_analysis(recs,outs,"1y")
    assert len(result)==1
    assert result.iloc[0]["Mätning"]=="Mot index"
    assert "värdefälla" in result.iloc[0]["Svagaste signaler"]


def test_raw_loss_is_fallback_when_benchmark_is_missing():
    recs=_recs({"Case Evidence Count":2})
    outs=pd.DataFrame([{"record_id":"r1","horizon":"1y","return_pct":-0.12,"excess_return_pct":None}])
    result=failed_recommendation_analysis(recs,outs,"1y")
    assert len(result)==1
    assert result.iloc[0]["Mätning"]=="Rå kursutveckling"


def test_no_reconstruction_when_old_snapshot_lacks_warning_fields():
    recs=_recs({})
    outs=pd.DataFrame([{"record_id":"r1","horizon":"1y","return_pct":-0.20}])
    result=failed_recommendation_analysis(recs,outs,"1y")
    assert result.iloc[0]["Diagnosstatus"]=="Orsak kan inte utläsas"
    assert "frysta data" in result.iloc[0]["Svagaste signaler"]


def test_summary_is_cautious_and_new_snapshots_freeze_data_quality_fields():
    failures=pd.DataFrame([{"Diagnosstatus":"Möjliga svagheter fanns redan"},{"Diagnosstatus":"Orsak kan inte utläsas"}])
    summary=failure_pattern_summary(failures)
    assert summary["count"]==2 and summary["diagnosable"]==1
    cols=snapshot_columns("long")
    assert "Fundamental Data status" in cols
    assert "Vinstkvalitet status" in cols
