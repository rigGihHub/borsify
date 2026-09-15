from pathlib import Path

import pandas as pd

from up_and_coming import assess_up_and_coming, select_up_and_coming


ROOT = Path(__file__).resolve().parents[1]


def _case(**changes):
    row = {
        "Ticker": "GROW.ST", "Börsvärde BSEK": 8.0,
        "Omsättningstillväxt": 0.18, "Vinsttillväxt": 0.25,
        "Vinstmarginal": 0.10, "ROE": 0.15, "FCF-yield": 0.04,
        "Skuld/eget kapital": 70, "Kvalitet": 68, "Datatäckning": 0.80,
        "KPI Inflection nivå": 2, "Revision breadth nivå": 1,
        "Analysis Confidence nivå": 3, "Value Trap verdict": "MARKET_WRONG",
        "Bolagsbedömning nivå": "green", "Ingångsläge nivå": "green",
        "Års Score": 72, "Avanza-universum": True, "Omsättning MSEK/dag": 1.0,
    }
    row.update(changes)
    return row


def test_strong_smaller_company_requires_multiple_evidence_families():
    result = assess_up_and_coming(_case())
    assert result["Up and coming godkänd"] is True
    assert result["Up and coming evidensfamiljer"] == 4
    assert result["Up and coming"].startswith("💎")


def test_growth_alone_is_not_enough():
    result = assess_up_and_coming(_case(**{
        "Vinstmarginal": None, "ROE": None, "FCF-yield": None,
        "KPI Inflection nivå": None, "Revision breadth nivå": None,
        "Fundamental förändring antal": None, "Kvalitet": 20,
        "Skuld/eget kapital": 200,
    }))
    assert result["Up and coming godkänd"] is False


def test_missing_market_cap_is_blocked_but_microcap_can_qualify():
    assert "börsvärde saknas" in assess_up_and_coming(_case(**{"Börsvärde BSEK": None}))["Up and coming blockerare"]
    assert assess_up_and_coming(_case(**{"Börsvärde BSEK": 0.2}))["Up and coming godkänd"] is True


def test_avanza_catalog_and_observed_liquidity_are_required():
    outside = assess_up_and_coming(_case(**{"Avanza-universum": False}))
    illiquid = assess_up_and_coming(_case(**{"Omsättning MSEK/dag": 0.05}))
    assert "Avanza-katalog" in outside["Up and coming blockerare"]
    assert "handelsaktivitet" in illiquid["Up and coming blockerare"]


def test_value_trap_red_entry_and_low_confidence_are_blocked():
    cases = [
        _case(**{"Value Trap verdict": "VALUE_TRAP"}),
        _case(**{"Ingångsläge nivå": "red"}),
        _case(**{"Analysis Confidence nivå": 1}),
    ]
    assert not select_up_and_coming(pd.DataFrame(cases)).shape[0]


def test_ranking_uses_evidence_then_growth_without_new_mega_score():
    frame = pd.DataFrame([
        _case(Ticker="SLOW", **{"Omsättningstillväxt": 0.12}),
        _case(Ticker="FAST", **{"Omsättningstillväxt": 0.30}),
    ])
    selected = select_up_and_coming(frame)
    assert selected.iloc[0]["Ticker"] == "FAST"
    assert "Up and coming Score" not in selected.columns


def test_app_has_direct_button_clickable_list_and_honest_copy():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.38.1"' in app
    assert "🚀 Visa bästa up and coming-aktierna" in app
    assert 'bq_horizon_focus"] = "upcoming"' in app
    assert "render_up_and_coming(filtered, profile)" in app
    assert "Ingen lista kan veta vilka som får en fantastisk framtid" in app
    assert "open_upcoming_" in app
    assert 'filtered["Avanza-universum"]' in app
    assert "Kontrollera alltid hos Avanza" in app


def test_cold_start_card_is_explicitly_stale_not_current():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "SENAST KOMPLETTA FÖRSTAVAL" in app
    assert "UPPDATERAS NU" in app
    assert "inte ett aktuellt köpråd" in app
    assert "latest_first_choice(DB_PATH, profile, market)" in app
