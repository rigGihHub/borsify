import pandas as pd
from horizon_signal_changes import add_change_signals, classify_change, dropped_from_top10


def test_new_strong_case_is_new_buy_signal():
    label, _ = classify_change(current_signal="KÖP NU", current_rank=2, current_score=76, previous_rank=None, previous_score=None, horizon="medium")
    assert label == "NY KÖPSIGNAL"


def test_rank_improvement_strengthens_even_with_small_score_move():
    label, _ = classify_change(current_signal="KÖP", current_rank=2, current_score=71, previous_rank=5, previous_score=70, horizon="medium")
    assert label == "STÄRKT"


def test_material_score_drop_weakens():
    label, _ = classify_change(current_signal="BEVAKA", current_rank=4, current_score=66, previous_rank=4, previous_score=70, horizon="year")
    assert label == "FÖRSVAGAD"


def test_small_changes_are_unchanged():
    label, _ = classify_change(current_signal="BYGG POSITION", current_rank=3, current_score=70, previous_rank=4, previous_score=69, horizon="year")
    assert label == "OFÖRÄNDRAD"


def test_missing_history_never_infers_strengthening_for_watch_signal():
    label, _ = classify_change(current_signal="BEVAKA PRISET", current_rank=1, current_score=75, previous_rank=None, previous_score=None, horizon="lifetime")
    assert label == "NY PÅ LISTAN"


def test_add_change_signals_does_not_mutate_score_or_ranking():
    current = pd.DataFrame([
        {"Ticker": "AAA", "Signal": "KÖP NU", "Mellan Score": 75.0},
        {"Ticker": "BBB", "Signal": "KÖP", "Mellan Score": 72.0},
    ])
    previous = pd.DataFrame([
        {"Ticker": "AAA", "Rank": 2, "Score": 74.0},
        {"Ticker": "BBB", "Rank": 1, "Score": 72.0},
    ])
    out = add_change_signals(current, previous, "Mellan Score", "medium")
    assert out["Ticker"].tolist() == ["AAA", "BBB"]
    assert out["Mellan Score"].tolist() == [75.0, 72.0]
    assert "Förändring" in out.columns


def test_departures_are_not_called_sell_signals():
    current = pd.DataFrame([{"Ticker": "AAA"}])
    previous = pd.DataFrame([{"Ticker": "AAA", "Rank": 1, "Score": 80}, {"Ticker": "BBB", "Rank": 2, "Score": 78}])
    assert dropped_from_top10(current, previous) == ["BBB"]


def test_version_and_ui_wiring():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.73.0"' in app
    assert '"Förändring"' in app
    assert "Lämnat topp 10 sedan föregående sparade analys" in app
