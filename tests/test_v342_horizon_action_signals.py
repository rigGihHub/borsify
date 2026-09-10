from pathlib import Path
import pandas as pd

from horizon_signals import action_signal, add_action_signals, signal_legend

APP = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")


def row(**kw):
    base = {
        "Mellan Score": 76,
        "Års Score": 77,
        "Livstid Score": 80,
        "Case Readiness": 78,
        "Datatäckning": .90,
        "Värdering": 70,
        "Relativ styrka": 60,
        "För långt gången": False,
    }
    base.update(kw)
    return base


def test_strong_cases_get_horizon_specific_action_language():
    assert action_signal(row(), "medium").label == "KÖP NU"
    assert action_signal(row(), "year").label == "KÖP / ÄG"
    assert action_signal(row(), "lifetime").label == "KÖP / ÄG LÅNGSIKTIGT"


def test_missing_evidence_never_strengthens_signal():
    weak = row(**{"Case Readiness": None, "Datatäckning": None})
    assert action_signal(weak, "medium").label == "BEVAKA"
    assert action_signal(weak, "year").label == "BEVAKA"
    assert action_signal(weak, "lifetime").label == "BEVAKA"


def test_lifetime_good_company_can_still_be_price_watch():
    r = row(**{"Livstid Score": 74, "Värdering": 42, "Case Readiness": 70})
    assert action_signal(r, "lifetime").label == "BEVAKA PRISET"


def test_add_signals_is_presentation_only_and_keeps_order_and_scores():
    df = pd.DataFrame([row(**{"Mellan Score": 75}), row(**{"Mellan Score": 70})], index=[5, 9])
    out = add_action_signals(df, "medium")
    assert list(out.index) == [5, 9]
    assert list(out["Mellan Score"]) == [75, 70]
    assert "Signal" in out.columns
    assert "Signal förklaring" in out.columns


def test_legends_exist_for_all_three_homepage_horizons():
    for horizon in ("medium", "year", "lifetime"):
        assert len(signal_legend(horizon)) >= 3


def test_homepage_table_has_more_decision_context():
    assert '"Land", "Kurs", "Signal", "Förändring", "Varför ändrad?", "Score", "Till platsen ovan", "Risk"' in APP
    assert 'Vad betyder signalerna?' in APP
    assert 'Signal: {first.get' in APP
    assert 'APP_VERSION = "3.73.0"' in APP
