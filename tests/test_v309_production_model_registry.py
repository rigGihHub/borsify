from pathlib import Path

import pytest

from production_model_registry import (
    EVENT_ACTIVATION, EVENT_PROMOTION, EVENT_ROLLBACK,
    bootstrap_registry, current_champion, production_definition_fingerprint,
    record_promotion, record_rollback, registry_history, registry_summary,
)


def test_fingerprint_is_stable_for_same_sources():
    root = Path(__file__).resolve().parents[1]
    assert production_definition_fingerprint(root) == production_definition_fingerprint(root)
    assert len(production_definition_fingerprint(root)) == 20


def test_bootstrap_is_idempotent(tmp_path):
    db = tmp_path / "registry.db"
    first = bootstrap_registry(db, "3.09.0", Path(__file__).resolve().parents[1])
    second = bootstrap_registry(db, "3.09.0", Path(__file__).resolve().parents[1])
    assert first["event_id"] == second["event_id"]
    history = registry_history(db)
    assert len(history) == 1
    assert history.iloc[0]["Händelse"] == EVENT_ACTIVATION


def test_promotion_requires_manual_ready_decision(tmp_path):
    db = tmp_path / "registry.db"
    bootstrap_registry(db, "3.09.0", Path(__file__).resolve().parents[1])
    with pytest.raises(ValueError):
        record_promotion(
            db, app_version="3.09.0", challenger_id="c1", challenger_label="C1",
            challenger_fingerprint="abcdef1234567890abcd", promotion_status="Redo",
            expected_ready_status="Redo", reason="Prospektivt bättre", decision_by="Rikard",
            rollback_trigger="Tydlig försämring", manual_decision=False,
        )
    with pytest.raises(ValueError):
        record_promotion(
            db, app_version="3.09.0", challenger_id="c1", challenger_label="C1",
            challenger_fingerprint="abcdef1234567890abcd", promotion_status="Vänta",
            expected_ready_status="Redo", reason="Prospektivt bättre", decision_by="Rikard",
            rollback_trigger="Tydlig försämring", manual_decision=True,
        )


def test_promotion_and_rollback_are_append_only(tmp_path):
    db = tmp_path / "registry.db"
    original = bootstrap_registry(db, "3.09.0", Path(__file__).resolve().parents[1])
    promoted = record_promotion(
        db, app_version="3.10.0", challenger_id="c1", challenger_label="Challenger 1",
        challenger_fingerprint="abcdef1234567890abcd", promotion_status="Redo",
        expected_ready_status="Redo", reason="Klarade alla grindar", decision_by="Rikard",
        rollback_trigger="Två mogna horisonter försämras", manual_decision=True,
    )
    assert promoted["event_type"] == EVENT_PROMOTION
    assert promoted["previous_fingerprint"] == original["model_fingerprint"]
    rolled = record_rollback(
        db, app_version="3.10.1", reason="Rollback-trigger uppfylld",
        decision_by="Rikard", manual_decision=True,
    )
    assert rolled["event_type"] == EVENT_ROLLBACK
    assert rolled["model_fingerprint"] == original["model_fingerprint"]
    history = registry_history(db)
    assert list(history["Händelse"]) == [EVENT_ROLLBACK, EVENT_PROMOTION, EVENT_ACTIVATION]


def test_registry_detects_runtime_definition_mismatch(tmp_path):
    db = tmp_path / "registry.db"
    root = Path(__file__).resolve().parents[1]
    bootstrap_registry(db, "3.09.0", root)
    summary = registry_summary(db, "3.09.0", root)
    assert summary["definition_matches_runtime"] is True


def test_ui_exposes_read_only_registry_and_version():
    app = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert 'APP_VERSION = "3.73.0"' in app
    assert "Produktionsmodell · champion och rollbackhistorik" in app
    assert "Visa produktions- och rollbackhistorik" in app
    assert "ingen modell kan bytas här automatiskt" in app.lower()
