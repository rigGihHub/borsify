import pandas as pd

from inflection_engine import build_inflection_metrics, assess_inflection


def _estimate(n):
    return pd.DataFrame({"numberOfAnalysts": [n]}, index=["+1y"])

def _trend():
    return pd.DataFrame({"current": [12.0], "30daysAgo": [10.0]}, index=["+1y"])

def _revisions(up=5, down=1):
    return pd.DataFrame({"upLast30days": [up], "downLast30days": [down]}, index=["+1y"])

def test_broad_coverage_keeps_full_estimate_weight():
    m = build_inflection_metrics(pd.DataFrame(), pd.DataFrame(), _trend(), _revisions(), earnings_estimate=_estimate(25))
    assert m["Analytikertäckning"] == "Bred analytikertäckning"
    assert m["Estimat tillförlitlighetsvikt"] == 1.0
    r = assess_inflection(m)
    assert "EPS-estimat har höjts" in r["Positiva förändringar"]

def test_one_analyst_is_deliberately_downweighted():
    m = build_inflection_metrics(pd.DataFrame(), pd.DataFrame(), _trend(), _revisions(1, 0), earnings_estimate=_estimate(1))
    assert m["Analytikertäckning"] == "Mycket tunn analytikertäckning"
    assert m["Estimat tillförlitlighetsvikt"] == 0.25
    r = assess_inflection(m)
    assert r["Inflection Score"] < 60

def test_missing_total_coverage_uses_revision_activity_without_inventing_analyst_count():
    m = build_inflection_metrics(pd.DataFrame(), pd.DataFrame(), _trend(), _revisions(5, 1))
    assert pd.isna(m["Analytiker antal"])
    assert m["Analytikertäckning"] == "Analytikeraktivitet finns, total täckning oklar"
    assert m["Estimat tillförlitlighetsvikt"] == 0.6

def test_no_coverage_means_estimate_direction_cannot_move_score():
    m = build_inflection_metrics(pd.DataFrame(), pd.DataFrame(), _trend(), pd.DataFrame())
    assert m["Estimat tillförlitlighetsvikt"] == 0.0
    r = assess_inflection(m)
    assert r["Inflection Score"] == 50.0
