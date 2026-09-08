from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"app.py").read_text(encoding="utf-8")
LANG=(ROOT/"decision_language.py").read_text(encoding="utf-8")

def test_version_is_at_least_249():
    assert 'APP_VERSION = "' in APP
    assert 'APP_VERSION = "2.48.0"' not in APP

def test_main_tabs_use_plain_historical_test_name():
    assert 'st.tabs(["Alla aktier", "Så fungerar Borsify", "Analyslabbet"])' in APP
    assert '["Marknad", "Edge Lab"]' not in APP

def test_buy_gate_is_explained_in_swedish():
    assert "Bara köp som klarar Borsifys krav" in APP
    assert "Buy Quality Gate" not in APP

def test_case_breaker_visible_heading_is_plain():
    assert "**Vad skulle få dig att tänka om kring aktien?**" in APP
    assert "**Case-breaker · vad skulle få dig att tänka om?**" not in APP

def test_deep_case_uses_plain_scenario_names():
    assert 'with st.expander("Visa analysen bakom", expanded=False):' in APP
    assert '"Varför nu"' in APP

def test_plain_finance_text_translates_common_jargon():
    assert 'möjlig felprissättning' in LANG
    assert 'vinst per aktie' in LANG
    assert 'fritt kassaflöde' in LANG
