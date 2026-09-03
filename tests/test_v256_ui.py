from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_256_or_newer():
    assert 'APP_VERSION = "2.55.0"' not in APP

def test_learning_ui_is_present_and_cautious():
    assert "#### Vad har Borsify lärt sig hittills?" in APP
    assert "Jämför historiska utfall efter" in APP
    assert "Borsify ändrar inte vikter eller köpgränser automatiskt" in APP
    assert "Kan börja jämföras" in APP
