from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_259_or_newer():
    assert 'APP_VERSION = "2.58.0"' not in APP

def test_earnings_quality_ui_is_plain_swedish():
    assert "**Blir vinsten faktiskt pengar?**" in APP
    assert "redovisad vinst med verkligt kassaflöde" in APP
    assert "kundfordringar eller lager växer snabbare än försäljningen" in APP
