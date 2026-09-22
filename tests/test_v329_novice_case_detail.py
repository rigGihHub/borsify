from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_and_novice_first_case_copy():
    assert 'APP_VERSION = "4.39.1"' in APP
    assert '**Vad kan få aktien att bli mer intressant:**' in APP
    assert '**Största risken**' in APP
    assert 'När ändrar Borsify sig?' in APP

def test_advanced_content_is_collapsed():
    assert 'with st.expander("Fler analysverktyg", expanded=False):' in APP
