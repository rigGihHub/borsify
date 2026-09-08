from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_discover_defaults_to_two_decision_cards():
    assert 'st.markdown("## Aktier att titta på")' in APP
    assert '"Kortare sikt", "Ungefär 1–6 månader"' in APP
    assert '"Längre sikt", "Flera år"' in APP

def test_discover_dense_sections_are_collapsed_or_removed():
    assert 'with st.expander("Fler kandidater", expanded=False):' in APP
    assert 'with st.expander("Sök på ett särskilt sätt", expanded=False):' in APP
    assert 'with st.expander("Fler analysverktyg", expanded=False):' in APP
    assert 'st.subheader("Dagens bästa möjligheter")' not in APP
    assert 'st.subheader("Jämför dagens kortlista")' not in APP
    assert 'st.subheader("Fler aktier som passar")' not in APP

def test_discovery_tab_labels_use_plain_language():
    assert 'st.tabs(["Aktier", "Nya uppslag", f"Signaler ({unread_signals})"])' in APP
