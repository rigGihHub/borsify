import pandas as pd

from decision_tiebreaker import rank_close_daily_candidates


def _frame(rows):
    return pd.DataFrame(rows)


def test_close_call_prefers_better_supported_case_over_tiny_relevance_edge():
    df = _frame([
        {"Ticker":"A.ST", "Dagens relevans":80.0, "Borsify Score":82, "Datatäckning":.80, "Case Readiness":62, "Relativ styrka":54, "Severe":False},
        {"Ticker":"B.ST", "Dagens relevans":78.5, "Borsify Score":81, "Datatäckning":.82, "Case Readiness":79, "Relativ styrka":58, "Severe":False},
    ])
    out = rank_close_daily_candidates(df)
    assert out.iloc[0]["Ticker"] == "B.ST"


def test_tiebreaker_cannot_overturn_clear_daily_relevance_gap():
    df = _frame([
        {"Ticker":"A.ST", "Dagens relevans":82.0, "Borsify Score":82, "Datatäckning":.75, "Case Readiness":61, "Relativ styrka":48, "Severe":False},
        {"Ticker":"B.ST", "Dagens relevans":77.5, "Borsify Score":83, "Datatäckning":.95, "Case Readiness":95, "Relativ styrka":90, "Severe":False},
    ])
    out = rank_close_daily_candidates(df)
    assert out.iloc[0]["Ticker"] == "A.ST"


def test_relative_strength_only_breaks_close_call_after_evidence_quality():
    df = _frame([
        {"Ticker":"A.ST", "Dagens relevans":79.0, "Borsify Score":82, "Datatäckning":.85, "Case Readiness":75, "Relativ styrka":52, "Severe":False},
        {"Ticker":"B.ST", "Dagens relevans":78.7, "Borsify Score":81, "Datatäckning":.84, "Case Readiness":75, "Relativ styrka":66, "Severe":False},
    ])
    out = rank_close_daily_candidates(df)
    assert out.iloc[0]["Ticker"] == "B.ST"


def test_severe_risk_loses_a_close_call():
    df = _frame([
        {"Ticker":"A.ST", "Dagens relevans":80.0, "Borsify Score":84, "Datatäckning":.90, "Case Readiness":90, "Relativ styrka":80, "Severe":True},
        {"Ticker":"B.ST", "Dagens relevans":79.0, "Borsify Score":80, "Datatäckning":.78, "Case Readiness":68, "Relativ styrka":55, "Severe":False},
    ])
    out = rank_close_daily_candidates(df)
    assert out.iloc[0]["Ticker"] == "B.ST"
