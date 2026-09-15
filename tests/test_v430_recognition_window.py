import math

from recognition_window import assess_recognition_window


def base():
    return {
        "Catalyst-to-Recognition status": "STRONG_RECOGNITION_PATH",
        "Catalyst Independent Support": True,
        "Analysis Confidence Score": 75,
        "KPI Inflection nivå": 2,
        "Revision breadth nivå": 2,
        "Riktkurs potential": .24,
    }


def test_verified_near_catalyst_gets_near_window():
    result = assess_recognition_window({**base(), "Catalyst Timing": "inom en månad"})
    assert result["Recognition Window status"] == "NEAR"
    assert result["Recognition Window payoff status"] == "ATTRACTIVE"


def test_medium_and_long_are_kept_coarse():
    medium = assess_recognition_window({**base(), "Catalyst Timing": "inom cirka tre månader"})
    long = assess_recognition_window({**base(), "Catalyst Timing": "6–18 månader", "Riktkurs potential": .20})
    assert medium["Recognition Window status"] == "MEDIUM"
    assert long["Recognition Window status"] == "LONG"
    assert long["Recognition Window payoff status"] == "MIXED"


def test_missing_timing_stays_unknown():
    result = assess_recognition_window({**base(), "Catalyst Timing": "—"})
    assert result["Recognition Window status"] == "UNKNOWN"
    assert result["Recognition Window payoff status"] == "UNKNOWN"


def test_vague_timing_is_not_invented():
    result = assess_recognition_window({**base(), "Catalyst Timing": "senare"})
    assert result["Recognition Window status"] == "UNKNOWN"


def test_recent_event_needs_post_report_confirmation():
    unconfirmed = assess_recognition_window({**base(), "Catalyst Timing": "5 dagar sedan"})
    confirmed = assess_recognition_window({**base(), "Catalyst Timing": "5 dagar sedan", "Post-report dagar sedan": 5})
    assert unconfirmed["Recognition Window status"] == "UNKNOWN"
    assert confirmed["Recognition Window status"] == "NEAR"


def test_low_confidence_blocks_specific_window():
    result = assess_recognition_window({**base(), "Catalyst Timing": "inom en vecka", "Analysis Confidence Score": 30})
    assert result["Recognition Window status"] == "UNKNOWN"


def test_missing_upside_does_not_become_positive():
    result = assess_recognition_window({**base(), "Catalyst Timing": "inom en månad", "Riktkurs potential": math.nan})
    assert result["Recognition Window status"] == "NEAR"
    assert result["Recognition Window payoff status"] == "UNKNOWN"


def test_no_path_means_unknown_window():
    result = assess_recognition_window({**base(), "Catalyst-to-Recognition status": "NO_RECOGNITION_PATH", "Catalyst Timing": "inom en vecka"})
    assert result["Recognition Window status"] == "UNKNOWN"


def test_app_wires_signal_and_ledger_freezes_it_without_ranking_effect():
    app = open("app.py", encoding="utf-8").read()
    deal = open("deal_conviction.py", encoding="utf-8").read()
    rankings = open("horizon_rankings.py", encoding="utf-8").read()
    ledger = open("recommendation_ledger.py", encoding="utf-8").read()
    assert 'APP_VERSION = "4.37.0"' in app
    assert "add_recognition_window(ranked)" in app
    assert '"Recognition Window", "Recognition Window status"' in ledger
    assert "Recognition Window" not in deal
    assert "Recognition Window" not in rankings
