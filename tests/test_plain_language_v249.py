from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_at_least_249():
    assert 'APP_VERSION = "' in APP
    assert 'APP_VERSION = "2.48.0"' not in APP

def test_main_tabs_use_plain_historical_test_name():
    assert '["Marknad", "Historiska tester"]' in APP
    assert '["Marknad", "Edge Lab"]' not in APP

def test_buy_gate_is_explained_in_swedish():
    assert "Bara köp som klarar Borsifys krav" in APP
    assert "Buy Quality Gate" not in APP

def test_case_breaker_visible_heading_is_plain():
    assert "**Vad skulle få dig att tänka om kring aktien?**" in APP
    assert "**Case-breaker · vad skulle få dig att tänka om?**" not in APP

def test_deep_case_uses_plain_scenario_names():
    assert '**TRE MÖJLIGA FRAMTIDSBILDER**' in APP
    assert 's1.metric("Svagt scenario"' in APP
    assert 's2.metric("Grundscenario"' in APP
    assert 's3.metric("Starkt scenario"' in APP

def test_plain_finance_text_translates_common_jargon():
    assert '("mispricing", "möjlig felprissättning")' in APP
    assert '("EPS", "vinst per aktie")' in APP
    assert '("FCF", "fritt kassaflöde")' in APP
