from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

def test_v336_version_and_compact_today_shell():
    assert 'APP_VERSION = "3.73.0"' in APP
    assert 'st.markdown("## Idag")' in APP
    assert '1 · FÖRSTAVAL' in APP
    assert '**Varför nu:**' in APP
    assert 'Risk:' in APP
    assert 'with st.expander("Mer", expanded=False)' in APP

def test_v336_first_choice_analysis_is_direct_and_manual_lookup_is_secondary():
    assert 'Visa analysen av {first_ticker}' in APP
    assert 'key_prefix="overview_first"' in APP
    assert '**Öppna en annan aktie**' in APP
