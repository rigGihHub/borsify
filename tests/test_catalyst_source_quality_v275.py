import pandas as pd
from catalyst_engine import build_catalyst_assessment, assess_catalyst_source_quality

NOW = pd.Timestamp("2026-09-03T12:00:00Z")

def _events(provider):
    return {"news": [{"title": "Company wins contract worth $500 million", "published_at": "2026-09-02T10:00:00Z", "provider": provider}]}

def test_reuters_is_strong_source_and_can_earn_independent_support():
    r = build_catalyst_assessment({}, _events("Reuters"), NOW)
    assert r["Catalyst Source Quality"] == "Stark källa"
    assert r["Catalyst Independent Support"] is True

def test_secondary_aggregator_does_not_earn_independent_support():
    r = build_catalyst_assessment({}, _events("Yahoo Finance"), NOW)
    assert r["Catalyst Source Quality"] == "Sekundär källa"
    assert r["Catalyst Independent Support"] is False
    assert "verifiera originalkällan" in r["Catalyst Verification"]

def test_unknown_named_source_is_context_not_topcase_support():
    r = build_catalyst_assessment({}, _events("Example News"), NOW)
    assert r["Catalyst Source Quality"] == "Okänd källkvalitet"
    assert r["Catalyst Independent Support"] is False

def test_missing_provider_has_no_source_quality_support():
    label, score, support = assess_catalyst_source_quality("")
    assert (label, score, support) == ("Källa saknas", 0, False)
