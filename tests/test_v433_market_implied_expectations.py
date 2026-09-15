from market_implied_expectations import assess_market_implied_expectations


def base():
    return {
        "Värdering": 72,
        "Värdering täckning": .8,
        "Värderingsmått antal": 4,
        "Forward P/E": 16,
        "FCF-yield": .06,
        "KPI Inflection nivå": 2,
        "Revision breadth nivå": 2,
        "Förändringsbekräftelse positiva familjer antal": 2,
        "Analysis Confidence Score": 75,
        "1 mån": .04,
        "Relativ marknad 3 mån": .03,
        "Relativ sektor 3 mån": .02,
        "Value Trap verdict": "MARKET_WRONG",
    }


def test_low_burden_plus_confirmed_improvement_is_strong_candidate():
    result = assess_market_implied_expectations(base())
    assert result["Market-Implied Expectations status"] == "LOW_EXPECTATIONS_BEING_BEATEN"
    assert result["Market-Implied Expectations nivå"] == 3


def test_cheap_without_improvement_is_not_promoted():
    row = {**base(), "KPI Inflection nivå": 0, "Revision breadth nivå": 0, "Förändringsbekräftelse positiva familjer antal": 0}
    result = assess_market_implied_expectations(row)
    assert result["Market-Implied Expectations status"] == "NO_IMPROVEMENT_CONFIRMATION"


def test_value_trap_blocks_positive_gap():
    result = assess_market_implied_expectations({**base(), "Value Trap verdict": "VALUE_TRAP"})
    assert result["Market-Implied Expectations nivå"] <= 1


def test_rerating_already_advanced_is_demanding():
    result = assess_market_implied_expectations({**base(), "1 mån": .30})
    assert result["Market-Implied Expectations status"] == "EXPECTATIONS_DEMANDING"


def test_thin_valuation_data_stays_unknown():
    result = assess_market_implied_expectations({**base(), "Värdering täckning": .2, "Värderingsmått antal": 1})
    assert result["Market-Implied Expectations status"] == "UNQUANTIFIABLE"


def test_low_confidence_blocks_strong_label():
    result = assess_market_implied_expectations({**base(), "Analysis Confidence Score": 30})
    assert result["Market-Implied Expectations status"] == "LOW_CONFIDENCE"


def test_app_wires_advisory_layer_without_ranking_effect():
    app = open("app.py", encoding="utf-8").read()
    rankings = open("horizon_rankings.py", encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.1"' in app
    assert "add_market_implied_expectations(ranked)" in app
    assert "Market-Implied Expectations" not in rankings
