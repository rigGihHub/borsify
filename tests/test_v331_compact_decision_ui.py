from pathlib import Path

APP = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")

def test_v331_version_and_compact_overview():
    assert 'APP_VERSION = "3.81.0"' in APP
    assert '## Idag' in APP
    assert 'with st.expander("Fler val och verktyg", expanded=False)' in APP
    assert '**Öppna en annan aktie**' in APP
    assert 'with st.expander("Anpassa sökningen", expanded=False)' in APP

def test_old_dashboard_noise_removed_from_overview():
    start = APP.index("def render_overview(")
    end = APP.index("def save_ai_usage", start)
    overview = APP[start:end]
    assert '## Nytt sedan sist' not in overview
    assert '## {focus_meta' not in overview
    assert '### Fler aktier värda en titt' not in overview
    assert 'Scanning:' not in overview
