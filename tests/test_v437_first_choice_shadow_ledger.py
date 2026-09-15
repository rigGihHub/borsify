import json
from datetime import datetime, timezone
from pathlib import Path

from first_choice_audit import build_first_choice_record, get_first_choice_records, save_first_choice_records


ROOT = Path(__file__).resolve().parents[1]


def _row(ticker="AAA", blockers=""):
    return {
        "Ticker": ticker, "Namn": "Alpha", "Pris": 101.5, "Prisdatum": "2026-09-15",
        "Borsify Score": 77.0, "Dagens relevans": 71.0,
        "Value Trap verdict": "MARKET_WRONG", "Analysis Confidence nivå": 3,
        "Förstaval godkänd": not blockers, "Förstaval blockerare": blockers,
        "_history": "must not be frozen",
    }


def test_record_is_point_in_time_and_role_specific():
    captured = datetime(2026, 9, 15, 8, 30, tzinfo=timezone.utc)
    incumbent = build_first_choice_record(_row(), "incumbent", "balanserad", "Norden", captured)
    gated = build_first_choice_record(_row(), "evidence_gated", "balanserad", "Norden", captured)
    assert incumbent["record_id"] != gated["record_id"]
    assert incumbent["captured_date"] == "2026-09-15"
    snapshot = json.loads(incumbent["snapshot_json"])
    assert snapshot["Pris"] == 101.5
    assert "_history" not in snapshot


def test_same_daily_observation_is_idempotent(tmp_path):
    db = tmp_path / "borsify.db"
    record = build_first_choice_record(
        _row(), "incumbent", "balanserad", "Norden",
        datetime(2026, 9, 15, 8, 30, tzinfo=timezone.utc),
    )
    assert save_first_choice_records(db, [record]) == 1
    assert save_first_choice_records(db, [record]) == 0
    saved = get_first_choice_records(db)
    assert len(saved) == 1


def test_different_roles_are_saved_as_shadow_pair(tmp_path):
    db = tmp_path / "borsify.db"
    captured = datetime(2026, 9, 15, 8, 30, tzinfo=timezone.utc)
    records = [
        build_first_choice_record(_row("OLD", "rött köpläge"), "incumbent", "p", "m", captured),
        build_first_choice_record(_row("NEW"), "evidence_gated", "p", "m", captured),
    ]
    assert save_first_choice_records(db, records) == 2
    saved = get_first_choice_records(db)
    assert set(saved["role"]) == {"incumbent", "evidence_gated"}
    assert set(saved["symbol"]) == {"OLD", "NEW"}


def test_no_empty_symbol_is_persisted(tmp_path):
    db = tmp_path / "borsify.db"
    record = build_first_choice_record(_row(""), "incumbent", "p", "m")
    assert save_first_choice_records(db, [record]) == 0


def test_app_freezes_both_choices_without_changing_score():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    audit = (ROOT / "first_choice_audit.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.37.0"' in app
    assert '"incumbent", profile, market' in app
    assert '"evidence_gated", profile, market' in app
    assert "bq_first_choice_gate_changed" in app
    assert "Borsify Score" in audit
    assert "add_scores" not in audit
