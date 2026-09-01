import math
from short_term_engine import assess_short_term_case


BENCH = {"month": .02, "3m": .05, "6m": .10}


def strong_row():
    return {
        "Pris": 120, "SMA50": 112, "Avstånd SMA200": .08,
        "1 mån": .08, "3 mån": .18, "6 mån": .30,
        "Dagsförändring": .01, "RSI14": 58, "Volymkvot": 1.4,
        "Risk": 75, "Omsättning MSEK/dag": 40, "Riskflaggor": "—",
    }


def test_strong_confirmed_case_can_rank_high():
    r = assess_short_term_case(
        strong_row(), BENCH,
        {"Inflection Score": 78, "Inflection Signal": "Positiv inflektion"},
        {"Catalyst Signal": "Tydlig möjlig katalysator", "Catalyst Support": True, "Primary Catalyst": "Order/kontrakt"},
    )
    assert r["Short Alpha Gate"] in {"Kortsiktigt toppcase", "Starkt kortsiktigt case"}
    assert r["Short Confirmation Count"] >= 4
    assert r["Short Alpha Score"] >= 65


def test_large_fall_is_not_rewarded():
    row = strong_row()
    row.update({"Avstånd SMA200": -.24, "1 mån": -.28, "3 mån": -.32, "6 mån": -.40, "Dagsförändring": -.12, "RSI14": 22})
    r = assess_short_term_case(row, BENCH, {}, {})
    assert r["Short Alpha Gate"] == "Ej kortsiktigt toppcase"
    assert r["Short Alpha Score"] <= 54
    assert "fall" in (r["Short Cautions"] + r["Short Vetoes"]).lower() or "negativ" in r["Short Vetoes"].lower()


def test_negative_revisions_can_veto_otherwise_good_chart():
    row = strong_row()
    r = assess_short_term_case(
        row, BENCH,
        {"Inflection Score": 15, "Inflection Signal": "Tydlig försämring"},
        {"Catalyst Signal": "Ingen tydlig katalysator verifierad", "Catalyst Support": False},
    )
    assert r["Short Alpha Gate"] == "Ej kortsiktigt toppcase"
    assert "försämras" in r["Short Vetoes"]


def test_profit_warning_vetoes_short_case():
    r = assess_short_term_case(
        strong_row(), BENCH,
        {"Inflection Score": 75, "Inflection Signal": "Positiv inflektion"},
        {"Catalyst Signal": "Ny risk måste verifieras först", "Catalyst Support": False},
    )
    assert r["Short Alpha Gate"] == "Ej kortsiktigt toppcase"


def test_relative_strength_compares_with_benchmark():
    row = strong_row()
    better = assess_short_term_case(row, {"month": 0, "3m": 0, "6m": 0})
    worse = assess_short_term_case(row, {"month": .15, "3m": .30, "6m": .45})
    assert better["Short Relative Strength"] > worse["Short Relative Strength"]


def test_report_date_alone_does_not_create_positive_catalyst():
    r = assess_short_term_case(
        strong_row(), BENCH, {},
        {"Catalyst Signal": "Närliggande kontrollpunkt", "Catalyst Support": False, "Primary Catalyst": "Kommande rapport"},
    )
    assert r["Short Catalyst"] < 70


def test_low_liquidity_is_caution_not_free_alpha():
    row = strong_row()
    row["Omsättning MSEK/dag"] = .4
    r = assess_short_term_case(row, BENCH)
    assert "låg daglig omsättning" in r["Short Cautions"]


def test_oversold_is_not_positive_factor_by_itself():
    row = strong_row()
    row.update({"RSI14": 20, "1 mån": -.10, "3 mån": -.05, "Avstånd SMA200": -.07})
    r = assess_short_term_case(row, BENCH)
    assert "översåld" in r["Short Cautions"]
    assert r["Short Alpha Gate"] != "Kortsiktigt toppcase"
