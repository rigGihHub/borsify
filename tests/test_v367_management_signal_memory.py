import sqlite3
from pathlib import Path

from management_signal_memory import (
    compare_management_signal_memory,
    ensure_management_signal_memory_table,
    previous_management_snapshot,
    save_management_snapshot,
    snapshot_from_management_signal,
)

ROOT = Path(__file__).resolve().parents[1]


def _signal(pos="", neg="", titles=""):
    p=[x.strip() for x in pos.split(",") if x.strip()]
    n=[x.strip() for x in neg.split(",") if x.strip()]
    return {
        "Ledningssignal status": "test",
        "Ledningssignal positiva": len(p),
        "Ledningssignal negativa": len(n),
        "Ledningssignal positiva ämnen": ", ".join(p),
        "Ledningssignal negativa ämnen": ", ".join(n),
        "Ledningssignal rubriker": titles,
    }


def test_no_concrete_signal_is_not_saved_as_history():
    assert snapshot_from_management_signal("AAA.ST", _signal(), {"news": []}, "2026-09-09") is None
    out=compare_management_signal_memory(None, None)
    assert out["Ledningsminne historik"] is False


def test_identical_repeated_scan_is_deduplicated():
    events={"news":[{"title":"CEO says demand is improving", "published_at":"2026-09-08T08:00:00Z"}]}
    snap=snapshot_from_management_signal("AAA.ST", _signal("Efterfrågan", titles="CEO says demand is improving"), events, "2026-09-09")
    conn=sqlite3.connect(":memory:")
    ensure_management_signal_memory_table(conn)
    save_management_snapshot(conn, snap); save_management_snapshot(conn, snap)
    count=conn.execute("select count(*) from management_signal_snapshots").fetchone()[0]
    assert count == 1
    assert snap["signal_date"] == "2026-09-08"


def test_positive_polarity_shift_is_detected():
    prev=snapshot_from_management_signal("AAA.ST", _signal(neg="Efterfrågan", titles="CEO says demand is weak"), None, "2026-08-01")
    cur=snapshot_from_management_signal("AAA.ST", _signal(pos="Efterfrågan, Marginal", titles="CEO says demand is improving | CFO says margins expand"), None, "2026-09-09")
    out=compare_management_signal_memory(cur, prev)
    assert out["Ledningsminne positiv"] is True
    assert out["Ledningsminne negativ"] is False
    assert out["Ledningsminne status"] == "Ledningsspråket stärks brett"


def test_missing_old_topic_is_not_treated_as_new_negative_signal():
    prev=snapshot_from_management_signal("AAA.ST", _signal(pos="Efterfrågan, Marginal", titles="a | b"), None, "2026-08-01")
    cur=snapshot_from_management_signal("AAA.ST", _signal(pos="Efterfrågan", titles="c"), None, "2026-09-09")
    out=compare_management_signal_memory(cur, prev)
    assert out["Ledningsminne negativ"] is False


def test_previous_snapshot_excludes_current_fingerprint():
    conn=sqlite3.connect(":memory:")
    first=snapshot_from_management_signal("AAA.ST", _signal(pos="Efterfrågan", titles="a"), None, "2026-08-01")
    second=snapshot_from_management_signal("AAA.ST", _signal(pos="Marginal", titles="b"), None, "2026-09-09")
    save_management_snapshot(conn, first); save_management_snapshot(conn, second)
    prev=previous_management_snapshot(conn, "AAA.ST", second["signal_key"])
    assert prev["signal_key"] == first["signal_key"]


def test_version_and_app_wiring():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'compare_management_signal_memory' in app
    assert 'Ledningsminne status' in app
