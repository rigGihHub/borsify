import pandas as pd
from case_breaker import evaluate_case_breakers


def _history():
    return pd.DataFrame([{"score": 74}, {"score": 70}])


def test_breaker_triggers_when_quality_is_below_user_limit():
    out = evaluate_case_breakers(
        {"score": 72, "quality": 54, "risk": 70},
        _history(),
        {"min_score": 60, "min_quality": 60, "min_risk": 55, "max_score_drop": 15},
    )
    assert out["status"] == "Case-breaker utlöst"
    assert any("Kvalitet" in item for item in out["triggered"])


def test_breaker_detects_large_score_drop_from_first_snapshot():
    out = evaluate_case_breakers(
        {"score": 58, "quality": 70, "risk": 70},
        _history(),
        {"min_score": 0, "min_quality": 0, "min_risk": 0, "max_score_drop": 12},
    )
    assert out["status"] == "Case-breaker utlöst"
    assert any("fallit" in item for item in out["triggered"])


def test_no_breaker_means_neutral_setup_message():
    out = evaluate_case_breakers(
        {"score": 70, "quality": 70, "risk": 70},
        _history(),
        {"min_score": 0, "min_quality": 0, "min_risk": 0, "max_score_drop": 0},
    )
    assert out["status"] == "Inga case-breakers satta"
