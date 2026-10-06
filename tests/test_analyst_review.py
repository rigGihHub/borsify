import math
import pandas as pd
import pytest
from dividend_units import dividend_fields, clean_legacy_dividend
from analysis_confidence import assess_analysis_confidence
from purchase_consistency import reconcile_purchase_decisions, purchase_blockers
from position_entry_guidance import add_position_entry_guidance
from top_pick_explainer import explain_top_pick
from decision_brief import build_decision_brief


def verified(**overrides):
    return {"Signal": "BYGG POSITION", "Deal Conviction Score": 75,
            "Datatäckning": 1, "Fundamental source status": "OK", "Deep source status": "OK",
            "KPI strukturerad täckning": 3, "Deep Confidence": 90,
            "Deal Conviction oberoende familjer": 4,
            "Ingångsläge nivå": "green", "Bolagsbedömning nivå": "green", "Risk": 75,
            "Historik år": 4, "Rapportdatum": pd.Timestamp.now(tz="UTC").isoformat(), **overrides}


@pytest.mark.parametrize("raw", [1.86, .0186])
def test_proact_yield_uses_amount_and_price_regardless_of_vendor_display_unit(raw):
    result = dividend_fields({"dividendYield": raw, "dividendRate": 2.6, "currentPrice": 140})
    assert result["Direktavkastning"] == pytest.approx(.01857142857)
    assert clean_legacy_dividend(result) == result


def test_unknown_legacy_units_are_not_reinterpreted_or_displayed():
    assert math.isnan(clean_legacy_dividend({"Direktavkastning": 1.86})["Direktavkastning"])


@pytest.mark.parametrize("override", [{"Deal Conviction Score": 23}, {"Deep Confidence": 0}, {"KPI strukturerad täckning": 0}, {"För långt gången": True}])
def test_purchase_blockers_always_propagate_to_signal_and_zero_position(override):
    frame = pd.DataFrame([verified(**override)])
    result = add_position_entry_guidance(reconcile_purchase_decisions(frame, "year")).iloc[0]
    assert result["Signal"] == "BEVAKA"
    assert result["Första positionsstorlek %"] == 0
    assert result["Köpbeslut hinder"]


def test_verified_purchase_is_not_suppressed():
    assert not purchase_blockers(verified(), "lifetime")
    result = reconcile_purchase_decisions(pd.DataFrame([verified()]), "year")
    assert result.iloc[0]["Signal"] == "BYGG POSITION"


@pytest.mark.parametrize("field,value", [("Historik år", 1), ("Rapportdatum", None), ("Rapportdatum", "2020-01-01")])
def test_lifetime_requires_real_history_and_fresh_report(field, value):
    assert purchase_blockers(verified(**{field: value}), "lifetime")


def test_core_coverage_alone_does_not_make_confidence_green():
    result = assess_analysis_confidence(verified(**{"Deep Confidence": 0, "KPI strukturerad täckning": 0}))
    assert result["Analysis Confidence nivå"] < 3
    assert "verksamhetsmått saknas" in result["Analysis Confidence varningar"]


def test_equal_final_scores_explain_actual_horizon_tiebreak():
    result = explain_top_pick(pd.DataFrame([
        {"Ticker": "A", "Borsify slutbetyg": 68, "Års Score": 73.8},
        {"Ticker": "B", "Borsify slutbetyg": 68, "Års Score": 72.1},
    ]), "Års Score", "year")
    assert "Års Score: 73.80 mot 72.10" in result["Varför #1"]
    assert "Års Score" in result["Jämförelseunderlag"]


def test_brief_exposes_sources_and_does_not_turn_generic_buy_text_into_catalyst():
    result = build_decision_brief({"Omsättningstillväxt": .08, "Vinstmarginal": .1,
                                   "Fundamental hämtad": "2026-10-04", "Analysis Confidence": "🟢 Gott analysförtroende",
                                   "Varför nu": "Köp stegvis över lång tid"})
    assert "8.0%" in result["Decision Brief tes"]
    assert "inte rapportdatum" in result["Decision Brief tes"]
    assert "ingen tydlig händelse" in result["Decision Brief recognition"]
    assert "bra information" in result["Decision Brief confidence"]


def test_research_merge_preserves_headline_scores_and_prices_but_fills_verified_gaps():
    from research_merge import merge_research
    base = pd.DataFrame([{"Ticker": "A", "Borsify Score": 68, "Pris": 140, "Deep Confidence": math.nan}])
    deep = pd.DataFrame([{"Ticker": "A", "Borsify Score": 99, "Pris": 999, "Deep Confidence": 85, "Historik år": 4}])
    row = merge_research(base, deep).iloc[0]
    assert row["Borsify Score"] == 68 and row["Pris"] == 140
    assert row["Deep Confidence"] == 85 and row["Historik år"] == 4
    assert math.isnan(base.iloc[0]["Deep Confidence"])


def test_hot_deploy_reloads_stale_bootstrap_and_alternative_api():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-c', '''
import inspect
import model_bootstrap
import horizon_alternatives
model_bootstrap.RELEASE = 'old-release'
model_bootstrap._MODULES = []
horizon_alternatives.rank_horizon_alternatives = lambda frame, horizon, limit=3: frame
import app
assert model_bootstrap.RELEASE == '4.41.2-alternative-fundamentals'
assert 'evidence_fn' in inspect.signature(app.rank_horizon_alternatives).parameters
'''], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-2000:]
