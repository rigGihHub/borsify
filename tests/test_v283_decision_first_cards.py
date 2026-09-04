from pathlib import Path

APP = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")

def test_v283_decision_first_toplist_copy():
    assert 'APP_VERSION = "2.83.0"' in APP
    assert '## Borsifys bästa köp' in APP
    assert 'Bara köp som klarar Borsifys krav.' in APP
    assert '**Vad ska du kontrollera?**' in APP

def test_v283_hides_scores_and_data_checks_from_card_first_view():
    assert 'st.metric("Borsifys huvudbetyg"' not in APP
    assert 'with st.expander("Visa mer om bedömningen", expanded=False):' in APP
    assert 'st.caption(f"Underlaget: {readiness_status}"' in APP
    assert 'st.caption(f"Datakoll: {trust_status}' in APP
