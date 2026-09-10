from pathlib import Path
from confirmed_why_now import build_confirmed_why_now


def test_two_positive_families_create_confirmed_plain_language():
    out = build_confirmed_why_now({
        "Förändringsbekräftelse kandidat": True,
        "Förändringsbekräftelse historikfamiljer": 2,
        "Förändringsbekräftelse positiva familjer": "Rapport, Konsensus",
    })
    assert out["Bekräftat varför nu status"] == "Bekräftat varför nu"
    assert "rapportutvecklingen förbättras" in out["Bekräftat varför nu"].lower()
    assert "analytikerna blir mer positiva" in out["Bekräftat varför nu"].lower()
    assert out["Bekräftat varför nu stöd antal"] == 2


def test_three_families_explain_strong_confirmation_without_score():
    out = build_confirmed_why_now({
        "Förändringsbekräftelse kandidat": True,
        "Förändringsbekräftelse stark": True,
        "Förändringsbekräftelse historikfamiljer": 3,
        "Förändringsbekräftelse positiva familjer": "Rapport, Konsensus, Ledning",
    })
    assert out["Bekräftat varför nu stark"] is True
    assert "Tre oberoende förändringar" in out["Bekräftat varför nu"]
    assert not any("score" in key.lower() for key in out)


def test_conflict_is_explicit_and_not_confirmed():
    out = build_confirmed_why_now({
        "Förändringsbekräftelse historikfamiljer": 2,
        "Förändringsbekräftelse varning": True,
        "Förändringsbekräftelse positiva familjer": "Rapport",
        "Förändringsbekräftelse negativa familjer": "Konsensus",
    })
    assert out["Bekräftat varför nu status"] == "Motstridigt varför nu"
    assert out["Bekräftat varför nu konflikt"] is True
    assert "men" in out["Bekräftat varför nu"]


def test_one_positive_family_is_not_overstated():
    out = build_confirmed_why_now({
        "Förändringsbekräftelse historikfamiljer": 2,
        "Förändringsbekräftelse positiva familjer": "Ledning",
    })
    assert out["Bekräftat varför nu status"] == "Ett positivt förändringsstöd"
    assert "ännu inte" in out["Bekräftat varför nu"]


def test_missing_history_is_neutral():
    out = build_confirmed_why_now({"Förändringsbekräftelse historikfamiljer": 1})
    assert out["Bekräftat varför nu status"] == "För lite historik"
    assert out["Bekräftat varför nu stöd antal"] == 0
    assert out["Bekräftat varför nu motbevis antal"] == 0


def test_release_wiring_and_version():
    app = Path('app.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "3.73.0"' in app
    assert 'from confirmed_why_now import build_confirmed_why_now' in app
    assert 'bq_confirmed_why_now_radar' in app
    assert 'Varför just nu – verifierat från flera håll' in app
