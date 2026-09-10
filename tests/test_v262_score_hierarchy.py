from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_main_discover_has_one_primary_metric_per_horizon():
    assert 'b.metric("Borsify"' in APP
    assert 'Topp 10 i kategorin' in APP

def test_advanced_engine_is_collapsed():
    assert 'with st.expander("Fler analysverktyg", expanded=False):' in APP

def test_secondary_numeric_evidence_remains_available():
    assert 'render_engine_board(filtered)' in APP
