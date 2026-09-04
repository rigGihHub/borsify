from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_v269_search_controls_remain_after_later_releases():
    assert 'discovery_intent = st.selectbox(' in APP
    assert 'search_horizon = st.selectbox(' in APP

def test_simple_search_has_case_horizon_country_price():
    assert '"Typ av case", DISCOVERY_INTENTS' in APP
    assert '"Tidshorisont",' in APP
    assert 'selected_countries = st.multiselect(' in APP
    assert '"Pris från (SEK)"' in APP
    assert '"Pris till (SEK)"' in APP

def test_search_summary_is_available():
    assert 'with st.expander("Din sökning", expanded=False):' in APP
    assert 'st.write(f"**Case:** {discovery_intent}")' in APP
    assert 'st.write(f"**Tid:** {search_horizon}")' in APP

def test_horizon_uses_existing_horizon_builder():
    assert 'apply_search_horizon(filtered, search_horizon, add_horizon_scores)' in APP
