from crowded_narrative import build_crowded_narrative
from pathlib import Path


def test_low_coverage_never_crowded():
    x=build_crowded_narrative({"Konsensus bullish andel":1.0,"Konsensus analytiker antal":3,"Riktkurs potential":0.0,"Värdering":20})
    assert x["Crowded varning"] is False


def test_popularity_alone_is_not_warning():
    x=build_crowded_narrative({"Konsensus bullish andel":0.85,"Konsensus analytiker antal":10,"Riktkurs potential":0.30,"Värdering":70})
    assert x["Crowded varning"] is False


def test_broad_positive_with_limited_upside_warns():
    x=build_crowded_narrative({"Konsensus bullish andel":0.85,"Konsensus analytiker antal":10,"Riktkurs potential":0.06,"Värdering":60})
    assert x["Crowded varning"] is True
    assert "begränsad uppsida" in x["Crowded status"]


def test_extreme_and_stretched_can_be_strong_warning():
    x=build_crowded_narrative({"Konsensus bullish andel":0.95,"Konsensus analytiker antal":12,"Riktkurs potential":0.05,"Värdering":25})
    assert x["Crowded stark varning"] is True


def test_missing_target_does_not_invent_limited_upside():
    x=build_crowded_narrative({"Konsensus bullish andel":0.85,"Konsensus analytiker antal":8,"Värdering":70})
    assert x["Crowded varning"] is False


def test_release_and_ui_present():
    app=Path('app.py').read_text()
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'Förväntningsrisk – när nästan alla redan är positiva' in app
