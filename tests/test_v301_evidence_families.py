from pathlib import Path

from evidence_families import build_evidence_families, evidence_family_rows
from case_quality_gate import build_case_quality_gate


def strong_case():
    return {
        "Mispricing Signal": "Tydlig möjlig felprissättning",
        "Djupkontroll": "Klarar djupkontroll",
        "Deep Confidence": 80,
        "Vinstkvalitet status": "STARK VINSTKVALITET",
        "Kapitaldisciplin status": "EFFEKTIV KAPITALANVÄNDNING",
        "Förväntningsriktning": "positiv",
        "Förväntningsförändring": "Förväntningarna förbättras med stöd i siffrorna",
        "Inflection Confidence": 75,
        "Relativ styrka": 72,
        "Relativ marknad 3 mån": .09,
        "Relativ sektor 3 mån": .06,
        "Relativ styrka förklaring": "starkare än marknad och sektor",
        "Catalyst Signal": "Tydlig möjlig katalysator",
        "Catalyst Support": True,
        "Catalyst Independent Support": True,
        "Catalyst Confidence": 70,
        "Primary Catalyst": "höjda prognoser efter rapport",
        "Scenario Status": "OK",
        "Scenario Verdict": "Attraktiv asymmetri",
        "Scenario Asymmetry": 2.4,
        "Scenario Confidence": 70,
        "Value Trap Risk": 25,
        "Fundamental Data status": "STARKT UNDERLAG",
        "Redundans status": "OK",
    }


def test_correlated_quality_inputs_count_as_one_family():
    out = build_evidence_families(strong_case())
    assert out["Evidence Family Bolagskvalitet"] == "STÖD"
    assert out["Evidence Family Support Count"] == 5
    assert "Bolagskvalitet" in out["Evidence Family Supports"]


def test_risk_clean_does_not_add_positive_support():
    out = build_evidence_families(strong_case())
    assert out["Evidence Family Risk/motbevis"] == "NEUTRAL"
    assert out["Evidence Family Support Count"] == 5


def test_report_and_catalyst_are_one_family_not_two_votes():
    c = strong_case()
    c["Post-report stöd"] = True
    c["Post-report status"] = "Positiv rapportdrift"
    out = build_evidence_families(c)
    assert out["Evidence Family Händelse/katalysator"] == "STÖD"
    assert out["Evidence Family Support Count"] == 5


def test_warning_family_is_visible_and_gate_uses_family_count():
    c = strong_case()
    c["Relativ styrka"] = 30
    c["Mispricing Signal"] = "Ingen tydlig felprissättning"
    fam = build_evidence_families(c)
    c.update(fam)
    gate = build_case_quality_gate(c)
    assert fam["Evidence Family Kursbekräftelse"] == "VARNING"
    assert fam["Evidence Family Support Count"] == 3
    assert gate["Case Evidence Basis"] == "oberoende signalgrupper"
    assert gate["Case Evidence Count"] == 3


def test_family_rows_have_six_stable_groups():
    out = build_evidence_families(strong_case())
    rows = evidence_family_rows(out)
    assert [r["Familj"] for r in rows] == [
        "Pris/värdering", "Bolagskvalitet", "Förändrade förväntningar",
        "Kursbekräftelse", "Händelse/katalysator", "Risk/motbevis",
    ]


def test_app_wires_evidence_families_before_quality_gate():
    app = Path("app.py").read_text()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "build_evidence_families" in app
    assert app.index("assessment.update(build_evidence_families") < app.index("assessment.update(build_case_quality_gate")
    assert "Liknande mått räknas inte flera gånger" in app
