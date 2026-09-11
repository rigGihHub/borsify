import pandas as pd
from research_signal_decision_gate import (
    signal_decision, apply_signal_decision_gate,
    DECISION_COLLECT, DECISION_PAUSE, DECISION_PROMOTE,
)


def _row(**overrides):
    row = {
        "Hypotes": "Post-Report Drift",
        "Åtgärd": "Promotion-granskning",
        "Mogna horisonter": 3,
        "Största sample": 45,
        "Regimrobusthet": "Stöd i flera regimer",
        "Signalöverlapp": "Lågt överlapp",
        "Incrementellt värde": "Tydligt inkrementellt stöd",
        "Kostnad/omsättning": "Kostnad/omsättning verifierad",
        "Out-of-sample": "Prospektiv PIT-evidens finns",
        "Datakvalitet": "Datakvalitet verifierad",
        "Blockerare": "",
    }
    row.update(overrides)
    return row


def test_gate_pass_requires_all_strict_checks():
    d=signal_decision(_row())
    assert d["Beslut"] == DECISION_PROMOTE
    assert d["Gate"] == "PASS"


def test_gate_waits_when_any_blocker_remains():
    d=signal_decision(_row(Blockerare="datakvalitet", Datakvalitet="Ej verifierad"))
    assert d["Beslut"] == DECISION_COLLECT
    assert d["Gate"] == "VÄNTA"


def test_high_overlap_cannot_pass_promotion_gate():
    d=signal_decision(_row(Signalöverlapp="Högt överlapp"))
    assert d["Beslut"] == DECISION_COLLECT
    assert "överlapp" in d["Skäl"].lower()


def test_negative_incremental_value_pauses_hypothesis():
    d=signal_decision(_row(**{"Incrementellt värde":"Inget inkrementellt värde"}))
    assert d["Beslut"] == DECISION_PAUSE
    assert d["Gate"] == "STOPP"


def test_critical_review_queue_is_pause_not_auto_kill():
    d=signal_decision(_row(**{"Åtgärd":"Granska kritiskt"}))
    assert d["Beslut"] == DECISION_PAUSE
    assert "Ingen automatisk kill" in d["Manuell åtgärd"]


def test_apply_gate_and_app_wiring():
    out=apply_signal_decision_gate(pd.DataFrame([_row()]))
    assert out.iloc[0]["Beslut"] == DECISION_PROMOTE
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Signal Decision Gate" in app
    assert "apply_signal_decision_gate(apply_data_quality(" in app
