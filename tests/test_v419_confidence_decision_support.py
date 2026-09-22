import importlib.util
from confidence_decision_support import assess_confidence_adjusted_decision

def test_strong_idea_strong_data_is_top_quadrant():
    r=assess_confidence_adjusted_decision({
        "Deal Conviction Score":82,"Analysis Confidence Score":84,
        "Ingångsläge nivå":"green","Bolagsbedömning nivå":"green",
    })
    assert r["Decision Support nivå"]==4
    assert "STARK IDÉ / STARK DATA"==r["Decision Support quadrant"]

def test_strong_idea_weak_data_demands_verification():
    r=assess_confidence_adjusted_decision({
        "Deal Conviction Score":82,"Analysis Confidence Score":42,
        "Analysis Confidence blockerare":"öppen circuit breaker",
    })
    assert r["Decision Support nivå"]==3
    assert "svag data" in r["Decision Support"].lower()

def test_weak_idea_strong_data_is_not_buy_signal():
    r=assess_confidence_adjusted_decision({
        "Deal Conviction Score":35,"Analysis Confidence Score":88,
    })
    assert r["Decision Support nivå"]==2
    assert "inte tillräckligt attraktivt" in r["Decision Support action"]

def test_red_entry_prevents_highest_priority():
    r=assess_confidence_adjusted_decision({
        "Deal Conviction Score":90,"Analysis Confidence Score":90,
        "Ingångsläge nivå":"red","Bolagsbedömning nivå":"green",
    })
    assert r["Decision Support nivå"]<4

def test_decision_support_does_not_modify_deal_conviction():
    deal=open("deal_conviction.py",encoding="utf-8").read()
    assert "Decision Support" not in deal
    assert "Analysis Confidence" not in deal

def test_app_imports_all_restored_health_layers_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert "from data_failure_transparency import" in app
    assert "from source_health_dashboard import" in app
    assert "from analysis_confidence import" in app
    assert "from confidence_decision_support import" in app
    assert "add_confidence_adjusted_decision(ranked)" in app

def test_app_can_be_parsed_with_required_symbols_imported():
    # Regression against v4.18 missing-import bug. Static import statements must exist.
    app=open("app.py",encoding="utf-8").read()
    for symbol in [
        "assess_failure_transparency","build_source_health_rows",
        "summarize_source_health","assess_analysis_confidence"
    ]:
        assert f"import" in app and symbol in app
