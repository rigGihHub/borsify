from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_258_or_newer():
    assert 'APP_VERSION = "2.57.0"' not in APP

def test_fundamental_change_ui_is_plain_and_separates_observed_from_estimates():
    assert '"Förändrade förväntningar"' in APP
    assert 'case.get("Förväntningsförändring"' in APP
