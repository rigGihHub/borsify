from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_255_or_newer():
    assert 'APP_VERSION = "2.54.0"' not in APP

def test_market_regime_is_explained_in_plain_swedish():
    assert "**Marknadsläget**" in APP
    assert "**Marknadsläget**" in APP
    assert "aktuellt köpkrav" in APP
    assert "Marknadskontroll:" in APP
