from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_254_or_newer():
    assert 'APP_VERSION = "2.53.0"' not in APP

def test_relative_strength_ui_is_plain_swedish():
    assert "**Jämfört med marknaden och sektorn**" in APP
    assert "Jämförelsen bygger på" in APP
    assert "Relativ jämförelse:" in APP
