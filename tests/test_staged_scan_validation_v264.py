import pandas as pd

from staged_scan_validation import (
    add_price_only_prefilter_scores,
    build_candidate_pool,
    validate_candidate_pool,
    activation_readiness,
)

def sample(n=120):
    rows=[]
    for i in range(n):
        rows.append({
            "Ticker":f"T{i:03d}",
            "Dagsförändring":(i%9-4)/100,
            "1 mån":(i%17-5)/100,
            "3 mån":(i%23-6)/100,
            "6 mån":(i%31-8)/100,
            "52v från topp":-(i%30)/100,
            "RSI14":30+(i%45),
            "Volymkvot":0.6+(i%12)/10,
            "Avstånd SMA200":(i%25-8)/100,
            "Omsättning lokal M/dag":1+(i%40),
        })
    return pd.DataFrame(rows)

def test_price_only_scores_do_not_require_fundamental_fields():
    df=sample()
    out=add_price_only_prefilter_scores(df)
    assert "Prefilter trend" in out
    assert "Prefilter bästa pris-signal" in out

def test_candidate_pool_respects_target_size():
    df=sample(120)
    pool=build_candidate_pool(df,fraction=.60,minimum=80)
    assert len(pool)==80

def test_validation_reports_missed_targets():
    df=sample(120)
    targets={"T000","T119"}
    result=validate_candidate_pool(df,targets,fraction=.20,minimum=20)
    assert result["targets"]==2
    assert result["retained"] <= 2
    assert isinstance(result["missed"],list)

def test_activation_requires_multiple_high_recall_runs():
    hist=pd.DataFrame({"retention":[1.0,1.0,1.0,1.0]})
    result=activation_readiness(hist,minimum_runs=5)
    assert result["ready"] is False

def test_activation_can_become_ready_after_repeated_high_recall():
    hist=pd.DataFrame({"retention":[1.0,.99,1.0,.98,1.0,.99]})
    result=activation_readiness(hist,minimum_runs=5)
    assert result["ready"] is True

def test_activation_rejects_one_bad_run():
    hist=pd.DataFrame({"retention":[1.0,1.0,.90,1.0,1.0,1.0]})
    result=activation_readiness(hist,minimum_runs=5)
    assert result["ready"] is False
