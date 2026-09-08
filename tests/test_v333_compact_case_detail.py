from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")

def test_v333_version_and_compact_long_case():
    assert 'APP_VERSION = "3.38.0"' in APP
    assert 'st.markdown("**Varför nu?**")' in APP
    assert 'st.markdown("**Största risken**")' in APP
    assert 'with st.expander("Visa analysen bakom", expanded=False):' in APP
    assert 'with st.expander("Visa delbedömningar"):' not in APP

def test_long_case_engine_details_are_after_disclosure():
    disclosure = APP.index('with st.expander("Visa analysen bakom", expanded=False):')
    datakoll = APP.index('"Datakvalitet": case.get("Data Trust status", "—")', disclosure)
    assert datakoll > disclosure
