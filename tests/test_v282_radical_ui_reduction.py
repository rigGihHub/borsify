from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_main_decision_copy_is_shorter():
    assert 'st.markdown("## Vad rekommenderar Borsify idag?")' in APP
    assert 'Köp nu – sälj i närtid' in APP
    assert 'Äg upp till ett år' in APP
    assert 'Äg resten av livet' in APP

def test_dense_tools_stay_secondary():
    assert 'with st.expander("Fler analysverktyg", expanded=False):' in APP
