import sqlite3
from pathlib import Path

from consensus_change_memory import (
    compare_consensus_memory, ensure_consensus_memory_table, previous_snapshot,
    save_snapshot, snapshot_from_result,
)


def _result(bull=.55, median=110, dispersion=.50, analysts=10):
    return {
        "Konsensus analytiker antal": analysts,
        "Konsensus bullish andel": bull,
        "Konsensus bearish andel": .1,
        "Riktkurs medel": median,
        "Riktkurs median": median,
        "Riktkurs hög": median * 1.25,
        "Riktkurs låg": median * .75,
        "Riktkurs dispersion": dispersion,
        "Konsensus uppgraderingar 45d": 2,
        "Konsensus nedgraderingar 45d": 0,
        "Konsensus initierad bevakning 45d": 0,
    }


def test_no_backfill_means_too_little_history():
    snap = snapshot_from_result("ABC.ST", _result(), "2026-09-09")
    out = compare_consensus_memory(snap, None)
    assert out["Konsensusminne status"] == "För lite historik"
    assert out["Konsensusminne historik"] is False


def test_detects_higher_targets_and_narrower_dispersion():
    prev = snapshot_from_result("ABC.ST", _result(bull=.50, median=100, dispersion=.60), "2026-09-02")
    cur = snapshot_from_result("ABC.ST", _result(bull=.54, median=106, dispersion=.48), "2026-09-09")
    out = compare_consensus_memory(cur, prev)
    assert out["Konsensusminne status"] == "Riktkurserna samlas kring högre nivå"
    assert out["Konsensusminne positiv"] is True


def test_detects_consensus_deterioration():
    prev = snapshot_from_result("ABC.ST", _result(bull=.70, median=120), "2026-09-02")
    cur = snapshot_from_result("ABC.ST", _result(bull=.55, median=108), "2026-09-09")
    out = compare_consensus_memory(cur, prev)
    assert out["Konsensusminne status"] == "Konsensus försämras"
    assert out["Konsensusminne negativ"] is True


def test_sqlite_memory_is_point_in_time_and_daily_idempotent():
    conn = sqlite3.connect(":memory:")
    ensure_consensus_memory_table(conn)
    first = snapshot_from_result("ABC.ST", _result(median=100), "2026-09-01")
    save_snapshot(conn, first)
    save_snapshot(conn, first)
    assert conn.execute("select count(*) from consensus_change_snapshots").fetchone()[0] == 1
    prev = previous_snapshot(conn, "ABC.ST", "2026-09-09")
    assert prev["captured_date"] == "2026-09-01"


def test_release_wiring():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.81.0"' in app
    assert "compare_consensus_memory" in app
    assert "Konsensusminne status" in app
