import pandas as pd

from catalyst_engine import build_catalyst_assessment
from case_quality_gate import build_case_quality_gate

NOW = pd.Timestamp("2026-09-03", tz="UTC")


def _base_top_case():
    return {
        "Djupkontroll": "Klarar djupkontroll", "Value Trap Risk": 15, "Deep Confidence": 80,
        "Inflection Signal": "Positiv inflektion", "Inflection Confidence": 80,
        "Mispricing Signal": "Tydlig möjlig felprissättning",
        "Scenario Status": "OK", "Scenario Verdict": "Attraktiv asymmetri",
        "Scenario Asymmetry": 2.5, "Scenario Confidence": 80, "INVEST Score": 90,
    }


def test_fundamental_inflection_explains_why_now_but_is_not_double_counted_as_independent_catalyst():
    case = {"Inflection Signal": "Positiv inflektion", "Inflection Confidence": 80,
            "EPS-estimat förändring": 0.08}
    r = build_catalyst_assessment(case, {}, NOW)
    assert r["Primary Catalyst"] == "Fundamental inflektion"
    assert r["Catalyst Support"] is False
    assert r["Catalyst Independent Support"] is False
    assert "samma signalfamilj" in r["Catalyst Verification"]


def test_fresh_named_external_positive_signal_can_be_independent_catalyst_support():
    events = {"news": [{"title": "Company wins contract worth EUR 500 million",
                        "published_at": "2026-09-01", "provider": "Reuters"}]}
    r = build_catalyst_assessment({}, events, NOW)
    assert r["Catalyst Support"] is True
    assert r["Catalyst Independent Support"] is True
    assert r["Catalyst Source"] == "Reuters"
    assert "originalkällan" in r["Catalyst Verification"]


def test_positive_external_headline_without_named_provider_is_not_independent_support():
    events = {"news": [{"title": "Company wins contract worth EUR 500 million",
                        "published_at": "2026-09-01"}]}
    r = build_catalyst_assessment({}, events, NOW)
    assert r["Catalyst Support"] is False


def test_topcase_does_not_get_fifth_pillar_by_reusing_inflection_data():
    base = _base_top_case()
    cat = build_catalyst_assessment({**base, "EPS-estimat förändring": 0.08}, {}, NOW)
    gate = build_case_quality_gate({**base, **cat})
    assert gate["Case Evidence Count"] == 4
    assert gate["Case Gate"] != "Toppcase"


def test_topcase_can_get_fifth_pillar_from_fresh_independent_external_signal():
    base = _base_top_case()
    events = {"news": [{"title": "Company wins contract worth EUR 500 million",
                        "published_at": "2026-09-01", "provider": "Reuters"}]}
    cat = build_catalyst_assessment(base, events, NOW)
    gate = build_case_quality_gate({**base, **cat})
    assert gate["Case Evidence Count"] == 5
    assert gate["Case Gate"] == "Toppcase"
