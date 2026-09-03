from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_264_or_newer():
    assert 'APP_VERSION = "2.63.0"' not in APP

def test_prefilter_is_validation_only():
    assert "This does NOT reduce today's Yahoo calls or change rankings." in APP
    assert "**Test av framtida snabbare scanning**" in APP
    assert "Därför används den inte för att styra dagens analys." in APP

def test_activation_requires_history():
    assert "minst fem separata körningar" in APP
    assert "mycket hög träff" in APP
