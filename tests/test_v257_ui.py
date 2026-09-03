from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_257_or_newer():
    assert 'APP_VERSION = "2.56.0"' not in APP

def test_case_quality_program_is_visible_and_plain_swedish():
    assert "**Hur bra är beslutsunderlaget?**" in APP
    assert "Detaljpoängen för underlaget finns under" in APP
    assert "Borsify lämnar hellre platsen tom" in APP
    assert "Styrkor i underlaget:" in APP
    assert "Luckor i underlaget:" in APP
