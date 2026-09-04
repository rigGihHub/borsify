import json
import pandas as pd

from recommendation_failure_analysis import failure_pattern_analysis, failure_pattern_overview


def _dataset(n_signal=10, n_clean=10, signal_failures=6, clean_failures=1, relative=True):
    recs=[]
    outs=[]
    total=n_signal+n_clean
    for i in range(total):
        has_signal=i<n_signal
        snap={"Case Evidence Count": 2 if has_signal else 6}
        recs.append({
            "record_id":f"r{i}", "horizon_type":"long", "snapshot_json":json.dumps(snap),
        })
        if has_signal:
            failed=i<signal_failures
        else:
            failed=(i-n_signal)<clean_failures
        row={"record_id":f"r{i}", "horizon":"1y", "return_pct":-0.20 if failed else 0.12}
        if relative:
            row["excess_return_pct"]=-0.08 if failed else 0.05
        outs.append(row)
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_pattern_compares_failure_rate_with_and_without_signal():
    recs,outs=_dataset()
    result=failure_pattern_analysis(recs,outs,"1y")
    row=result[result["Signal"]=="Få oberoende stöd"].iloc[0]
    assert row["Exponerade"]==10
    assert row["Utan signal"]==10
    assert row["Misslyckandegrad med signal"]==0.6
    assert row["Misslyckandegrad utan signal"]==0.1
    assert row["Status"]=="Möjligt återkommande mönster"
    assert row["Mätning"]=="Mot index"


def test_missing_snapshot_fields_are_not_counted_as_clean_cases():
    recs,outs=_dataset(n_signal=5,n_clean=5,signal_failures=3,clean_failures=1)
    extra=pd.DataFrame([{"record_id":f"old{i}","horizon_type":"long","snapshot_json":"{}"} for i in range(10)])
    extra_out=pd.DataFrame([{"record_id":f"old{i}","horizon":"1y","return_pct":0.1,"excess_return_pct":0.02} for i in range(10)])
    result=failure_pattern_analysis(pd.concat([recs,extra],ignore_index=True),pd.concat([outs,extra_out],ignore_index=True),"1y")
    row=result[result["Signal"]=="Få oberoende stöd"].iloc[0]
    assert row["Exponerade"]==5
    assert row["Utan signal"]==5


def test_pattern_uses_one_basis_for_whole_cohort_and_does_not_mix():
    recs,outs=_dataset(relative=True)
    outs.loc[0,"excess_return_pct"]=None
    result=failure_pattern_analysis(recs,outs,"1y")
    assert set(result["Mätning"])=={"Rå kursutveckling"}


def test_small_groups_are_not_promoted_to_pattern():
    recs,outs=_dataset(n_signal=4,n_clean=4,signal_failures=4,clean_failures=0)
    result=failure_pattern_analysis(recs,outs,"1y")
    row=result[result["Signal"]=="Få oberoende stöd"].iloc[0]
    assert row["Status"]=="För lite underlag"
    overview=failure_pattern_overview(result)
    assert overview["status"]=="För lite historik"


def test_pattern_output_never_contains_automatic_weight_changes():
    recs,outs=_dataset()
    result=failure_pattern_analysis(recs,outs,"1y")
    overview=failure_pattern_overview(result)
    assert "new_weight" not in overview
    assert "new_threshold" not in overview
