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
