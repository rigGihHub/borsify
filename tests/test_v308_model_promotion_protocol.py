import json
import pandas as pd

from model_promotion_protocol import (
    GATE_FAIL, GATE_PASS, GATE_WAIT, STATUS_BLOCK, STATUS_REVIEW, STATUS_WAIT,
    promotion_data_coverage, promotion_regime_gate, rollback_plan,
    model_promotion_protocol,
)
from prospective_challenger_registry import ProspectiveChallenger
from signal_ablation import SHORT_WEIGHTS


def _snap(regime="Positiv"):
    s = {"PIT Complete": True, "Marknadsläge": regime, "Short Vetoes": "—"}
    for i, (_, (field, _)) in enumerate(SHORT_WEIGHTS.items()):
        s[field] = 70 + i
    return json.dumps(s)


def test_data_coverage_requires_point_in_time_and_signal_completeness():
    spec = ProspectiveChallenger("x", "Test", "Momentum", "hyp")
    recs = pd.DataFrame([
        {"model_version": "3.07.0", "captured_date": "2026-09-06", "snapshot_json": _snap()},
        {"model_version": "3.08.0", "captured_date": "2026-09-07", "snapshot_json": _snap()},
    ])
    result = promotion_data_coverage(recs, spec)
    assert result["status"] == GATE_PASS
    assert result["pit_complete_rate"] == 1.0
    assert result["signal_complete_rate"] == 1.0


def test_data_coverage_fails_when_frozen_signals_are_missing():
    spec = ProspectiveChallenger("x", "Test", "Momentum", "hyp")
    bad = json.loads(_snap())
    bad.pop(next(iter(SHORT_WEIGHTS.values()))[0])
    recs = pd.DataFrame([{"model_version": "3.07.0", "captured_date": "2026-09-06", "snapshot_json": json.dumps(bad)}])
    assert promotion_data_coverage(recs, spec)["status"] == GATE_FAIL


def test_regime_gate_waits_for_two_mature_regimes():
    audit = pd.DataFrame([
        {"Marknadsläge": "Positiv", "Oberoende case": 20, "Förändring topp-botten": 0.01},
        {"Marknadsläge": "Negativ", "Oberoende case": 8, "Förändring topp-botten": 0.02},
    ])
    assert promotion_regime_gate(audit)["status"] == GATE_WAIT


def test_regime_gate_blocks_material_regime_damage():
    audit = pd.DataFrame([
        {"Marknadsläge": "Positiv", "Oberoende case": 20, "Förändring topp-botten": 0.01},
        {"Marknadsläge": "Negativ", "Oberoende case": 20, "Förändring topp-botten": -0.03},
    ])
    assert promotion_regime_gate(audit)["status"] == GATE_FAIL


def test_rollback_contract_is_explicit_and_never_automatic():
    spec = ProspectiveChallenger("x", "Test", "Momentum", "hyp")
    plan = rollback_plan(spec)
    assert plan["status"] == GATE_PASS
    assert "föregående champion" in plan["champion_backup"].lower()
    assert plan["automatic"].startswith("Nej")


def test_protocol_waits_instead_of_promoting_without_outcomes():
    protocol, gates = model_promotion_protocol(pd.DataFrame(), pd.DataFrame())
    assert not protocol.empty
    assert set(protocol["Status"]) == {STATUS_WAIT}
    assert STATUS_REVIEW not in set(protocol["Status"])
    assert not gates.empty


def test_v308_ui_and_version_are_wired():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Model Promotion Protocol" in app
    assert "promotionskrav och rollback-plan" in app
