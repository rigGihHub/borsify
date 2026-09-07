import json
import pandas as pd

from policy_promotion_protocol import (
    GATE_FAIL,
    GATE_PASS,
    GATE_WAIT,
    STATUS_REVIEW,
    policy_calibration_gate,
    policy_data_coverage_gate,
    policy_promotion_protocol,
    policy_promotion_summary,
    policy_rollback_plan,
)
from prospective_policy_registry import default_prospective_policies, prospective_policy_results


def _data():
    recs, outs = [], []
    base = pd.Timestamp("2026-09-07")
    # 80 independent cases, split between SVAG and MYCKET SVAG. Each regime has
    # enough policy-ok and policy-weak observations for the locked policy test.
    for i in range(80):
        requirement = (i % 4) < 2
        regime = "SVAG" if i < 40 else "MYCKET SVAG"
        snap = {
            "Marknadsläge": regime,
            "Short Momentum": 72,
            "Short Catalyst": 70 if requirement else 40,
            "Short Revisions": 45,
            "Short Trend": 66,
            "Short Relative Strength": 64,
            "Idiosynkratisk volatilitet status": "INGEN TYDLIG EXTRA RISK",
            "Evidence Family Support Count": 3,
        }
        recs.append({
            "record_id": f"r{i}", "symbol": f"S{i}",
            "captured_date": (base + pd.Timedelta(days=i * 45)).date().isoformat(),
            "model_version": "3.17.0", "horizon_type": "short",
            "snapshot_json": json.dumps(snap), "score": 70,
        })
        for horizon in ("1m", "3m", "6m"):
            outs.append({
                "record_id": f"r{i}", "horizon": horizon,
                "return_pct": 0.18 if requirement else -0.05,
            })
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_calibration_and_coverage_gates_pass_on_clean_prospective_sample():
    recs, outs = _data()
    policy = default_prospective_policies()[0]
    detail = prospective_policy_results(recs, outs, ["1m", "3m", "6m"])
    assert policy_calibration_gate(detail, policy)["status"] == GATE_PASS
    assert policy_data_coverage_gate(recs, policy)["status"] == GATE_PASS


def test_missing_policy_field_blocks_data_coverage():
    recs, _ = _data()
    policy = default_prospective_policies()[0]
    recs["snapshot_json"] = recs["snapshot_json"].map(
        lambda raw: json.dumps({k: v for k, v in json.loads(raw).items() if k != "Short Revisions"})
    )
    assert policy_data_coverage_gate(recs, policy)["status"] == GATE_FAIL


def test_full_protocol_can_only_open_manual_review_and_never_auto_activate():
    recs, outs = _data()
    policy = default_prospective_policies()[0]
    protocol, gates = policy_promotion_protocol(recs, outs, [policy])
    assert protocol.iloc[0]["Status"] == STATUS_REVIEW
    assert protocol.iloc[0]["Godkända kontroller"] == 5
    assert set(gates["Status"]) == {GATE_PASS}
    summary = policy_promotion_summary(protocol)
    assert summary["status"] == STATUS_REVIEW
    assert "manuellt" in summary["text"].lower()
    assert policy_rollback_plan(policy)["automatic"].startswith("Nej")


def test_empty_history_waits_instead_of_promoting():
    policy = default_prospective_policies()[0]
    protocol, gates = policy_promotion_protocol(pd.DataFrame(), pd.DataFrame(), [policy])
    assert protocol.iloc[0]["Status"] != STATUS_REVIEW
    assert GATE_WAIT in set(gates["Status"])


def test_v317_ui_and_version_contract():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Policy Promotion Protocol" in app
    assert "policy_promotion_protocol" in app
    assert "aktiverar aldrig en policy automatiskt" in app
