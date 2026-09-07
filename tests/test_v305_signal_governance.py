import pandas as pd

from signal_governance import (
    ACTION_DEEMPHASISE,
    ACTION_KEEP,
    ACTION_MIXED,
    ACTION_RETIRE,
    ACTION_WAIT,
    build_signal_governance,
    governance_decision,
    signal_governance_summary,
)


def _rows(statuses, cases=30):
    return pd.DataFrame({
        "Status": statuses,
        "Oberoende case": [cases] * len(statuses),
    })


def test_one_horizon_can_never_promote_or_retire():
    assert governance_decision(_rows(["Lovande"], 100))["Åtgärd"] == ACTION_WAIT
    assert governance_decision(_rows(["Ifrågasatt"], 100))["Åtgärd"] == ACTION_WAIT


def test_two_consistent_positive_horizons_support_keep_only():
    result = governance_decision(_rows(["Lovande", "Lovande"], 30))
    assert result["Åtgärd"] == ACTION_KEEP
    assert "inte att automatiskt öka vikten" in result["Skäl"]


def test_mixed_horizon_evidence_stays_under_watch():
    result = governance_decision(_rows(["Lovande", "Ifrågasatt", "Oklart"], 50))
    assert result["Åtgärd"] == ACTION_MIXED


def test_two_questioned_horizons_can_trigger_deemphasis_review():
    result = governance_decision(_rows(["Ifrågasatt", "Ifrågasatt"], 30))
    assert result["Åtgärd"] == ACTION_DEEMPHASISE


def test_retirement_requires_three_questioned_horizons_and_larger_sample():
    assert governance_decision(_rows(["Ifrågasatt"] * 3, 47))["Åtgärd"] == ACTION_DEEMPHASISE
    assert governance_decision(_rows(["Ifrågasatt"] * 3, 48))["Åtgärd"] == ACTION_RETIRE


def test_horizon_case_counts_are_not_summed():
    result = governance_decision(pd.DataFrame({
        "Status": ["Ifrågasatt", "Ifrågasatt", "Ifrågasatt"],
        "Oberoende case": [20, 20, 20],
    }))
    assert result["Största oberoende sample"] == 20
    assert result["Åtgärd"] == ACTION_WAIT


def test_build_governance_keeps_all_six_signals_even_without_history():
    table = build_signal_governance(pd.DataFrame(), pd.DataFrame())
    assert len(table) == 6
    assert set(table["Åtgärd"]) == {ACTION_WAIT}


def test_summary_never_claims_automatic_change():
    table = pd.DataFrame([{"Signal": "X", "Åtgärd": ACTION_RETIRE}])
    summary = signal_governance_summary(table)
    assert "Ingenting tas bort automatiskt" in summary["text"]


def test_app_version_and_governance_ui_are_wired():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Vilka signaler ska Borsify behålla – eller börja ifrågasätta?" in app
    assert "build_signal_governance" in app
    assert "Case räknas aldrig ihop mellan horisonter" in app
