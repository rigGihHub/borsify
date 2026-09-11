from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_v341_keeps_compact_primary_case():
    assert 'APP_VERSION = "3.81.0"' in APP
    assert 'Förstaval' in APP
    assert 'Varför nu?' in APP
    assert 'Största risken' in APP

def test_engine_details_are_secondary():
    assert APP.index('Fler analysverktyg') > APP.index('Vad rekommenderar Borsify idag?')
