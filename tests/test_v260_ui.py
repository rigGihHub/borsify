from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_data_trust_is_still_available_in_analysis_engine():
    assert 'Data Trust status' in APP
    assert 'Fler analysverktyg' in APP
