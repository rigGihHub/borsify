from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_discover_defaults_to_three_decision_horizons():
    assert 'st.markdown("## Vad rekommenderar Borsify idag?")' in APP
    assert 'Köp nu – sälj i närtid' in APP
    assert 'Äg upp till ett år' in APP
    assert 'Äg resten av livet' in APP

def test_discover_dense_sections_are_collapsed_or_removed():
    assert 'with st.expander("Sök på ett särskilt sätt", expanded=False):' in APP
    assert 'with st.expander("Fler analysverktyg", expanded=False):' in APP
    assert 'st.subheader("Dagens bästa möjligheter")' not in APP

def test_discovery_tab_labels_use_plain_language():
    assert 'st.tabs(["Aktier", "Nya uppslag", f"Signaler ({unread_signals})"])' in APP
