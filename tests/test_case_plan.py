import pandas as pd
from case_plan import build_case_plan, apply_case_plans


def test_short_plan_uses_verified_short_signals():
    case = {
        "Short Why Now": "stark relativ styrka; positiv teknisk trend",
        "Short Relative Strength": 72,
        "Short Trend": 81,
        "Short Revisions": 68,
        "Short Catalyst": 40,
        "Short Counterargument": "momentum kan vända",
        "Short Vetoes": "—",
    }
    plan = build_case_plan(case, "short")
    assert "stark relativ styrka" in plan["Case Plan Tes"]
    assert "relativ styrka fortsätter" in plan["Case Plan Bekräftelse"]
    assert "estimatsignalerna" in plan["Case Plan Bekräftelse"]
    assert plan["Case Plan Varning"] == "momentum kan vända"


def test_short_plan_does_not_invent_price_target():
    plan = build_case_plan({
        "Short Why Now":"trend",
        "Short Relative Strength":70,
        "Short Trend":80,
        "Short Vetoes":"—",
    }, "short")
    assert "Ingen godtycklig procentgräns" in plan["Case Plan Prisregel"]


def test_short_plan_flags_relevance_reassessment_after_large_move():
    plan = build_case_plan({
        "Short Why Now":"trend",
        "Relevans nu":"Mindre attraktivt än vid signal",
        "Sedan rekommendation":0.15,
    }, "short")
    assert "+15.0%" in plan["Case Plan Prisregel"]
    assert "omprövas nu" in plan["Case Plan Prisregel"]


def test_long_plan_uses_scenarios_without_calling_them_target_prices():
    plan = build_case_plan({
        "Varför marknaden kan ha fel":"marginalerna normaliseras",
        "Inflection Score":70,
        "Mispricing Signal":"Möjlig felprissättning",
        "Base upside":0.35,
        "Bear upside":-0.20,
        "Scenario Asymmetry":1.75,
        "Case Vetoes":"inga hårda motbevis i gate-modellen",
    }, "long")
    assert "Base +35%" in plan["Case Plan Prisregel"]
    assert "Bear -20%" in plan["Case Plan Prisregel"]
    assert "gamla uppsidesiffror får inte återanvändas" in plan["Case Plan Prisregel"]


def test_long_plan_refuses_price_rule_without_scenario_data():
    plan = build_case_plan({"Varför marknaden kan ha fel":"kvalitet underskattas"}, "long")
    assert "underlaget saknas" in plan["Case Plan Prisregel"]


def test_apply_case_plans_preserves_row_count_and_adds_columns():
    frame = pd.DataFrame([{"Ticker":"A.ST","Short Why Now":"trend"}])
    out = apply_case_plans(frame, "short")
    assert len(out) == 1
    assert "Case Plan Tes" in out.columns
    assert out.iloc[0]["Case Plan Tes"] == "trend"
