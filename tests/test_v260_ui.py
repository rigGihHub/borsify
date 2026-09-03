from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_260_or_newer():
    assert 'APP_VERSION = "2.59.0"' not in APP

def test_data_trust_is_visible_on_recommendations():
    assert "**Datakoll**" in APP
    assert "Källa:" in APP
    assert "Datavarning:" in APP
    assert "Yahoo Finance via yfinance" in APP
