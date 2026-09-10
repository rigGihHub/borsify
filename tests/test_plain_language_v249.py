from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_deep_case_uses_plain_scenario_names():
    assert 'plain_finance_text' in APP
    assert 'Varför nu?' in APP
    assert 'Största risken' in APP
