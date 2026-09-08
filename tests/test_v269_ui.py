from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_v269_search_controls_remain_after_later_releases():
    assert 'discovery_intent = st.selectbox(' in APP
    assert 'search_horizon = st.selectbox(' in APP

def test_simple_search_has_case_horizon_country_price():
    assert '"Vad vill du hitta?", DISCOVERY_INTENTS' in APP
    assert '"Hur länge tänker du äga?",' in APP
    assert 'selected_countries = st.multiselect(' in APP
    assert '"Min pris"' in APP
    assert '"Max pris"' in APP

def test_search_summary_is_available():
    assert 'with st.expander("Anpassa sökningen", expanded=False):' in APP
    assert 'st.caption(intent_plain_text(discovery_intent))' in APP
    assert '"Hur länge tänker du äga?"' in APP

def test_horizon_uses_existing_horizon_builder():
    assert 'apply_search_horizon(filtered, search_horizon, add_horizon_scores)' in APP
