from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_252_or_newer():
    assert 'APP_VERSION = "2.51.0"' not in APP

def test_near_buy_ui_is_present():
    assert "👀 Nära köpsignal" in APP
    assert "**Vad saknas?**" in APP

def test_chase_warning_is_present():
    assert "Har aktien redan gått långt?" in APP
    assert "Risk att köpa efter en stor uppgång" in APP
