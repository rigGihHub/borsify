from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")

def test_version_and_novice_first_overview():
    assert 'APP_VERSION = "3.38.0"' in APP
    assert '## Idag' in APP
    assert 'st.markdown(f"### {first_name}")' in APP
    assert 'Risk:' in APP
    assert 'Inget köp känns tillräckligt starkt idag' in APP

def test_overview_hides_engine_detail():
    assert 'with st.expander("Om dagens analys", expanded=False)' in APP
    assert '1 · FÖRSTAVAL' in APP

def test_daily_reason_language_is_less_technical():
    assert 'kursbilden är stark just nu' in APP
    assert 'why_today.append(f"RSI {rsi:.0f} visar' not in APP
