from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_sidebar_has_one_primary_choice_and_collapsed_customization():
    assert 'st.header("Borsifys val")' in APP
    assert '"Vad vill du hitta?", DISCOVERY_INTENTS' in APP
    assert 'with st.expander("Anpassa sökningen", expanded=False):' in APP
    assert 'with st.expander("Din sökning", expanded=False):' not in APP
    assert 'with st.expander("Fler filter", expanded=False):' not in APP

def test_primary_navigation_is_reduced_to_four_destinations():
    assert '["Idag", "Fler aktier", f"Bevakning ({len(watch_df_global)})", "Mer"]' in APP
    assert 'elif page == "Marknad":' not in APP
    assert 'st.tabs(["Alla aktier", "Så fungerar Borsify", "Analyslabbet"])' in APP

def test_beginner_labels_avoid_internal_terms_in_primary_controls():
    assert '"Hur länge tänker du äga?"' in APP
    assert '"Var ska Borsify leta?"' in APP
    assert 'st.subheader("Alla analyserade aktier")' in APP
