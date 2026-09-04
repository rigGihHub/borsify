from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_251_or_newer():
    assert 'APP_VERSION = "2.50.0"' not in APP

def test_toplist_cards_answer_four_questions():
    for text in [
        "**Varför köpa?**",
        "**Varför just nu?**",
        "**Största risken**",
        "**Vad ska du kontrollera?**",
    ]:
        assert text in APP

def test_technical_numbers_are_moved_to_expander():
    assert 'with st.expander("Visa mer om bedömningen", expanded=False):' in APP
    assert 'st.metric("Borsifys betyg för tidshorisonten"' in APP
