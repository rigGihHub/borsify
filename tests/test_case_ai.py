import pandas as pd
from case_ai import build_case_ai_context, build_case_ai_input, build_case_ai_instructions, local_case_explanation


def test_long_context_contains_case_evidence_but_not_unknown_fields():
    case = {
        "Ticker":"ALLEI.ST","Namn":"Alleima","Pris":91.2,"Case Gate":"Starkt case",
        "Case Confidence":71,"Case Supports":["fundamental kvalitet","felprissättning"],
        "Devil's Advocate":"värderingen har redan stigit",
        "Secret Internal Thing":"do not include",
    }
    ctx = build_case_ai_context(case, "long")
    assert ctx["case_data"]["Ticker"] == "ALLEI.ST"
    assert ctx["case_data"]["Case Supports"] == ["fundamental kvalitet","felprissättning"]
    assert "Secret Internal Thing" not in ctx["case_data"]


def test_short_context_uses_short_fields():
    case = {
        "Ticker":"A.ST","Short Alpha Score":78,"Short Why Now":"stark relativ styrka",
        "Case Gate":"Toppcase",
    }
    ctx = build_case_ai_context(case, "short")
    assert ctx["case_data"]["Short Alpha Score"] == 78
    assert "Case Gate" not in ctx["case_data"]


def test_input_contains_user_question_and_guardrailed_context():
    case = {"Ticker":"ALLEI.ST","Case Gate":"Starkt case","Confidence":80}
    prompt = build_case_ai_input(case, "long", "Varför när den redan gått så starkt?")
    assert "Varför när den redan gått så starkt?" in prompt
    assert "ALLEI.ST" in prompt
    assert "Confidence är evidenstäckning" in prompt


def test_instructions_require_counterargument_and_no_hallucination():
    ins = build_case_ai_instructions()
    assert "starkaste motargumentet" in ins
    assert "Hitta aldrig på" in ins
    assert "absolut aktiekurs" in ins


def test_local_fallback_is_explicitly_not_ai():
    case = {"Ticker":"A.ST","Case Gate":"Bevaka","Case Supports":["kvalitet"],"Devil's Advocate":"dyr"}
    text = local_case_explanation(case, "long")
    assert "regelbaserat reservsvar" in text
    assert "dyr" in text


def test_short_context_now_includes_current_valuation_and_price_relevance_data():
    case = {
        "Ticker":"BUFAB.ST","Pris":134.0,"Valuta":"SEK","Prisdatum":"2026-09-02",
        "P/E":22.4,"Forward P/E":18.7,"EV/EBITDA":13.2,"FCF yield":0.041,
        "ROE":0.19,"Vinstmarginal":0.11,"Risk":68,
        "Short Alpha Score":71,"Short Trend":88,"Short Relative Strength":50,
    }
    ctx = build_case_ai_context(case, "short")
    data = ctx["case_data"]
    assert data["Pris"] == 134.0
    assert data["Valuta"] == "SEK"
    assert data["P/E"] == 22.4
    assert data["Forward P/E"] == 18.7
    assert data["FCF yield"] == 0.041
    assert data["Short Trend"] == 88


def test_instructions_explain_current_price_relevance_without_equating_price_with_valuation():
    ins = build_case_ai_instructions()
    assert "fortfarande är relevant från dagens kurs" in ins
    assert "hög aktiekurs i kronor" in ins
    assert "Forward P/E" in ins
