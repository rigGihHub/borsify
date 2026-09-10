from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_fundamental_change_ui_is_plain_and_separates_observed_from_estimates():
    assert 'plain_finance_text' in APP
    assert 'När ska jag ompröva?' in APP
