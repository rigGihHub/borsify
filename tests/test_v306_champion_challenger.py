import pandas as pd

from champion_challenger import (
    ChallengerSpec,
    STATUS_BETTER,
    STATUS_WAIT,
    ACTION_CONTINUE,
    compare_short_challenger,
    challenger_governance,
    default_short_challengers,
)
from model_change_log import model_change_log_table


def test_default_challengers_are_pre_registered_and_simple():
    rows = default_short_challengers()
    assert len(rows) == 6
    assert len({x.challenger_id for x in rows}) == 6
    assert all(x.excluded_signal for x in rows)


def test_governance_requires_multiple_horizons_before_continuing():
    one = pd.DataFrame([
        {"Challenger": "Utan Trend", "Status": STATUS_BETTER, "Oberoende case": 30},
    ])
    g1 = challenger_governance(one)
    assert g1.iloc[0]["Åtgärd"] != ACTION_CONTINUE

    two = pd.DataFrame([
        {"Challenger": "Utan Trend", "Status": STATUS_BETTER, "Oberoende case": 30},
        {"Challenger": "Utan Trend", "Status": STATUS_BETTER, "Oberoende case": 28},
    ])
    g2 = challenger_governance(two)
    assert g2.iloc[0]["Åtgärd"] == ACTION_CONTINUE


def test_empty_comparison_waits_instead_of_guessing():
    spec = ChallengerSpec("x", "Test", "Trend", "hypotes")
    out = compare_short_challenger(pd.DataFrame(), pd.DataFrame(), "1m", spec)
    assert out["Status"] == STATUS_WAIT
    assert out["Oberoende case"] == 0


def test_change_log_contains_champion_challenger_and_no_auto_promotion_language():
    table = model_change_log_table()
    row = table[table["Version"].eq("3.06.0")].iloc[0]
    assert "Champion" in row["Förändring"]
    assert "innan manuell" in row["Motivering"]


def test_v306_ui_and_version_are_wired():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Champion–Challenger" in app
    assert "Modellens ändringslogg" in app
    assert "produktionsmodellen automatiskt" in app
