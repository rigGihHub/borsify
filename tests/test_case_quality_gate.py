import pandas as pd
from case_quality_gate import build_case_quality_gate, case_gate_rank_key


def base_case():
    return {
        "Djupkontroll": "Klarar djupkontroll",
        "Value Trap Risk": 15,
        "Deep Confidence": 80,
        "Inflection Signal": "Positiv inflektion",
        "Inflection Confidence": 75,
        "Mispricing Signal": "Tydlig möjlig felprissättning",
        "Scenario Status": "OK",
        "Scenario Verdict": "Attraktiv asymmetri",
        "Scenario Asymmetry": 2.5,
        "Scenario Confidence": 75,
        "Catalyst Signal": "Tydlig möjlig katalysator",
        "Catalyst Support": True,
        "Catalyst Confidence": 75,
        "INVEST Score": 86,
    }


def test_five_independent_supports_can_make_top_case():
    r = build_case_quality_gate(base_case())
    assert r["Case Gate"] == "Toppcase"
    assert r["Case Evidence Count"] == 5
    assert r["Case Veto Count"] == 0


def test_value_trap_cannot_be_rescued_by_other_positive_signals():
    c = base_case(); c["Djupkontroll"] = "Avstå tills vidare"; c["Value Trap Risk"] = 85
    r = build_case_quality_gate(c)
    assert r["Case Gate"] == "Ej toppcase"
    assert r["Case Veto Count"] >= 1


def test_demanding_valuation_blocks_top_case():
    c = base_case(); c["Mispricing Signal"] = "Marknaden kan vara mer rimlig än caset"
    r = build_case_quality_gate(c)
    assert r["Case Gate"] != "Toppcase"
    assert r["Case Veto Count"] >= 1


def test_negative_inflection_is_real_counterevidence():
    c = base_case(); c["Inflection Signal"] = "Tydlig försämring"
    r = build_case_quality_gate(c)
    assert r["Case Gate"] != "Toppcase"
    assert "försämras" in r["Case Vetoes"]


def test_low_data_confidence_prevents_top_case():
    c = base_case(); c["Deep Confidence"] = 25; c["Inflection Confidence"] = 20; c["Scenario Confidence"] = 20
    r = build_case_quality_gate(c)
    assert r["Case Gate"] == "Ej toppcase"
    assert r["Case Confidence"] < 45


def test_rank_prefers_gate_before_invest_score():
    strong = base_case(); strong.update(build_case_quality_gate(strong))
    weak = base_case(); weak["Djupkontroll"] = "Kräver extra kontroll"; weak["INVEST Score"] = 99; weak.update(build_case_quality_gate(weak))
    assert case_gate_rank_key(strong) > case_gate_rank_key(weak)


def test_topcase_requires_concrete_catalyst():
    case = {
        'Djupkontroll':'Klarar djupkontroll','Value Trap Risk':15,'Deep Confidence':80,
        'Inflection Signal':'Positiv inflektion','Inflection Confidence':80,
        'Mispricing Signal':'Tydlig möjlig felprissättning',
        'Scenario Status':'OK','Scenario Verdict':'Attraktiv asymmetri','Scenario Asymmetry':2.5,'Scenario Confidence':80,
        'Catalyst Signal':'Ingen tydlig katalysator verifierad','Catalyst Support':False,'Catalyst Confidence':0,
        'INVEST Score':90,
    }
    r = build_case_quality_gate(case)
    assert r['Case Gate'] != 'Toppcase'
    assert r['Case Evidence Count'] == 4


def test_five_independent_supports_can_make_topcase():
    case = {
        'Djupkontroll':'Klarar djupkontroll','Value Trap Risk':15,'Deep Confidence':80,
        'Inflection Signal':'Positiv inflektion','Inflection Confidence':80,
        'Mispricing Signal':'Tydlig möjlig felprissättning',
        'Scenario Status':'OK','Scenario Verdict':'Attraktiv asymmetri','Scenario Asymmetry':2.5,'Scenario Confidence':80,
        'Catalyst Signal':'Tydlig möjlig katalysator','Catalyst Support':True,'Catalyst Confidence':75,
        'INVEST Score':90,
    }
    r = build_case_quality_gate(case)
    assert r['Case Gate'] == 'Toppcase'
    assert r['Case Evidence Count'] == 5
