import pandas as pd

from catalyst_engine import build_catalyst_assessment

NOW=pd.Timestamp("2026-09-03T10:00:00Z")

def base_case():
    return {
        "Inflection Signal":"Neutral",
        "Inflection Confidence":50,
    }

def test_fresh_positive_headline_can_support_why_now():
    events={"news":[{
        "title":"Company wins new contract",
        "published_at":"2026-09-02T08:00:00Z",
        "provider":"Example News",
        "link":"https://example.invalid/story",
    }]}
    result=build_catalyst_assessment(base_case(),events,now=NOW)
    assert result["Primary Catalyst"]=="Order/kontrakt"
    assert result["Catalyst Timing"]=="1 dagar sedan"
    assert "Example News" in result["Catalyst Evidence"]

def test_undated_headline_cannot_be_why_now():
    events={"news":[{"title":"Company wins new contract"}]}
    result=build_catalyst_assessment(base_case(),events,now=NOW)
    assert result["Primary Catalyst"]=="Ingen verifierad"
    assert "utan verifierbart datum" in result["Catalyst Warnings"]

def test_old_headline_is_context_not_current_catalyst():
    events={"news":[{
        "title":"Company wins new contract",
        "published_at":"2026-07-01T08:00:00Z",
        "provider":"Example News",
    }]}
    result=build_catalyst_assessment(base_case(),events,now=NOW)
    assert result["Primary Catalyst"]=="Ingen verifierad"
    assert "Äldre rubrik" in result["Catalyst Warnings"]

def test_fresh_negative_headline_blocks_positive_catalyst_signal():
    events={"news":[{
        "title":"Company cuts guidance after weak quarter",
        "published_at":"2026-09-03T08:00:00Z",
        "provider":"Example News",
    }]}
    result=build_catalyst_assessment(base_case(),events,now=NOW)
    assert result["Catalyst Signal"]=="Ny risk måste verifieras först"
    assert "Färsk rubrik kan vara negativ" in result["Catalyst Warnings"]
