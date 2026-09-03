from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_261_or_newer():
    assert 'APP_VERSION = "2.60.0"' not in APP

def test_homepage_starts_with_three_focus_cases():
    assert 'st.markdown("## Dagens bästa möjligheter")' in APP
    assert "Borsify börjar med högst tre kandidater" in APP
    assert 'daily_shortlist.head(3)' in APP

def test_secondary_horizon_lists_are_collapsed():
    assert 'with st.expander("Visa bästa köp efter tidshorisont", expanded=False):' in APP

def test_main_navigation_is_conditional_not_streamlit_tabs():
    assert 'page = st.radio(' in APP
    assert 'if page == "Överblick":' in APP
    assert 'elif page == "Upptäck":' in APP

def test_deep_analysis_is_inside_discover_branch():
    discover=APP.index('elif page == "Upptäck":')
    deep=APP.index('deep_longlist = build_deep_longlist', discover)
    assert deep > discover
    pre_discover=APP[:discover]
    assert 'deep_longlist = build_deep_longlist' not in pre_discover

def test_discover_explains_lazy_loading():
    assert "Fördjupad kandidatgranskning körs först när du öppnar Upptäck" in APP

def test_holdings_are_collapsed_on_homepage():
    assert 'with st.expander("Min portfölj och säljkontroll", expanded=False):' in APP
