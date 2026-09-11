from pathlib import Path
from change_confirmation_engine import build_change_confirmation


def test_requires_two_independent_history_families():
    out = build_change_confirmation({
        "Rapportminne historik": True,
        "Rapportminne förbättring": True,
    })
    assert out["Förändringsbekräftelse kandidat"] is False
    assert out["Förändringsbekräftelse status"] == "För lite oberoende förändringshistorik"


def test_two_positive_families_confirm_change():
    out = build_change_confirmation({
        "Rapportminne historik": True, "Rapportminne förbättring": True,
        "Konsensusminne historik": True, "Konsensusminne positiv": True,
    })
    assert out["Förändringsbekräftelse kandidat"] is True
    assert out["Förändringsbekräftelse stark"] is False
    assert out["Förändringsbekräftelse positiva familjer"] == "Rapport, Konsensus"


def test_three_positive_families_are_strong_confirmation():
    out = build_change_confirmation({
        "Rapportminne historik": True, "Rapportminne förbättring": True,
        "Konsensusminne historik": True, "Konsensusminne positiv": True,
        "Ledningsminne historik": True, "Ledningsminne positiv": True,
    })
    assert out["Förändringsbekräftelse kandidat"] is True
    assert out["Förändringsbekräftelse stark"] is True


def test_positive_and_negative_families_are_conflict_not_confirmation():
    out = build_change_confirmation({
        "Rapportminne historik": True, "Rapportminne förbättring": True,
        "Konsensusminne historik": True, "Konsensusminne negativ": True,
    })
    assert out["Förändringsbekräftelse kandidat"] is False
    assert out["Förändringsbekräftelse varning"] is True
    assert "säger emot" in out["Förändringsbekräftelse status"]


def test_missing_history_never_counts_as_evidence():
    out = build_change_confirmation({
        "Rapportminne historik": False, "Rapportminne förbättring": True,
        "Konsensusminne historik": True, "Konsensusminne positiv": True,
        "Ledningsminne historik": True,
    })
    assert out["Förändringsbekräftelse positiva familjer"] == "Konsensus"
    assert out["Förändringsbekräftelse kandidat"] is False


def test_two_negative_families_create_warning_not_buy_candidate():
    out = build_change_confirmation({
        "Rapportminne historik": True, "Rapportminne försämring": True,
        "Ledningsminne historik": True, "Ledningsminne negativ": True,
    })
    assert out["Förändringsbekräftelse kandidat"] is False
    assert out["Förändringsbekräftelse varning"] is True
    assert out["Förändringsbekräftelse status"] == "Försämringen bekräftas från flera håll"


def test_release_wiring_and_version():
    app = Path('app.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'from change_confirmation_engine import build_change_confirmation' in app
    assert 'Förändringsbekräftelse status' in app
