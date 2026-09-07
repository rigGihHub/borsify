import numpy as np
from expectation_change import build_expectation_change
from case_quality_gate import build_case_quality_gate


def test_strong_positive_requires_analyst_and_reported_alignment():
    out = build_expectation_change({
        "EPS-estimat förändring": 0.06,
        "EPS-revisionsbalans": 0.6,
        "Estimat tillförlitlighetsvikt": 1.0,
        "Analytiker antal": 12,
        "Omsättning acceleration": 0.06,
        "Marginal YoY förändring": 0.03,
        "Vinst YoY senaste kvartal": 0.20,
    })
    assert out["Förväntningsriktning"] == "positiv"
    assert out["Förväntningsstyrka"] == "stark"
    assert "stöd i siffrorna" in out["Förväntningsförändring"]


def test_positive_analyst_view_does_not_hide_weak_reported_data():
    out = build_expectation_change({
        "EPS-estimat förändring": 0.05,
        "EPS-revisionsbalans": 0.5,
        "Estimat tillförlitlighetsvikt": 1.0,
        "Omsättning acceleration": -0.08,
        "Marginal YoY förändring": -0.04,
        "Vinst YoY senaste kvartal": -0.30,
    })
    assert out["Förväntningsriktning"] == "konflikt"
    assert "svagare siffror" in out["Förväntningsförändring"]


def test_thin_analyst_coverage_cannot_create_expectation_upgrade_on_its_own():
    out = build_expectation_change({
        "EPS-estimat förändring": 0.20,
        "EPS-revisionsbalans": 1.0,
        "Estimat tillförlitlighetsvikt": 0.25,
        "Analytiker antal": 1,
    })
    assert out["Förväntning analyst direction"] == 0
    assert out["Förväntningsriktning"] == "neutral"


def test_case_gate_can_use_expectation_change_without_new_mega_score():
    case = {
        "Djupkontroll": "Klarar djupkontroll",
        "Value Trap Risk": 20,
        "Deep Confidence": 80,
        "Inflection Confidence": 70,
        "Inflection Signal": "Neutral / oklar förändring",
        "Förväntningsriktning": "positiv",
        "Förväntningsförändring": "Förväntningarna förbättras med stöd i siffrorna",
        "Mispricing Signal": "Möjlig felprissättning",
        "Scenario Status": "OK",
        "Scenario Verdict": "Möjligen attraktiv asymmetri",
        "Scenario Asymmetry": 1.5,
        "Scenario Confidence": 70,
        "Catalyst Signal": "Närliggande kontrollpunkt",
        "Catalyst Support": False,
        "Catalyst Confidence": 60,
        "Fundamental Data status": "STARKT UNDERLAG",
    }
    out = build_case_quality_gate(case)
    assert out["Case Evidence Count"] >= 4
    assert "Score" not in " ".join(out.keys())
