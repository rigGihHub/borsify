from pathlib import Path

import pytest

from production_policy_registry import (
    EVENT_ACTIVATION,
    EVENT_PROMOTION,
    EVENT_ROLLBACK,
    active_policy_fingerprint,
    bootstrap_policy_registry,
    policy_registry_history,
    policy_registry_summary,
    record_policy_promotion,
    record_policy_rollback,
)
from policy_promotion_protocol import STATUS_REVIEW


def test_policy_registry_bootstrap_is_idempotent_and_matches_runtime(tmp_path):
    db = tmp_path / "policy_registry.db"
    first = bootstrap_policy_registry(db, "3.18.0")
    second = bootstrap_policy_registry(db, "3.18.0")
    assert first["event_id"] == second["event_id"]
    assert first["event_type"] == EVENT_ACTIVATION
    assert first["policy_fingerprint"] == active_policy_fingerprint()
    summary = policy_registry_summary(db, "3.18.0")
    assert summary["definition_matches_runtime"] is True
    assert len(policy_registry_history(db)) == 1


def test_policy_promotion_requires_manual_ready_decision(tmp_path):
    db = tmp_path / "policy_registry.db"
    bootstrap_policy_registry(db, "3.18.0")
    with pytest.raises(ValueError):
        record_policy_promotion(
            db, app_version="3.18.0", candidate_policy_id="policy-x", candidate_label="Policy X",
            candidate_fingerprint="abcdef1234567890", promotion_status=STATUS_REVIEW,
            expected_ready_status=STATUS_REVIEW, reason="Godkänt test", decision_by="Rikard",
            rollback_trigger="Försämrad modellhälsa", manual_decision=False,
        )
    with pytest.raises(ValueError):
        record_policy_promotion(
            db, app_version="3.18.0", candidate_policy_id="policy-x", candidate_label="Policy X",
            candidate_fingerprint="abcdef1234567890", promotion_status="Vänta",
            expected_ready_status=STATUS_REVIEW, reason="Godkänt test", decision_by="Rikard",
            rollback_trigger="Försämrad modellhälsa", manual_decision=True,
        )


def test_recorded_promotion_does_not_pretend_runtime_changed(tmp_path):
    db = tmp_path / "policy_registry.db"
    bootstrap_policy_registry(db, "3.18.0")
    promoted = record_policy_promotion(
        db, app_version="3.18.0", candidate_policy_id="policy-x", candidate_label="Policy X",
        candidate_fingerprint="abcdef1234567890", promotion_status=STATUS_REVIEW,
        expected_ready_status=STATUS_REVIEW, reason="Alla grindar godkända", decision_by="Rikard",
        rollback_trigger="Försämrad modellhälsa", manual_decision=True,
    )
    assert promoted["event_type"] == EVENT_PROMOTION
    summary = policy_registry_summary(db, "3.18.0")
    assert summary["definition_matches_runtime"] is False
    assert "runtime" in summary["status"].lower()


def test_policy_rollback_restores_previous_registered_definition(tmp_path):
    db = tmp_path / "policy_registry.db"
    original = bootstrap_policy_registry(db, "3.18.0")
    record_policy_promotion(
        db, app_version="3.18.0", candidate_policy_id="policy-x", candidate_label="Policy X",
        candidate_fingerprint="abcdef1234567890", promotion_status=STATUS_REVIEW,
        expected_ready_status=STATUS_REVIEW, reason="Alla grindar godkända", decision_by="Rikard",
        rollback_trigger="Försämrad modellhälsa", manual_decision=True,
    )
    rolled = record_policy_rollback(
        db, app_version="3.18.0", reason="Rollback-test", decision_by="Rikard", manual_decision=True,
    )
    assert rolled["event_type"] == EVENT_ROLLBACK
    assert rolled["policy_fingerprint"] == original["policy_fingerprint"]
    assert policy_registry_summary(db, "3.18.0")["definition_matches_runtime"] is True
    assert list(policy_registry_history(db)["Händelse"]) == [EVENT_ROLLBACK, EVENT_PROMOTION, EVENT_ACTIVATION]


def test_v318_ui_schema_and_version_contract():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    schema = (root / "supabase_schema.sql").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.38.0"' in app
    assert "Produktionspolicy · aktiv urvalspolicy och rollbackhistorik" in app
    assert "policy_registry_summary" in app
    assert "aktiverar aldrig en policy automatiskt" in app
    assert "production_policy_events" in schema
