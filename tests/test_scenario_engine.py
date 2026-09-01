import math
from scenario_engine import build_scenarios, scenario_summary

def test_requires_positive_eps_and_price():
    r = build_scenarios({"Pris": 100, "EPS": -2})
    assert r["status"] == "Otillräcklig data"

def test_builds_three_transparent_scenarios():
    row = {"Pris": 100, "EPS": 5, "Forward EPS": 5.6, "P/E": 20, "Forward P/E": 18}
    deep = {"Revenue CAGR": 0.09, "EPS CAGR": 0.10, "Value Trap Risk": 20}
    r = build_scenarios(row, deep)
    assert r["status"] == "OK"
    assert r["bear"]["future_price"] < r["base"]["future_price"] < r["bull"]["future_price"]
    assert r["bear"]["eps_growth"] < r["base"]["eps_growth"] < r["bull"]["eps_growth"]
    assert r["bear"]["exit_pe"] < r["base"]["exit_pe"] < r["bull"]["exit_pe"]

def test_value_trap_makes_bear_case_harsher():
    row = {"Pris": 100, "EPS": 5, "P/E": 20}
    healthy = build_scenarios(row, {"Revenue CAGR": .08, "EPS CAGR": .09, "Value Trap Risk": 10})
    risky = build_scenarios(row, {"Revenue CAGR": .08, "EPS CAGR": .09, "Value Trap Risk": 85})
    assert risky["bear"]["future_price"] < healthy["bear"]["future_price"]
    assert risky["base"]["future_price"] < healthy["base"]["future_price"]

def test_inflection_changes_growth_only_modestly():
    row = {"Pris": 100, "EPS": 5, "P/E": 20}
    deep = {"Revenue CAGR": .08, "EPS CAGR": .08}
    weak = build_scenarios(row, deep, {"score": 20})
    strong = build_scenarios(row, deep, {"score": 80})
    assert strong["base"]["eps_growth"] > weak["base"]["eps_growth"]
    assert strong["base"]["eps_growth"] - weak["base"]["eps_growth"] <= .08

def test_scenario_summary_is_not_a_buy_signal():
    row = {"Pris": 100, "EPS": 5, "P/E": 20}
    r = build_scenarios(row, {"Revenue CAGR": .08, "EPS CAGR": .08})
    text = scenario_summary(r)
    assert "Bear" in text and "Base" in text and "Bull" in text
    assert "köp" not in text.lower()

def test_extreme_growth_is_bounded():
    row = {"Pris": 100, "EPS": 2, "P/E": 50}
    r = build_scenarios(row, {"EPS CAGR": 1.5, "Revenue CAGR": .8})
    assert r["bull"]["eps_growth"] <= .30
    assert r["bull"]["exit_pe"] <= 38
